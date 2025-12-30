from fastapi import APIRouter

# ====================
# Core router (ALWAYS ON)
# ====================
core_router = APIRouter()

from .v1.health import router as health_router

core_router.include_router(
    health_router,
    prefix="/v1",
    tags=["Health"]
)

# ====================
# Auth router (OPTIONAL)
# ====================
auth_router = APIRouter()

# ⚠️ IMPORTANT:
# Do NOT import this in minimal mode
def get_auth_router() -> APIRouter:
    router = APIRouter()
    from .v1.auth import router as _auth_router
    from .v1.integrations import router as _integrations_router
    router.include_router(
        _auth_router,
        prefix="/v1/auth",
        tags=["Authentication"]
    )
    router.include_router(
        _integrations_router,
        prefix="/v1/integrations",
        tags=["Integrations"]
    )
    return router


__all__ = ["core_router", "auth_router"]
