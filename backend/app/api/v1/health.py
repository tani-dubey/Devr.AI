import logging
from fastapi import APIRouter, HTTPException, Request
from app.core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)
services={}

@router.get("/health")
async def health_check(request: Request):
    """
    General health check endpoint to verify services are running.

    Returns:
        dict: Status of the application and its services
    """
    try:
        if settings.code_intelligence_enabled:
            from app.database.weaviate.client import get_weaviate_client
            async with get_weaviate_client() as client:
                services["weaviate"] = (
                    "ready" if await client.is_ready() else "not_ready"
                )
        else:
            services["weaviate"] = "disabled"

        return {
            "status": "healthy",
            "services": services,
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unhealthy",
                "error": str(e)
            }
        ) from e


@router.get("/health/weaviate")
async def weaviate_health():
    """Check specifically Weaviate service health."""
    try:
        is_ready = None
        if settings.code_intelligence_enabled:
            from app.database.weaviate.client import get_weaviate_client
            async with get_weaviate_client() as client:
                is_ready = await client.is_ready()

        return {
            "service": "weaviate",
            "status": "ready" if is_ready else "not_ready"
        }
    except Exception as e:
        logger.error(f"Weaviate health check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "service": "weaviate",
                "status": "unhealthy",
                "error": str(e)
            }
        ) from e


@router.get("/health/discord")
async def discord_health(request: Request):
    """Check specifically Discord bot health."""
    try:
        app_instance = request.app.state.app_instance
        
        services = {
            "discord_bot": (
                "running"
                if app_instance.discord_bot
                and not app_instance.discord_bot.is_closed()
                else "stopped"
            )
        }
        return {
            "service": "discord_bot",
            "status": services
        }        
        
    except Exception as e:
        logger.error(f"Discord bot health check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "service": "discord_bot",
                "status": "unhealthy",
                "error": str(e)
            }
        ) from e
