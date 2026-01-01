import logging
import asyncio
import discord
from discord import app_commands
from discord.ext import commands, tasks

from app.core.config import settings
from app.core.orchestration.queue_manager import AsyncQueueManager, QueuePriority

from app.agents.devrel.onboarding.messages import (
    build_encourage_verification_message,
    build_new_user_welcome,
    build_verified_capabilities_intro,
    build_verified_welcome,
)

from integrations.discord.bot import DiscordBot
from integrations.discord.views import OAuthView, OnboardingView, build_final_handoff_embed

logger = logging.getLogger(__name__)


# ============================================================
# Core / Non-Auth utilities
# ============================================================

def github_verification_enabled() -> bool:
    """True only when GitHub + Supabase are configured."""
    return all([
        settings.github_token,
        settings.supabase_url,
        settings.supabase_key,
    ])


async def send_github_unavailable(interaction: discord.Interaction):
    embed = discord.Embed(
        title="❌ GitHub Verification Unavailable",
        description=(
            "GitHub verification is disabled on this server.\n\n"
            "**Reason:** GitHub and/or Supabase is not configured.\n\n"
            "If you're running locally, this is expected in minimal mode."
        ),
        color=discord.Color.red(),
    )
    await interaction.followup.send(embed=embed, ephemeral=True)


# ============================================================
# DevRel Commands Cog
# ============================================================

class DevRelCommands(commands.Cog):
    def __init__(self, bot: DiscordBot, queue_manager: AsyncQueueManager):
        self.bot = bot
        self.queue = queue_manager

    # ---------------------------
    # Lifecycle
    # ---------------------------

    def cog_load(self):
        if github_verification_enabled():
            self.token_cleanup_task.start()
        else:
            logger.info("Skipping token cleanup task (Supabase disabled)")

    def cog_unload(self):
        if self.token_cleanup_task.is_running():
            self.token_cleanup_task.cancel()

    # ---------------------------
    # Background task (lazy)
    # ---------------------------

    @tasks.loop(minutes=5)
    async def token_cleanup_task(self):
        if not github_verification_enabled():
            return
        try:
            from app.services.auth.verification import cleanup_expired_tokens
            await cleanup_expired_tokens()
        except Exception as e:
            logger.error(f"Token cleanup failed: {e}")

    @token_cleanup_task.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

    # ---------------------------
    # Non-Auth Commands
    # ---------------------------

    @app_commands.command(name="reset", description="Reset your DevRel thread and memory.")
    async def reset_thread(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        await self.queue.enqueue(
            {
                "type": "clear_thread_memory",
                "memory_thread_id": user_id,
                "user_id": user_id,
                "cleanup_reason": "manual_reset",
            },
            QueuePriority.HIGH,
        )
        self.bot.active_threads.pop(user_id, None)
        await interaction.response.send_message(
            "Your DevRel thread & memory have been reset!",
            ephemeral=True,
        )

    @app_commands.command(name="help", description="Show DevRel assistant help.")
    async def help_devrel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="DevRel Assistant Help",
            description="I can help you with Devr.AI related questions!",
            color=discord.Color.blue(),
        )
        embed.add_field(
            name="Commands",
            value=(
                "• `/reset`\n"
                "• `/help`\n"
                "• `/verify_github`\n"
                "• `/verification_status`"
            ),
            inline=False,
        )
        await interaction.response.send_message(embed=embed)

    # ---------------------------
    # Auth-Dependent Commands
    # ---------------------------

    @app_commands.command(name="verification_status")
    async def verification_status(self, interaction: discord.Interaction):
        if not github_verification_enabled():
            await send_github_unavailable(interaction)
            return

        from app.services.auth.management import get_or_create_user_by_discord

        profile = await get_or_create_user_by_discord(
            discord_id=str(interaction.user.id),
            display_name=interaction.user.display_name,
            discord_username=interaction.user.name,
            avatar_url=str(interaction.user.avatar.url) if interaction.user.avatar else None,
        )

        if profile.is_verified:
            embed = discord.Embed(title="✅ Verified", color=discord.Color.green())
            embed.add_field(name="GitHub", value=profile.github_username)
        else:
            embed = discord.Embed(
                title="❌ Not Verified",
                description="Use `/verify_github` to link your account.",
                color=discord.Color.red(),
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="verify_github")
    async def verify_github(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        if not github_verification_enabled():
            await send_github_unavailable(interaction)
            return

        from app.services.auth.management import get_or_create_user_by_discord
        from app.services.auth.supabase import login_with_github
        from app.services.auth.verification import create_verification_session

        profile = await get_or_create_user_by_discord(
            discord_id=str(interaction.user.id),
            display_name=interaction.user.display_name,
            discord_username=interaction.user.name,
            avatar_url=str(interaction.user.avatar.url) if interaction.user.avatar else None,
        )

        if profile.is_verified:
            await interaction.followup.send("✅ Already verified.", ephemeral=True)
            return

        session_id = await create_verification_session(str(interaction.user.id))
        callback_url = f"{settings.backend_url}/v1/auth/callback?session={session_id}"
        auth_url = (await login_with_github(redirect_to=callback_url))["url"]

        embed = discord.Embed(
            title="🔗 Link GitHub",
            description="Click below to authenticate.",
            color=discord.Color.blue(),
        )

        await interaction.followup.send(
            embed=embed,
            view=OAuthView(auth_url, "GitHub"),
            ephemeral=True,
        )


# ============================================================
# Onboarding Cog (Supabase-safe)
# ============================================================

class OnboardingCog(commands.Cog):
    def __init__(self, bot: DiscordBot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if not github_verification_enabled():
            await member.send(
                "👋 Welcome to Devr.AI!\n\n"
                "GitHub verification is disabled in local mode."
            )
            return

        from app.services.auth.management import get_or_create_user_by_discord
        await get_or_create_user_by_discord(
            discord_id=str(member.id),
            display_name=member.display_name,
            discord_username=member.name,
            avatar_url=str(member.avatar.url) if member.avatar else None,
        )


# ============================================================
# Extension loader
# ============================================================

async def setup(bot: commands.Bot):
    await bot.add_cog(DevRelCommands(bot, bot.queue_manager))
    await bot.add_cog(OnboardingCog(bot))