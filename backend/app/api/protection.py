"""Backend protection (docs/SPEC.md §4.2): rate limits and client attestation.

Counters live in an UNLOGGED Postgres table, keyed by salted SHA-256 of the IP / device
key id (salt rotates daily), never the raw identifier, never linked to report content.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
from dataclasses import dataclass
from typing import Protocol

from fastapi import HTTPException, Request
from sqlalchemy import Engine, text

from app.config import Settings


def hashed(kind: str, value: str, salt: str) -> str:
    day_salt = f"{salt}:{dt.date.today().isoformat()}".encode()
    return f"{kind}:" + hmac.new(day_salt, value.encode(), hashlib.sha256).hexdigest()[:32]


class RateLimiter:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def add(self, key: str, window_s: int, amount: int = 1) -> int:
        """Add to the counter of the current window; returns the new total."""
        with self.engine.begin() as c:
            return c.execute(
                text(
                    """
                    INSERT INTO rate_limit_counter AS r (key, window_start, count, expires_at)
                    VALUES (:k,
                            to_timestamp(floor(extract(epoch FROM now()) / :w) * :w),
                            :n,
                            to_timestamp(floor(extract(epoch FROM now()) / :w) * :w + :w))
                    ON CONFLICT (key, window_start) DO UPDATE SET count = r.count + :n
                    RETURNING count
                    """
                ),
                {"k": key, "w": window_s, "n": amount},
            ).scalar_one()

    def current(self, key: str, window_s: int) -> int:
        with self.engine.connect() as c:
            return (
                c.execute(
                    text(
                        "SELECT count FROM rate_limit_counter WHERE key = :k AND window_start = "
                        "to_timestamp(floor(extract(epoch FROM now()) / :w) * :w)"
                    ),
                    {"k": key, "w": window_s},
                ).scalar()
                or 0
            )

    def hit(self, key: str, limit: int, window_s: int) -> None:
        if self.add(key, window_s) > limit:
            raise HTTPException(
                status_code=429,
                detail={"code": "rate_limited"},
                headers={"Retry-After": str(window_s)},
            )

    def cleanup(self) -> None:
        with self.engine.begin() as c:
            c.execute(text("DELETE FROM rate_limit_counter WHERE expires_at < now()"))


def client_ip(request: Request, settings: Settings) -> str:
    if settings.protection.trust_forwarded_for:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ---------------- attestation ----------------


@dataclass(frozen=True)
class ClientIdentity:
    provider: str
    device_key: str | None  # hashed attested key id; None when not attested


class AttestationProvider(Protocol):
    def verify(self, request: Request) -> ClientIdentity: ...


class DisabledAttestation:
    """Dev / Simulator mode (App Attest needs a real device). Accepts every request."""

    def verify(self, request: Request) -> ClientIdentity:
        return ClientIdentity(provider="disabled", device_key=None)


def make_attestation(settings: Settings) -> AttestationProvider:
    mode = settings.protection.attestation_mode
    if mode == "disabled":
        return DisabledAttestation()
    # app_attest: M4 (SPEC §4.2). Fail at startup rather than silently accepting.
    raise ValueError(f"attestation mode {mode!r} is not implemented yet")
