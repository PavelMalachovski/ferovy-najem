"""Backend protection (docs/SPEC.md §4.2): rate limits and client attestation.

Counters live in an UNLOGGED Postgres table, keyed by salted SHA-256 of the IP / device
key id (salt rotates daily), never the raw identifier, never linked to report content.
"""

from __future__ import annotations

import base64
import binascii
import datetime as dt
import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
from typing import Protocol

from fastapi import HTTPException, Request
from sqlalchemy import Engine, text

from app.attest.app_attest import AppAttestVerifier, AttestationError, AttestedKey
from app.config import Settings

log = logging.getLogger(__name__)


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
    device_key: str | None  # SHA-256 of the attested key id; None when not attested


class AttestationProvider(Protocol):
    required: bool

    def verify(self, request: Request, body: bytes) -> ClientIdentity: ...
    def new_challenge(self) -> bytes | None: ...
    def register(self, key_id: bytes, attestation: bytes, challenge: bytes) -> None: ...


def _unauthorized(code: str) -> HTTPException:
    return HTTPException(status_code=401, detail={"code": code})


def _b64(value: str | None) -> bytes | None:
    if not value:
        return None
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        return None


class DisabledAttestation:
    """Dev / Simulator mode (App Attest needs a real device). Accepts every request."""

    required = False

    def verify(self, request: Request, body: bytes) -> ClientIdentity:
        return ClientIdentity(provider="disabled", device_key=None)

    def new_challenge(self) -> bytes | None:
        return None

    def register(self, key_id: bytes, attestation: bytes, challenge: bytes) -> None:
        raise HTTPException(status_code=404, detail={"code": "attestation_disabled"})


class AppAttestProvider:
    """Headers on protected requests: X-App-Attest-Key and X-App-Attest-Assertion (base64)."""

    required = True

    def __init__(
        self,
        engine: Engine,
        verifier: AppAttestVerifier,
        environment: str,
        allow_unattested: bool,
        challenge_ttl_s: int,
    ) -> None:
        self.engine = engine
        self.verifier = verifier
        self.environment = environment
        self.allow_unattested = allow_unattested
        self.challenge_ttl_s = challenge_ttl_s

    @staticmethod
    def key_hash(key_id: bytes) -> str:
        return hashlib.sha256(key_id).hexdigest()

    def new_challenge(self) -> bytes:
        challenge = secrets.token_bytes(32)
        with self.engine.begin() as c:
            c.execute(text("DELETE FROM attest_challenge WHERE expires_at < now()"))
            c.execute(
                text(
                    "INSERT INTO attest_challenge (challenge_hash, expires_at) "
                    "VALUES (:h, now() + make_interval(secs => :ttl))"
                ),
                {"h": hashlib.sha256(challenge).hexdigest(), "ttl": self.challenge_ttl_s},
            )
        return challenge

    def register(self, key_id: bytes, attestation: bytes, challenge: bytes) -> None:
        with self.engine.begin() as c:
            used = c.execute(
                text(
                    "DELETE FROM attest_challenge WHERE challenge_hash = :h AND expires_at > now() "
                    "RETURNING 1"
                ),
                {"h": hashlib.sha256(challenge).hexdigest()},
            ).first()
        if not used:
            raise _unauthorized("attestation_challenge_invalid")
        try:
            key = self.verifier.verify_attestation(key_id, attestation, challenge)
        except AttestationError as e:
            log.warning("attestation rejected: %s", e)
            raise _unauthorized("attestation_failed") from e
        with self.engine.begin() as c:
            c.execute(
                text(
                    "INSERT INTO attested_key (key_hash, public_key_der, counter, environment) "
                    "VALUES (:h, :pk, 0, :env) ON CONFLICT (key_hash) DO NOTHING"
                ),
                {"h": self.key_hash(key_id), "pk": key.public_key_der, "env": self.environment},
            )

    def verify(self, request: Request, body: bytes) -> ClientIdentity:
        key_id = _b64(request.headers.get("x-app-attest-key"))
        assertion = _b64(request.headers.get("x-app-attest-assertion"))
        if key_id is None or assertion is None:
            if self.allow_unattested:
                return ClientIdentity(provider="unattested", device_key=None)
            raise _unauthorized("attestation_required")
        h = self.key_hash(key_id)
        with self.engine.begin() as c:
            row = c.execute(
                text(
                    "SELECT public_key_der, counter FROM attested_key "
                    "WHERE key_hash = :h FOR UPDATE"
                ),
                {"h": h},
            ).first()
            if row is None:
                raise _unauthorized("attestation_unknown_key")  # client should re-attest
            try:
                counter = self.verifier.verify_assertion(
                    AttestedKey(key_id, bytes(row.public_key_der), row.counter), assertion, body
                )
            except AttestationError as e:
                log.warning("assertion rejected: %s", e)
                raise _unauthorized("attestation_failed") from e
            c.execute(
                text(
                    "UPDATE attested_key SET counter = :n, last_used_at = now() WHERE key_hash = :h"
                ),
                {"n": counter, "h": h},
            )
        return ClientIdentity(provider="app_attest", device_key=h)


def make_attestation(settings: Settings, engine: Engine) -> AttestationProvider:
    p = settings.protection
    if p.attestation_mode == "disabled":
        return DisabledAttestation()
    if p.attestation_mode == "app_attest":
        if not p.app_attest_app_id:
            raise ValueError("PROTECTION__APP_ATTEST_APP_ID is required for app_attest mode")
        verifier = AppAttestVerifier(p.app_attest_app_id, p.app_attest_environment)
        return AppAttestProvider(
            engine, verifier, p.app_attest_environment, p.allow_unattested, p.attest_challenge_ttl_s
        )
    raise ValueError(f"unknown attestation mode {p.attestation_mode!r}")
