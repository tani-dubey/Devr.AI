from pydantic_settings import BaseSettings
from dotenv import load_dotenv
from pydantic import field_validator, ConfigDict
from typing import Optional

load_dotenv()

class Settings(BaseSettings):
    ## CORE (minimal code)
    backend_url: str =""
    
    ## OPTIONAL
    
    # Gemini LLM API Key
    gemini_api_key: Optional[str] = None

    # Tavily API Key
    tavily_api_key: Optional[str] = None

    # Platforms
    github_token: Optional[str] = None
    discord_bot_token: Optional[str] = None

    # DB configuration
    supabase_url: Optional[str] = None
    supabase_key: Optional[str] = None


    # LangSmith Tracing
    langsmith_tracing: bool = False
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_api_key: str = ""
    langsmith_project: str = "DevR_AI"

    # Agent Configuration
    devrel_agent_model: str = "gemini-2.5-flash"
    github_agent_model: str = "gemini-2.5-flash"
    classification_agent_model: str = "gemini-2.0-flash"
    agent_timeout: int = 30
    max_retries: int = 3

    # RabbitMQ configuration
    rabbitmq_url: Optional[str] = None

    # Onboarding UX toggles
    onboarding_show_oauth_button: bool = True

    ## used where supabase is required feature
    def require_supabase():
        if not settings.supabase_url or not settings.supabase_key:
            raise RuntimeError(
                "Supabase is not configured. "
                "This feature is unavailable in minimal local mode."
            )


    model_config = ConfigDict(
        env_file=".env",
        extra="ignore"
    )  # to prevent errors from extra env variables


settings = Settings()
