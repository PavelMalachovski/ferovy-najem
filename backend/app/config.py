from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env",),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "dev"
    database_url: str = "postgresql+psycopg://ferovy:ferovy@localhost:5432/ferovy"

    cuzk_api_key: SecretStr | None = None
    cuzk_api_base_url: str = "https://api-kn.cuzk.gov.cz/api/v1"
    cuzk_timeout_s: float = 15.0

    cors_allow_origins: list[str] = []


@lru_cache
def get_settings() -> Settings:
    return Settings()
