"""ARES (company register) and ISIR (insolvency register) clients (docs/SPEC.md §5, §5.3).

Personal-data rule: fields are whitelisted BEFORE caching. For natural persons (OSVČ) no
name is kept and ISIR is not queried at all (MVP decision 2026-11-14).
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import asdict, dataclass, field
from typing import Literal
from xml.sax.saxutils import escape

import httpx
from defusedxml import ElementTree as ET

from app.clients.api_kn import Cache

log = logging.getLogger(__name__)

# ARES PravniForma codes whose name contains "fyzická osoba" (codebook checked 2026-11-14).
NATURAL_PERSON_FORMS = {"101", "102", "105", "106", "107", "108", "424", "425"}


class RegisterUnavailable(Exception):
    pass


def valid_ico(ico: str) -> bool:
    """Czech IČO: 8 digits, mod-11 checksum."""
    if len(ico) != 8 or not ico.isdigit():
        return False
    s = sum(int(d) * w for d, w in zip(ico[:7], range(8, 1, -1), strict=True))
    return int(ico[7]) == (11 - s % 11) % 10


# ---------------- ARES ----------------


@dataclass(frozen=True)
class Company:
    ico: str
    name: str | None  # None for natural persons
    legal_form: str | None
    natural_person: bool
    active: bool
    founded: dt.date | None
    ended: dt.date | None
    isir_source_state: str | None  # ARES seznamRegistraci.stavZdrojeIr (semantics undocumented)


class AresClient:
    BASE = "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest"

    def __init__(self, http: httpx.Client, cache: Cache, ttl_s: int = 24 * 3600) -> None:
        self.http = http
        self.cache = cache
        self.ttl = ttl_s

    def company(self, ico: str) -> Company | None:
        key = f"ico:{ico}"
        hit = self.cache.get(key)
        if hit is not None:
            return None if hit.status == 404 else _company_from_cache(hit.body)
        try:
            r = self.http.get(f"{self.BASE}/ekonomicke-subjekty/{ico}")
        except httpx.HTTPError as e:
            raise RegisterUnavailable(f"ARES: {e}") from e
        if r.status_code in (400, 404):
            self.cache.put(key, 404, None, self.ttl)
            return None
        if r.status_code != 200:
            raise RegisterUnavailable(f"ARES: HTTP {r.status_code}")
        c = parse_ares(r.json())
        self.cache.put(key, 200, _company_to_cache(c), self.ttl)
        return c


def parse_ares(d: dict) -> Company:
    form = d.get("pravniForma")
    natural = form is None or form in NATURAL_PERSON_FORMS  # unknown form → treat as person
    reg = d.get("seznamRegistraci") or {}
    ended = d.get("datumZaniku")
    return Company(
        ico=d["ico"],
        name=None if natural else d.get("obchodniJmeno"),
        legal_form=form,
        natural_person=natural,
        active=ended is None and reg.get("stavZdrojeRos") == "AKTIVNI",
        founded=dt.date.fromisoformat(d["datumVzniku"]) if d.get("datumVzniku") else None,
        ended=dt.date.fromisoformat(ended) if ended else None,
        isir_source_state=reg.get("stavZdrojeIr"),
    )


def _company_to_cache(c: Company) -> dict:
    d = asdict(c)
    d["founded"] = c.founded.isoformat() if c.founded else None
    d["ended"] = c.ended.isoformat() if c.ended else None
    return d


def _company_from_cache(d: dict) -> Company:
    return Company(
        **d
        | {
            "founded": dt.date.fromisoformat(d["founded"]) if d["founded"] else None,
            "ended": dt.date.fromisoformat(d["ended"]) if d["ended"] else None,
        }
    )


# ---------------- ISIR ----------------

ISIR_URL = "https://isir.justice.cz:8443/isir_cuzk_ws/IsirWsCuzkService"
ISIR_NS = "http://isirws.cca.cz/types/"
# Only these fields of a proceeding are kept (SPEC §5.3); everything else may be personal data.
ISIR_KEEP = (
    "druhStavKonkursu",
    "bcVec",
    "rocnik",
    "cisloSenatu",
    "nazevOrganizace",
    "datumPmZahajeniUpadku",
    "datumPmUkonceniUpadku",
    "urlDetailRizeni",
)


@dataclass(frozen=True)
class Insolvency:
    status: Literal["none", "active", "unknown"]
    proceedings: list[dict] = field(default_factory=list)  # whitelisted fields only


def isir_request(ico: str) -> str:
    return (
        '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
        f'xmlns:typ="{ISIR_NS}"><soapenv:Body><typ:getIsirWsCuzkDataRequest>'
        f"<ic>{escape(ico)}</ic><maxPocetVysledku>10</maxPocetVysledku>"
        "<filtrAktualniRizeni>T</filtrAktualniRizeni>"
        "<maxRelevanceVysledku>2</maxRelevanceVysledku>"
        "</typ:getIsirWsCuzkDataRequest></soapenv:Body></soapenv:Envelope>"
    )


def parse_isir(xml: bytes, ico: str) -> Insolvency:
    root = ET.fromstring(xml)
    resp = root.find(f".//{{{ISIR_NS}}}getIsirWsCuzkDataResponse")
    if resp is None:
        return Insolvency("unknown")
    code = resp.findtext("stav/kodChyby")
    if code == "WS2":  # empty result = no ongoing proceeding
        return Insolvency("none")
    if code:  # WS1/WS3/WS4 (sync stopped), SQL1, SERVER1
        log.warning("ISIR error %s: %s", code, resp.findtext("stav/textChyby"))
        return Insolvency("unknown")
    proceedings = []
    for d in resp.findall("data"):
        if d.findtext("dalsiDluznikVRizeni") == "T":  # co-debtor added by the service
            continue
        if d.findtext("ic") != ico:
            continue
        proceedings.append({k: d.findtext(k) for k in ISIR_KEEP})
    return Insolvency("active" if proceedings else "none", proceedings)


class IsirClient:
    def __init__(self, http: httpx.Client, cache: Cache, ttl_s: int = 3600) -> None:
        self.http = http
        self.cache = cache
        self.ttl = ttl_s

    def check_company(self, ico: str) -> Insolvency:
        """Only for legal persons (caller's responsibility; see module docstring)."""
        key = f"ico:{ico}"
        hit = self.cache.get(key)
        if hit is not None:
            return Insolvency(**hit.body)
        try:
            r = self.http.post(
                ISIR_URL,
                content=isir_request(ico).encode(),
                headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": '""'},
            )
        except httpx.HTTPError as e:
            log.warning("ISIR unavailable: %s", e)
            return Insolvency("unknown")
        if r.status_code != 200:
            log.warning("ISIR HTTP %s", r.status_code)
            return Insolvency("unknown")
        result = parse_isir(r.content, ico)
        if result.status != "unknown":
            self.cache.put(key, 200, asdict(result), self.ttl)
        return result
