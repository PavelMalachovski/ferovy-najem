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

    # --- Ingestion (SPEC §5.2, §5) ---
    mf_rent_map_page_url: str = (
        "https://mf.gov.cz/cs/rozpoctova-politika/podpora-projektoveho-rizeni/"
        "cenova-mapa/cenova-mapa-infografika"
    )
    ruian_csv_url_template: str = "https://vdp.cuzk.gov.cz/vymenny_format/csv/{date}_OB_ADR_csv.zip"
    # Municipalities loaded for address autocomplete: Praha, Brno. Use --all for whole CZ.
    ruian_obce: list[int] = [554782, 582786]

    # --- API KN cache TTLs in seconds (SPEC §4.2) ---
    cuzk_cache_ttl_s: int = 24 * 3600
    cuzk_cache_negative_ttl_s: int = 6 * 3600
    cuzk_cache_codebook_ttl_s: int = 7 * 24 * 3600


@lru_cache
def get_settings() -> Settings:
    return Settings()
