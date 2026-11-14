"""Hourly: API KN quota and key expiry (docs/SPEC.md §4.2, §5.1).

Usage: python -m app.ops.quota_watch    (StavUctu is free: not counted against the quota)
"""

from __future__ import annotations

import datetime as dt
import logging
import sys

from app.api.protection import RateLimiter
from app.clients.api_kn import ApiKnClient, ApiKnError, NullCache, StavUctu
from app.config import Settings, get_settings
from app.db import get_engine
from app.ops.alerts import Alerter

log = logging.getLogger(__name__)


def check(status: StavUctu, settings: Settings, alerter: Alerter, today: dt.date) -> list[str]:
    sent = []
    used = status.provedeno_volani / status.limit_volani if status.limit_volani else 0
    for level in sorted(settings.ops.quota_warn_levels, reverse=True):
        if used >= level:
            key = f"quota{int(level * 100)}:{status.aktualni_obdobi}"
            msg = (
                f"API KN quota {used:.0%} used ({status.provedeno_volani}/{status.limit_volani}) "
                f"in period {status.aktualni_obdobi}"
            )
            if alerter.send(key, msg):
                sent.append(key)
            break  # only the highest level reached
    if status.expirace_api_key:
        days = (status.expirace_api_key.date() - today).days
        if days <= settings.ops.key_expiry_warn_days:
            key = f"key_expiry:{status.expirace_api_key.date()}"
            if alerter.send(
                key, f"API KN key expires in {days} days ({status.expirace_api_key.date()})"
            ):
                sent.append(key)
    return sent


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = get_settings()
    alerter = Alerter(settings.ops, RateLimiter(get_engine()))
    try:
        status = ApiKnClient.from_settings(settings, NullCache()).account_status()
    except ApiKnError as e:
        alerter.send("api_kn_unreachable", f"API KN account status failed: {type(e).__name__}")
        return 1
    log.info(
        "API KN period=%s used=%s/%s key_expires=%s",
        status.aktualni_obdobi,
        status.provedeno_volani,
        status.limit_volani,
        status.expirace_api_key,
    )
    check(status, settings, alerter, dt.date.today())
    return 0


if __name__ == "__main__":
    sys.exit(main())
