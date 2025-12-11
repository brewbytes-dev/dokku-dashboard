"""Application configuration."""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings from environment variables."""

    # Dokku SSH settings
    dokku_host: str = "128.140.127.105"
    dokku_user: str = "dokku"
    dokku_ssh_key: str = "/root/.ssh/id_rsa"

    # App settings
    app_name: str = "Dokku Dashboard"
    debug: bool = False

    class Config:
        env_prefix = "DASHBOARD_"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()

