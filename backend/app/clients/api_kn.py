"""ČÚZK API KN client with a Postgres response cache (docs/SPEC.md §4.2, §5.1).

Every call counts against a daily quota of 500 (incl. 404s), so responses are cached:
positive 24 h, negative (404) 6 h, codebooks 7 d. 429 and 5xx are never cached.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from dataclasses import dataclass
from typing import Protocol

import httpx
from pydantic import BaseModel, ConfigDict, TypeAdapter
from pydantic.alias_generators import to_camel
from sqlalchemy import Engine, text

from app.config import Settings

log = logging.getLogger(__name__)

# ---------- errors ----------


class ApiKnError(Exception):
    pass


class ApiKnQuotaExceeded(ApiKnError):
    """HTTP 429: daily quota used up. Report degrades, never fails (SPEC §4.2)."""


class ApiKnAuthError(ApiKnError):
    """HTTP 401/403: key missing, invalid or expired."""


class ApiKnUnavailable(ApiKnError):
    """Timeout, network error or 5xx."""


# ---------- response models (only fields we use; extra fields ignored) ----------


class _Model(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")


class Ref(_Model):
    kod: int
    nazev: str


class LvRef(_Model):
    id: int
    cislo: int
    katastralni_uzemi: Ref | None = None


class ParcelaDef(_Model):
    id: int
    katastralni_uzemi: Ref


class JednotkaDef(_Model):
    id: int
    cislo_jednotky: int


class RizeniDef(_Model):
    id: int
    typ_rizeni: str
    poradove_cislo: int
    rok: int
    kod_pracoviste: int


class Stavba(_Model):
    id: int
    typ_stavby: Ref | None = None
    cisla_domovni: list[int] = []
    cast_obce: Ref | None = None
    obec: Ref | None = None
    lv: LvRef | None = None
    zpusob_vyuziti: Ref | None = None
    jednotky: list[JednotkaDef] = []
    parcely: list[ParcelaDef] = []
    rizeni_plomby: list[RizeniDef] = []


class Jednotka(_Model):
    id: int
    cislo_jednotky: int
    typ_jednotky: Ref | None = None
    zpusob_vyuziti: Ref | None = None
    lv: LvRef | None = None
    rizeni_plomby: list[RizeniDef] = []


class Operace(_Model):
    nazev: str
    datum_provedeni: dt.datetime | None = None


class Rizeni(_Model):
    id: int
    typ_rizeni: str
    poradove_cislo: int
    rok: int
    kod_pracoviste: int
    datum_prijeti: dt.datetime | None = None
    stav: str | None = None
    provedene_operace: list[Operace] = []


class StavUctu(_Model):
    aktualni_obdobi: str
    provedeno_volani: int
    limit_volani: int
    expirace_api_key: dt.datetime | None = None


@dataclass(frozen=True)
class Fetched[T]:
    data: T
    as_of: dt.datetime | None
    from_cache: bool


# ---------- cache ----------


@dataclass(frozen=True)
class CachedResponse:
    status: int
    body: dict | None


class Cache(Protocol):
    def get(self, key: str) -> CachedResponse | None: ...
    def put(self, key: str, status: int, body: dict | None, ttl_s: int) -> None: ...


class NullCache:
    def get(self, key: str) -> CachedResponse | None:
        return None

    def put(self, key: str, status: int, body: dict | None, ttl_s: int) -> None:
        pass


class PgCache:
    """Shared external-response cache (table external_cache), keys prefixed per source.
    Holds public register data only, no request metadata."""

    def __init__(self, engine: Engine, prefix: str = "kn:") -> None:
        self.engine = engine
        self.prefix = prefix

    def get(self, key: str) -> CachedResponse | None:
        with self.engine.connect() as c:
            row = c.execute(
                text(
                    "SELECT status, body FROM external_cache WHERE key = :k AND expires_at > now()"
                ),
                {"k": self.prefix + key},
            ).first()
        return CachedResponse(row.status, row.body) if row else None

    def put(self, key: str, status: int, body: dict | None, ttl_s: int) -> None:
        with self.engine.begin() as c:
            c.execute(
                text(
                    "INSERT INTO external_cache (key, status, body, expires_at) "
                    "VALUES (:k, :s, CAST(:b AS jsonb), now() + make_interval(secs => :ttl)) "
                    "ON CONFLICT (key) DO UPDATE SET status = EXCLUDED.status, "
                    "body = EXCLUDED.body, fetched_at = now(), expires_at = EXCLUDED.expires_at"
                ),
                {
                    "k": self.prefix + key,
                    "s": status,
                    "b": json.dumps(body) if body is not None else None,
                    "ttl": ttl_s,
                },
            )


# ---------- client ----------


class ApiKnClient:
    def __init__(self, http: httpx.Client, cache: Cache, settings: Settings) -> None:
        self.http = http
        self.cache = cache
        self.ttl = settings.cuzk_cache_ttl_s
        self.negative_ttl = settings.cuzk_cache_negative_ttl_s
        self.codebook_ttl = settings.cuzk_cache_codebook_ttl_s
        self.calls = 0  # HTTP calls made by this instance (quota spent)

    @classmethod
    def from_settings(cls, settings: Settings, cache: Cache) -> ApiKnClient:
        if not settings.cuzk_api_key:
            raise ApiKnAuthError("CUZK_API_KEY is not set")
        http = httpx.Client(
            base_url=settings.cuzk_api_base_url,
            headers={
                "ApiKey": settings.cuzk_api_key.get_secret_value(),
                "Accept": "application/json",
            },
            timeout=settings.cuzk_timeout_s,
        )
        return cls(http, cache, settings)

    # --- public API ---

    def stavba_by_adresni_misto(self, kod: int) -> Fetched[Stavba] | None:
        return self._fetch(f"/Stavby/AdresniMisto/{kod}", Stavba, self.ttl)

    def jednotka(self, id_: int) -> Fetched[Jednotka] | None:
        return self._fetch(f"/Jednotky/{id_}", Jednotka, self.ttl)

    def rizeni(self, id_: int) -> Fetched[Rizeni] | None:
        return self._fetch(f"/Rizeni/{id_}", Rizeni, self.ttl)

    def codebook(self, name: str) -> list[Ref]:
        res = self._fetch(f"/CiselnikyISKN/{name}", list[Ref], self.codebook_ttl)
        return res.data if res else []

    def account_status(self) -> StavUctu:
        """Not cached and not counted against the quota."""
        r = self._request("/AplikacniSluzby/StavUctu")
        return StavUctu.model_validate(r.json())

    # --- internals ---

    def _fetch(self, path: str, model, ttl_s: int) -> Fetched | None:
        hit = self.cache.get(path)
        if hit is not None:
            return self._parse(hit.status, hit.body, model, from_cache=True)

        r = self._request(path)
        self.calls += 1
        if r.status_code == 404:
            self.cache.put(path, 404, None, self.negative_ttl)
            return None
        body = r.json()
        self.cache.put(path, 200, body, ttl_s)
        return self._parse(200, body, model, from_cache=False)

    def _request(self, path: str) -> httpx.Response:
        try:
            r = self.http.get(path)
        except httpx.HTTPError as e:
            raise ApiKnUnavailable(f"{path}: {e}") from e
        if r.status_code == 429:
            raise ApiKnQuotaExceeded(path)
        if r.status_code in (401, 403):
            raise ApiKnAuthError(f"{path}: HTTP {r.status_code}")
        if r.status_code >= 500:
            raise ApiKnUnavailable(f"{path}: HTTP {r.status_code}")
        if r.status_code not in (200, 404):
            raise ApiKnError(f"{path}: unexpected HTTP {r.status_code}")
        return r

    @staticmethod
    def _parse(status: int, body: dict | None, model, *, from_cache: bool) -> Fetched | None:
        if status == 404 or body is None:
            return None
        data = TypeAdapter(model).validate_python(body.get("data"))
        as_of = body.get("aktualnostDatK")
        return Fetched(
            data=data,
            as_of=dt.datetime.fromisoformat(as_of) if as_of else None,
            from_cache=from_cache,
        )
