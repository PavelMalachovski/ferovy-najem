"""Dev check for M1: address → building → k.ú. → unit → proceedings → MF reference rent.

Usage:
    python -m app.cli.resolve 21951977 --unit 24 --disposition 2+kk [--lift ...]

Uses the API KN cache, so repeated runs cost no quota.
"""

from __future__ import annotations

import argparse
import sys

from app.clients.api_kn import ApiKnClient, PgCache
from app.config import get_settings
from app.db import get_engine
from app.services import rent_map
from app.services.property import resolve


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("ruian_code", type=int, help="RÚIAN kód adresního místa")
    ap.add_argument("--unit", type=int, help="unit number, e.g. 24 for 1403/24")
    ap.add_argument("--disposition", default="2+kk")
    for f in ("lift", "balcony", "terrace", "furnished", "garage", "new-build"):
        ap.add_argument(f"--{f}", action="store_true")
    args = ap.parse_args(argv)

    settings = get_settings()
    engine = get_engine()
    client = ApiKnClient.from_settings(settings, PgCache(engine))
    p = resolve(client, args.ruian_code, args.unit)

    print(f"address {p.ruian_code}")
    b = p.building
    if b is None:
        print("  building: NOT FOUND")
        return 1
    print(f"  building id={b.id} č.p.={b.cisla_domovni} use={b.use!r}")
    print(f"  units={b.unit_count} LV={b.lv_number}")
    print(f"  obec={b.obec_name} ({b.obec_code})  k.ú.={b.ku_name} ({b.ku_code})")
    print(f"  check level: {p.check_level}  hints={p.hints}")
    if p.check_level == "unit":
        if p.unit:
            u = p.unit
            print(f"  unit {args.unit}: found, use={u.use_name!r} ({u.use_code}) LV={u.lv_number}")
            print(f"    type={u.type_name!r}")
        else:
            print(f"  unit {args.unit}: NOT FOUND in this building")
    for r in p.proceedings:
        state = "in progress" if r.in_progress else "finished"
        print(f"  řízení {r.number} on {r.scope}: {state} ({r.stav!r}, received {r.received})")
    if not p.proceedings:
        print("  řízení: none")

    features = rent_map.Features(
        lift=args.lift,
        balcony=args.balcony,
        terrace=args.terrace,
        furnished=args.furnished,
        garage=args.garage,
        new_build=args.new_build,
    )
    vk = rent_map.size_category(args.disposition)
    ref = rent_map.lookup(engine, ku_code=b.ku_code, obec_code=b.obec_code, category=vk)
    if ref is None:
        print("  MF rent map: no data (run app.ingest.mf_rent_map)")
    else:
        print(
            f"  MF rent map ({ref.unit_kind} {ref.unit_name}, VK{vk}, period to {ref.period_end}): "
            f"reference {ref.reference} Kč/m² (95 % {ref.band_low}–{ref.band_high}), "
            f"coverage {ref.coverage}/5, raw asking {ref.raw_min}–{ref.raw_max}"
        )
        print(
            f"  expected with features: {ref.expected_per_m2(features)} Kč/m² "
            f"(surcharges +{ref.surcharge_per_m2(features)})"
        )
    print(f"  data as of {p.data_as_of}; API KN calls spent now: {client.calls}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
