from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./app.db"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "insecure-dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    admin_email: str = "admin@example.com"
    admin_password: str = "change-me"

    liara_api_key: str = ""
    # Must include the AI service id: https://ai.liara.ir/api/v1/<AI_SERVICE_ID>
    liara_base_url: str = "https://ai.liara.ir/api/v1"
    liara_default_model: str = "openai/gpt-4.1-mini"
    # A premium reasoning model planning a project can think for minutes before it answers;
    # 60s cut Opus off mid-plan. This is the per-request ceiling - the agent's own
    # timeout_seconds still bounds the run as a whole.
    provider_timeout_seconds: float = 300.0

    workspaces_dir: str = "./workspaces"


@lru_cache
def get_settings() -> Settings:
    return Settings()
