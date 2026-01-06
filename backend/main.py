import asyncio
import logging
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

# from app.api.router import api_router
from app.api.router import core_router
from app.core.config import settings
from app.core.orchestration.queue_manager import AsyncQueueManager
from app.database.weaviate.client import get_weaviate_client

# DevRel commands are now loaded dynamically (commented out below)
# from integrations.discord.cogs import DevRelCommands

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DevRAIApplication:
    """
    Manages the application's core components and background tasks.
    """

    def __init__(self):
        """Initializes all services required by the application."""
        self.weaviate_client = None
        self.queue_manager = AsyncQueueManager()
        if settings.supabase_key and settings.supabase_url:
            from app.core.orchestration.agent_coordinator import AgentCoordinator
            self.agent_coordinator = AgentCoordinator(self.queue_manager)

        self.discord_bot= None
        self.weaviate_enabled= True
        if settings.discord_bot_token:
            from integrations.discord.bot import DiscordBot
            from discord.ext import commands
            self.discord_bot= DiscordBot(self.queue_manager)

    async def start_background_tasks(self):
        logger.info("Starting background tasks...")

        try:
            # 1. Start queue (mandatory)
            if settings.rabbitmq_url:
                await self.queue_manager.start(num_workers=3)
                logger.info("Queue manager started")
            else:
                logger.info("Queue manager disabled (minimal local mode)")


            # 2. Optional Weaviate
            if self.weaviate_enabled:
                try:
                    await self.test_weaviate_connection()
                    logger.info("Weaviate enabled")
                except Exception as e:
                    logger.warning("Weaviate disabled: %s", e)
                    self.weaviate_enabled = False

            # 3. Optional Discord
            if self.discord_bot:
                try:
                    await self.discord_bot.load_extension("integrations.discord.cogs")
                    asyncio.create_task(
                        self.discord_bot.start(settings.discord_bot_token)
                    )
                    logger.info("Discord bot started")
                except Exception as e:
                    logger.info("Discord startup failed")
                    self.discord_bot = None
            else:
                logger.info("Discord disabled (no token)")

            logger.info("Background tasks started successfully")

        except Exception as e:
            logger.error("Startup failed: %s", e, exc_info=True)
            await self.stop_background_tasks()
            raise



    async def test_weaviate_connection(self):
        """Test Weaviate connection during startup."""
        try:
            async with get_weaviate_client() as client:
                if await client.is_ready():
                    logger.info("Weaviate connection successful and ready")
        except Exception as e:
            logger.error(f"Failed to connect to Weaviate: {e}")
            raise

    async def stop_background_tasks(self):
        """Stops all background tasks and connections gracefully."""
        logger.info("Stopping background tasks and closing connections...")
        try:
            if self.discord_bot and not self.discord_bot.is_closed():
                await self.discord_bot.close()
                logger.info("Discord bot has been closed.")
        except Exception as e:
            logger.error(f"Error closing Discord bot: {e}", exc_info=True)
        try:
            await self.queue_manager.stop()
            logger.info("Queue manager has been stopped.")
        except Exception as e:
            logger.error(f"Error stopping queue manager: {e}", exc_info=True)
        logger.info("All background tasks and connections stopped.")


# --- FASTAPI LIFESPAN AND APP INITIALIZATION ---
app_instance = DevRAIApplication()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan manager for the FastAPI application. Handles startup and shutdown events.
    """
    app.state.app_instance = app_instance
    await app_instance.start_background_tasks()
    yield
    await app_instance.stop_background_tasks()


api = FastAPI(title="Devr.AI API", version="1.0", lifespan=lifespan)

# Configure CORS
api.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite default dev server
        "http://localhost:3000",  # Alternative dev server
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@api.get("/favicon.ico")
async def favicon():
    """Return empty favicon to prevent 404 logs"""
    return Response(status_code=204)

# api.include_router(api_router)
# --- Core routes (always enabled) ---
api.include_router(core_router)
logger.info("Core API routes enabled")

# --- Optional: Auth / OAuth routes ---
if settings.supabase_key and settings.supabase_url:
    try:
        from app.api.v1.auth import router as auth_router
        api.include_router(auth_router, prefix="/auth", tags=["auth"])
        logger.info("Auth routes enabled (Supabase detected)")
    except Exception as e:
        logger.error(f"Failed to load auth routes: {e}", exc_info=True)
else:
    logger.info("Auth routes disabled (minimal local mode)")


if __name__ == "__main__":
    required_vars = [
        "BACKEND_URL"
    ]
    optional_vars = {
        "supabase": ["SUPABASE_URL", "SUPABASE_KEY"],
        "discord" : ["DISCORD_BOT_TOKEN"],
        "llm":["GEMINI_API_KEY"],
        "queue": ["RABBITMQ_URL"],  
        "search": ["TAVILY_API_KEY"],
        "github": ["GITHUB_TOKEN"]
    }
    missing_vars = [var for var in required_vars if not getattr(settings, var.lower(), None)]

    if missing_vars:
        raise RuntimeError(f"Core backend misconfigured. Missing: {','.join(missing_vars)} ")

    # Optional features
    feature_status={}
    for feature, vars in optional_vars.items():
        enabled= all(getattr(settings, var.lower(),None) for var in vars
        )
        feature_status[feature]=enabled

        if not enabled:
           logger.warning(f" {feature.capitalize()} disable - running on minimal local mode"
         )
    app_instance.feature_status = feature_status

    # for nice DX 
    enabled = [f for f, ok in feature_status.items() if ok]
    logger.info(f"Enabled integrations: {', '.join(enabled) or 'none'}")


    uvicorn.run(
        "__main__:api",
        host="0.0.0.0",
        port=8000,
        reload=True,
        ws_ping_interval=20,
        ws_ping_timeout=20
    )