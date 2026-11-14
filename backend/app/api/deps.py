"""Shared app services, created once in the lifespan and injected per request."""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from fastapi import Request
from sqlalchemy import Engine

from app.api.protection import AttestationProvider, RateLimiter
from app.clients.api_kn import ApiKnClient, PgCache
from app.clients.registers import AresClient, IsirClient
from app.config import Settings


@dataclass
class Services:
    settings: Settings
    engine: Engine
    http_kn: httpx.Client
    http_registers: httpx.Client
    attestation: AttestationProvider
    limiter: RateLimiter

    # Per-request client instances (call counting for the API KN budget).
    def api_kn(self) -> ApiKnClient:
        return ApiKnClient(self.http_kn, PgCache(self.engine, "kn:"), self.settings)

    def ares(self) -> AresClient:
        return AresClient(self.http_registers, PgCache(self.engine, "ares:"))

    def isir(self) -> IsirClient:
        return IsirClient(self.http_registers, PgCache(self.engine, "isir:"))


def make_services(settings: Settings, engine: Engine, attestation: AttestationProvider) -> Services:
    key = settings.cuzk_api_key.get_secret_value() if settings.cuzk_api_key else ""
    return Services(
        settings=settings,
        engine=engine,
        http_kn=httpx.Client(
            base_url=settings.cuzk_api_base_url,
            headers={"ApiKey": key, "Accept": "application/json"},
            timeout=settings.cuzk_timeout_s,
        ),
        http_registers=httpx.Client(timeout=15),
        attestation=attestation,
        limiter=RateLimiter(engine),
    )


def get_services(request: Request) -> Services:
    return request.app.state.services
