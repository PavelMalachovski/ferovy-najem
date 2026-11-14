"""Live probe of ČÚZK API KN (M0).

Checks the API key, downloads codebooks, runs one address → building → parcel →
unit → proceeding chain and saves every response as a test fixture.

Usage (from backend/):
    uv run python -m scripts.probe_api_kn --kod <kód adresního místa> [--unit N]

Every call counts against the API KN quota (incl. 404s). The script prints the
quota before and after.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import httpx

from app.config import get_settings

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "api_kn"

CODEBOOKS = [
    "TypyJednotky",
    "ZpusobyVyuzitiJednotky",
    "TypyStavby",
    "ZpusobyVyuzitiStavby",
]

# Defensive guard: API KN must not return personal data (vyhl. 358/2013 § 14a).
# If a response ever contains such keys, refuse to save it as a fixture.
PII_KEY_PATTERN = re.compile(
    r"vlastnik|vlastnic|jmeno|prijmeni|rodne|osoba|subjekt|opravnen|datumNarozeni",
    re.IGNORECASE,
)


class Probe:
    def __init__(self, client: httpx.Client, out_dir: Path) -> None:
        self.client = client
        self.out_dir = out_dir
        self.calls: list[tuple[str, int]] = []

    def get(self, path: str, fixture: str, params: dict[str, Any] | None = None) -> Any:
        r = self.client.get(path, params=params)
        self.calls.append((path, r.status_code))
        print(f"  GET {path} {params or ''} -> {r.status_code}")
        if r.status_code == 404:
            self._save(fixture, {"_status": 404, "body": _safe_json(r)})
            return None
        r.raise_for_status()
        body = r.json()
        self._save(fixture, body)
        return body

    def _save(self, name: str, body: Any) -> None:
        hits = sorted(_find_pii_keys(body))
        if hits:
            sys.exit(f"ABORT: possible personal-data keys {hits} in {name}; not saved.")
        self.out_dir.mkdir(parents=True, exist_ok=True)
        path = self.out_dir / f"{name}.json"
        path.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _safe_json(r: httpx.Response) -> Any:
    try:
        return r.json()
    except ValueError:
        return r.text


def _find_pii_keys(obj: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            if PII_KEY_PATTERN.search(k):
                found.add(k)
            found |= _find_pii_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            found |= _find_pii_keys(v)
    return found


def print_quota(label: str, q: dict[str, Any]) -> None:
    print(
        f"[{label}] period={q.get('aktualniObdobi')} used={q.get('provedenoVolani')} "
        f"limit={q.get('limitVolani')} key_expires={q.get('expiraceApiKey')}"
    )


def collect_plomby(obj: dict[str, Any] | None, scope: str) -> list[tuple[str, dict[str, Any]]]:
    if not obj:
        return []
    return [(scope, r) for r in obj.get("rizeniPlomby") or []]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--kod", type=int, required=True, help="RÚIAN kód adresního místa")
    ap.add_argument("--unit", type=int, help="číslo jednotky (the part after '/')")
    ap.add_argument(
        "--scan-units",
        type=int,
        default=3,
        help="without --unit: fetch up to N units of the building (default 3)",
    )
    ap.add_argument("--skip-codebooks", action="store_true")
    ap.add_argument("--out", type=Path, default=FIXTURES_DIR)
    args = ap.parse_args()

    settings = get_settings()
    if not settings.cuzk_api_key or not settings.cuzk_api_key.get_secret_value():
        sys.exit("CUZK_API_KEY is not set (put it into .env at the repo root).")

    client = httpx.Client(
        base_url=settings.cuzk_api_base_url,
        headers={"ApiKey": settings.cuzk_api_key.get_secret_value(), "Accept": "application/json"},
        timeout=settings.cuzk_timeout_s,
    )
    p = Probe(client, args.out)

    print("a) account status")
    q_before = p.get("/AplikacniSluzby/StavUctu", "stav_uctu_before")
    print_quota("before", q_before)

    if not args.skip_codebooks:
        print("b) codebooks")
        for name in CODEBOOKS:
            p.get(f"/CiselnikyISKN/{name}", f"ciselnik_{name}")

    print("c) address chain")
    stavba_env = p.get(f"/Stavby/AdresniMisto/{args.kod}", f"stavba_adresni_misto_{args.kod}")
    stavba = (stavba_env or {}).get("data")
    if not stavba:
        sys.exit("No building for this address code.")

    parcely = stavba.get("parcely") or []
    print(
        f"  building id={stavba['id']} units={len(stavba.get('jednotky') or [])} "
        f"parcels={len(parcely)} plomby={len(stavba.get('rizeniPlomby') or [])}"
    )
    if parcely:
        ku = parcely[0].get("katastralniUzemi")
        print(f"  k.ú. from Stavba.parcely[0]: {ku}")
        par_env = p.get(f"/Parcely/{parcely[0]['id']}", f"parcela_{parcely[0]['id']}")
        if par_env:
            print(f"  k.ú. from /Parcely: {par_env['data'].get('katastralniUzemi')}")

    jednotky = stavba.get("jednotky") or []
    if args.unit is not None:
        targets = [j for j in jednotky if j.get("cisloJednotky") == args.unit]
        if not targets:
            print(f"  unit {args.unit} not in building.jednotky")
    else:
        targets = jednotky[: args.scan_units]

    plomby = collect_plomby(stavba, "building")
    for j in targets:
        env = p.get(f"/Jednotky/{j['id']}", f"jednotka_{j['id']}")
        unit = (env or {}).get("data")
        if unit:
            print(
                f"  unit {unit.get('cisloJednotky')}: typ={unit.get('typJednotky')} "
                f"vyuziti={unit.get('zpusobVyuziti')} plomby={len(unit.get('rizeniPlomby') or [])}"
            )
            plomby += collect_plomby(unit, f"unit {unit.get('cisloJednotky')}")

    print("d) proceedings (plomby)")
    if not plomby:
        print("  none on building or probed units")
    seen: set[int] = set()
    for scope, r in plomby:
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        env = p.get(f"/Rizeni/{r['id']}", f"rizeni_{r['id']}")
        if env:
            d = env["data"]
            print(
                f"  [{scope}] {d.get('typRizeni')}-{d.get('poradoveCislo')}/{d.get('rok')} "
                f"stav={d.get('stav')!r} prijato={d.get('datumPrijeti')}"
            )

    q_after = p.get("/AplikacniSluzby/StavUctu", "stav_uctu_after")
    print_quota("after", q_after)
    used = (q_after.get("provedenoVolani") or 0) - (q_before.get("provedenoVolani") or 0)
    print(f"\nHTTP calls made: {len(p.calls)}; quota counter delta: {used}")
    print(f"Fixtures saved to {args.out}")


if __name__ == "__main__":
    main()
