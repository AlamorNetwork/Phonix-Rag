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
    liara_base_url: str = "https://ai.liara.ir/api/v1"
    liara_default_model: str = "openai/gpt-4o-mini"

    workspaces_dir: str = "./workspaces"


@lru_cache
def get_settings() -> Settings:
    return Settings()
