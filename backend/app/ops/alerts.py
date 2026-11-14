"""Operational alerts: always logged; optionally sent to Telegram. Deduplicated per day."""

from __future__ import annotations

import logging

import httpx

from app.api.protection import RateLimiter
from app.config import OpsSettings

log = logging.getLogger("app.alerts")
DAY = 86400


class Alerter:
    def __init__(self, ops: OpsSettings, limiter: RateLimiter, http: httpx.Client | None = None):
        self.ops = ops
        self.limiter = limiter
        self.http = http or httpx.Client(timeout=10)

    def send(self, key: str, message: str) -> bool:
        """Returns True if sent now, False if this key already alerted today."""
        if self.limiter.add(f"alert:{key}", DAY) > 1:
            return False
        log.warning("ALERT %s: %s", key, message)
        token, chat = self.ops.alert_telegram_bot_token, self.ops.alert_telegram_chat_id
        if token and chat:
            try:
                self.http.post(
                    f"https://api.telegram.org/bot{token.get_secret_value()}/sendMessage",
                    json={"chat_id": chat, "text": f"[ferovy-najem] {message}"},
                ).raise_for_status()
            except httpx.HTTPError as e:
                log.error("telegram alert failed: %s", type(e).__name__)  # never log the token URL
        return True
