from app.core.config import settings
from supabase._async.client import AsyncClient

_client: AsyncClient | None = None

def get_supabase_client() -> AsyncClient:
    global _client
    """
    Returns a shared asynchronous Supabase client instance.
    """
    if _client is None:
        if not settings.supabase_url or not settings.supabase_key:
            raise RuntimeError("Supabase is not configured")
        _client = AsyncClient(
            settings.supabase_url,
            settings.supabase_key,
        )
    return _client
