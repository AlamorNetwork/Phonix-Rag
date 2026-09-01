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

    # "docker" runs agent commands in a throwaway, network-less container; "host" runs them in
    # the workspace directory with only a path restriction. Host mode is for development -
    # anything that executes code needs the container boundary, and tools that do so refuse to
    # run without it rather than quietly falling back.
    sandbox_mode: str = "docker"
    sandbox_image: str = "python:3.12-slim"
    sandbox_memory: str = "512m"
    sandbox_cpus: str = "1.0"
    sandbox_pids_limit: int = 128
    # Commands get no network by default. Only widen this for a specific, scoped reason.
    sandbox_network: str = "none"
    # Leave empty under a rootless daemon (container root is already an unprivileged host
    # user); set e.g. "1000:1000" when the daemon is rootful.
    sandbox_user: str = ""
    sandbox_timeout_seconds: float = 120.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
