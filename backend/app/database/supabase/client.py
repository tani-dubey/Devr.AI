from supabase import AsyncClient
from app.core.config import settings

_supabase_client: AsyncClient | None = None


def get_supabase_client() -> AsyncClient:
    global _supabase_client

    if not settings.supabase_url or not settings.supabase_key:
        raise RuntimeError(
            "Supabase is not configured. "
            "This feature is unavailable in minimal local mode."
        )

    if _supabase_client is None:
        _supabase_client = AsyncClient(
            settings.supabase_url,
            settings.supabase_key
        )

    return _supabase_client
