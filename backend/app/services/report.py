"""Report assembly and scoring (docs/SPEC.md §6). Stateless: nothing is persisted.

Each block degrades on its own (unavailable / unknown); the report never fails because
one source is down.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import Engine

from app.api.v1 import schemas as s
from app.clients.api_kn import ApiKnClient, ApiKnError, ApiKnQuotaExceeded
from app.clients.registers import AresClient, IsirClient, RegisterUnavailable, valid_ico
from app.config import ScoringSettings
from app.services import flood, rent_map
from app.services.property import PropertyLookup, resolve

log = logging.getLogger(__name__)

SEVERITY = {"unknown": 0, "green": 1, "yellow": 2, "red": 3}
NAHLIZENI = "https://nahlizenidokn.cuzk.gov.cz"
DISCLAIMER = {
    "cs": "Orientační informace, není právní posouzení.",
    "en": "Indicative information, not a legal assessment.",
}
SOURCES = [
    "ČÚZK – API KN, RÚIAN (CC BY 4.0)",
    "MF ČR – Cenová mapa nájemního bydlení",
    "ARES, ISIR",
    "Záplavová území, VÚV TGM, v.v.i. / MŽP (CC BY 4.0)",
]
# ZpusobyVyuzitiJednotky codes → property signal (SPEC §5.1).
UNIT_USE_SIGNAL = {
    2: "unit_not_registered_as_flat",
    3: "unit_not_registered_as_flat",
    4: "unit_not_registered_as_flat",
    5: "unit_not_registered_as_flat",
    8: "unit_not_registered_as_flat",
    6: "unit_unfinished",
    7: "unit_is_group",
    9: "unit_is_group",
}


def worst(*statuses: s.Status) -> s.Status:
    return max(statuses, key=SEVERITY.__getitem__) if statuses else "unknown"


@dataclass
class ReportDeps:
    engine: Engine
    api_kn: ApiKnClient
    ares: AresClient
    isir: IsirClient
    scoring: ScoringSettings
    # Returns False when today's API KN budget is spent (global protection, SPEC §4.2).
    api_kn_budget_ok: Callable[[], bool] = lambda: True
    on_api_kn_calls: Callable[[int], None] = lambda n: None


def build_report(req: s.ReportRequest, deps: ReportDeps, lang: str = "cs") -> s.ReportResponse:
    prop_lookup, prop_block = _property(req, deps)
    price = _price(req, deps, prop_lookup)
    landlord = _landlord(req.landlord_ico, deps) if req.landlord_ico else None
    address = _address(req, deps, prop_lookup)
    scam = _scam(req, price, deps.scoring)

    # Overall = worst block; "overpriced" alone is information → capped at yellow.
    price_for_overall = "yellow" if price.verdict == "far_above" else price.status
    overall = worst(
        price_for_overall,
        prop_block.status,
        landlord.status if landlord else "unknown",
        address.status,
        scam.status,
    )
    return s.ReportResponse(
        overall=overall,
        price=price,
        property=prop_block,
        landlord=landlord,
        address=address,
        scam_flags=scam,
        disclaimer=DISCLAIMER.get(lang, DISCLAIMER["cs"]),
        sources=SOURCES,
    )


# ---------------- property ----------------


def _property(
    req: s.ReportRequest, deps: ReportDeps
) -> tuple[PropertyLookup | None, s.PropertyBlock]:
    if not deps.api_kn_budget_ok():
        return None, s.PropertyBlock(status="unknown", available=False, unavailable_reason="quota")
    before = deps.api_kn.calls
    try:
        p = resolve(deps.api_kn, req.ruian_code, req.unit_number)
    except ApiKnQuotaExceeded:
        return None, s.PropertyBlock(status="unknown", available=False, unavailable_reason="quota")
    except ApiKnError as e:
        log.warning("API KN unavailable: %s", e)
        return None, s.PropertyBlock(
            status="unknown", available=False, unavailable_reason="service"
        )
    finally:
        deps.on_api_kn_calls(deps.api_kn.calls - before)

    if p.building is None:
        return p, s.PropertyBlock(
            status="yellow",
            available=True,
            building_found=False,
            check_level="building",
            signals=["building_not_found"],
            kn_deeplink=NAHLIZENI,
        )

    signals: list[str] = []
    status: s.Status = "green"
    if p.unit_found is False:
        signals.append("unit_not_found")
        status = "yellow"
    if p.unit and (sig := UNIT_USE_SIGNAL.get(p.unit.use_code or 1)):
        signals.append(sig)
        status = "yellow"
    active = [r for r in p.proceedings if r.in_progress]
    if any(r.type == "V" and r.scope == "unit" for r in active):
        signals.append("ownership_change_in_progress_unit")
        status = "red"
    elif active:
        signals.append("proceeding_in_progress")
        status = worst(status, "yellow")

    if p.unit:
        link = f"{NAHLIZENI}/ZobrazObjekt.aspx?typ=Jednotka&id={p.unit.id}"
    else:
        link = f"{NAHLIZENI}/ZobrazObjekt.aspx?typ=Budova&id={p.building.id}"
    return p, s.PropertyBlock(
        status=status,
        available=True,
        check_level=p.check_level,
        building_found=True,
        unit_found=p.unit_found,
        unit_use_code=p.unit.use_code if p.unit else None,
        unit_use_name=p.unit.use_name if p.unit else None,
        ku_name=p.building.ku_name,
        proceedings=[
            s.ProceedingOut(
                type=r.type,
                number=r.number,
                state=r.stav,
                received=r.received,
                scope=r.scope,
                in_progress=r.in_progress,
            )
            for r in p.proceedings
        ],
        signals=signals,
        hints=list(p.hints),
        kn_deeplink=link,
        data_as_of=p.data_as_of,
    )


# ---------------- price ----------------


def _price(req: s.ReportRequest, deps: ReportDeps, p: PropertyLookup | None) -> s.PriceBlock:
    b = p.building if p else None
    if b is None:
        return s.PriceBlock(status="unknown", available=False)
    vk = rent_map.size_category(req.disposition)
    ref = rent_map.lookup(deps.engine, ku_code=b.ku_code, obec_code=b.obec_code, category=vk)
    if ref is None:
        return s.PriceBlock(status="unknown", available=False)

    f = rent_map.Features(**req.features.model_dump())
    expected = ref.expected_per_m2(f)
    asking = req.rent_czk / req.area_m2
    ratio = asking / expected
    sc = deps.scoring
    if ratio < sc.price_red_below:
        verdict, status = "far_below", "red"
    elif ratio < sc.price_yellow_below:
        verdict, status = "below", "yellow"
    elif ratio <= sc.price_yellow_above:
        verdict, status = "typical", "green"
    elif ratio <= sc.price_red_above:
        verdict, status = "above", "yellow"
    else:
        verdict, status = "far_above", "red"
    limited = ref.coverage <= sc.price_low_coverage_max
    if limited and status == "red":
        status = "yellow"

    return s.PriceBlock(
        status=status,
        available=True,
        verdict=verdict,
        asking_per_m2=round(asking, 1),
        expected_per_m2=expected,
        reference_per_m2=ref.reference_new_build if f.new_build else ref.reference,
        surcharge_per_m2=ref.surcharge_per_m2(f),
        band_low=ref.band_low,
        band_high=ref.band_high,
        raw_min=ref.raw_min,
        raw_median=ref.raw_median,
        raw_max=ref.raw_max,
        coverage=ref.coverage,
        limited_data=limited,
        ratio=round(ratio, 3),
        unit_name=ref.unit_name,
        unit_kind=ref.unit_kind,
        size_category=vk,
        period_end=ref.period_end,
    )


# ---------------- landlord ----------------


def _landlord(ico: str, deps: ReportDeps) -> s.LandlordBlock:
    if not valid_ico(ico):
        return s.LandlordBlock(status="yellow", ico=ico, found=False, signals=["ico_invalid"])
    try:
        c = deps.ares.company(ico)
    except RegisterUnavailable as e:
        log.warning("%s", e)
        return s.LandlordBlock(status="unknown", ico=ico, found=False)
    if c is None:
        return s.LandlordBlock(status="yellow", ico=ico, found=False, signals=["ico_not_found"])

    block = s.LandlordBlock(
        status="green",
        ico=ico,
        found=True,
        name=c.name,
        natural_person=c.natural_person,
        active=c.active,
    )
    if not c.active:
        block.status = "red"
        block.signals.append("company_not_active")
    if c.natural_person:
        return block  # MVP: no ISIR for natural persons (personal data)

    if c.isir_source_state == "NEEXISTUJICI":
        block.insolvency = "none"  # never in ISIR per ARES; skip the SOAP call
        return block
    ins = deps.isir.check_company(ico)
    block.insolvency = ins.status
    if ins.status == "active":
        block.status = "red"
        block.signals.append("insolvency_in_progress")
        block.insolvency_stage = ins.proceedings[0].get("druhStavKonkursu")
    return block


# ---------------- address ----------------


def _address(req: s.ReportRequest, deps: ReportDeps, p: PropertyLookup | None) -> s.AddressBlock:
    point = p.building.point_5514 if p and p.building else None
    point = point or flood.point_for_address(deps.engine, req.ruian_code)
    if point is None:
        return s.AddressBlock(status="unknown", flood_zone=None)
    fc = flood.check_point(deps.engine, *point, near_m=deps.scoring.flood_near_m)
    status: s.Status = {
        None: "unknown",
        "none": "green",
        "near": "yellow",
        "q100": "yellow",
        "active": "yellow",
    }[fc.zone]
    return s.AddressBlock(
        status=status, flood_zone=fc.zone, distance_m=fc.distance_m, data_version=fc.data_version
    )


# ---------------- scam flags ----------------


def _scam(req: s.ReportRequest, price: s.PriceBlock, sc: ScoringSettings) -> s.ScamBlock:
    flags = [q for q, yes in req.answers.items() if yes]
    if price.verdict == "far_below" and not price.limited_data:
        flags.append("price_far_below_reference")
    if not flags:
        return s.ScamBlock(status="green", flags=[])
    status = "yellow" if all(f in sc.yellow_flags for f in flags) else "red"
    return s.ScamBlock(status=status, flags=flags)
