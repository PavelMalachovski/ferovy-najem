from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class ScoringSettings(BaseModel):
    """Report thresholds (SPEC §6). Override via env, e.g. SCORING__PRICE_RED_BELOW=0.65."""

    price_red_below: float = 0.70
    price_yellow_below: float = 0.85
    price_yellow_above: float = 1.15
    price_red_above: float = 1.30
    # MF data coverage 1–5; at or below this the price block is capped at yellow.
    price_low_coverage_max: int = 2
    flood_near_m: int = 100
    # Scam flags raised from the questionnaire; anything not listed here is red.
    yellow_flags: list[str] = ["unit_number_withheld"]


class ProtectionSettings(BaseModel):
    """SPEC §4.2. Counters are keyed by salted hashes, never raw IPs."""

    suggest_per_ip_per_minute: int = 60
    report_per_ip_per_hour: int = 10
    report_per_device_per_day: int = 20
    api_kn_daily_budget: int = 450  # of 500/day; leave headroom for ops and ingestion
    trust_forwarded_for: bool = False  # set True only behind our own reverse proxy
    attestation_mode: str = "disabled"  # disabled | app_attest
    app_attest_app_id: str = ""  # "<TeamID>.<bundle id>", e.g. ABCDE12345.cz.ferovynajem.app
    app_attest_environment: str = "production"  # development for Xcode/TestFlight-debug builds
    # Devices without App Attest support (old iPhones, Simulator): IP limits only.
    allow_unattested: bool = False
    attest_challenge_ttl_s: int = 300
    attest_per_ip_per_hour: int = 20


class OpsSettings(BaseModel):
    """Scheduled jobs and alerts. Alerts always go to the log; Telegram if both are set."""

    alert_telegram_bot_token: SecretStr | None = None
    alert_telegram_chat_id: str | None = None
    quota_warn_levels: list[float] = [0.7, 0.9]
    key_expiry_warn_days: int = 30
    attested_key_retention_days: int = 180


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env",),
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    env: str = "dev"
    database_url: str = "postgresql+psycopg://ferovy:ferovy@localhost:5432/ferovy"

    cuzk_api_key: SecretStr | None = None
    cuzk_api_base_url: str = "https://api-kn.cuzk.gov.cz/api/v1"
    cuzk_timeout_s: float = 15.0

    cors_allow_origins: list[str] = []
    # Secret for hashing IPs/device ids in rate-limit counters (rotated daily with the date).
    rate_limit_salt: SecretStr = SecretStr("dev-only-change-me")

    scoring: ScoringSettings = ScoringSettings()
    ops: OpsSettings = OpsSettings()
    protection: ProtectionSettings = ProtectionSettings()

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
