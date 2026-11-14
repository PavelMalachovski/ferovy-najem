"""Address → building → unit → proceedings via API KN (docs/SPEC.md §5.1).

Facts only; scoring/colours happen in the report layer (M2).
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field
from typing import Literal

from app.clients.api_kn import ApiKnClient, Rizeni, RizeniDef

log = logging.getLogger(__name__)

RIZENI_FINISHED = "Řízení bylo ukončeno"
KNOWN_STAV = {"U nemovitostí byla vyznačena plomba", RIZENI_FINISHED}


@dataclass(frozen=True)
class Building:
    id: int
    cisla_domovni: list[int]
    use: str | None  # e.g. "bytový dům"
    obec_code: int | None
    obec_name: str | None
    ku_code: int | None
    ku_name: str | None
    lv_number: int | None
    unit_count: int
    point_5514: tuple[float, float] | None  # definiční bod (x, y) in S-JTSK


@dataclass(frozen=True)
class Unit:
    id: int
    cislo_jednotky: int  # as API returns it: cisloDomovni * 10000 + unit
    type_code: int | None
    type_name: str | None
    use_code: int | None
    use_name: str | None
    lv_number: int | None


@dataclass(frozen=True)
class Proceeding:
    id: int
    type: str  # V, Z, PGP, PD, ZPV
    number: str  # e.g. "V-75142/2026-101"
    stav: str | None
    received: dt.datetime | None
    scope: Literal["unit", "building"]
    in_progress: bool


@dataclass
class PropertyLookup:
    ruian_code: int
    building: Building | None
    check_level: Literal["unit", "building"]
    unit_number: int | None
    unit_found: bool | None
    unit: Unit | None
    proceedings: list[Proceeding] = field(default_factory=list)
    hints: list[Literal["ask_unit_number", "whole_house"]] = field(default_factory=list)
    data_as_of: dt.datetime | None = None


def encoded_unit_numbers(cisla_domovni: list[int], unit_number: int) -> set[int]:
    """API KN encodes číslo jednotky as cisloDomovni * 10000 + unit (1403/24 → 14030024)."""
    return {cd * 10000 + unit_number for cd in cisla_domovni}


def resolve(client: ApiKnClient, ruian_code: int, unit_number: int | None = None) -> PropertyLookup:
    fetched = client.stavba_by_adresni_misto(ruian_code)
    if fetched is None:
        return PropertyLookup(
            ruian_code=ruian_code,
            building=None,
            check_level="building",
            unit_number=unit_number,
            unit_found=None,
            unit=None,
        )
    s = fetched.data
    ku = s.parcely[0].katastralni_uzemi if s.parcely else None
    building = Building(
        id=s.id,
        cisla_domovni=s.cisla_domovni,
        use=s.zpusob_vyuziti.nazev if s.zpusob_vyuziti else None,
        obec_code=s.obec.kod if s.obec else None,
        obec_name=s.obec.nazev if s.obec else None,
        ku_code=ku.kod if ku else None,
        ku_name=ku.nazev if ku else None,
        lv_number=s.lv.cislo if s.lv else None,
        unit_count=len(s.jednotky),
        point_5514=(s.definicni_bod.x, s.definicni_bod.y) if s.definicni_bod else None,
    )
    result = PropertyLookup(
        ruian_code=ruian_code,
        building=building,
        check_level="building",
        unit_number=unit_number,
        unit_found=None,
        unit=None,
        data_as_of=fetched.as_of,
    )
    plomby: list[tuple[Literal["unit", "building"], RizeniDef]] = [
        ("building", r) for r in s.rizeni_plomby
    ]

    if not s.jednotky:
        result.hints.append("whole_house")
    elif unit_number is None:
        result.hints.append("ask_unit_number")
    else:
        wanted = encoded_unit_numbers(s.cisla_domovni, unit_number)
        match = next((j for j in s.jednotky if j.cislo_jednotky in wanted), None)
        result.check_level = "unit"
        result.unit_found = match is not None
        if match:
            u = client.jednotka(match.id)
            if u is not None:
                j = u.data
                result.unit = Unit(
                    id=j.id,
                    cislo_jednotky=j.cislo_jednotky,
                    type_code=j.typ_jednotky.kod if j.typ_jednotky else None,
                    type_name=j.typ_jednotky.nazev if j.typ_jednotky else None,
                    use_code=j.zpusob_vyuziti.kod if j.zpusob_vyuziti else None,
                    use_name=j.zpusob_vyuziti.nazev if j.zpusob_vyuziti else None,
                    lv_number=j.lv.cislo if j.lv else None,
                )
                plomby += [("unit", r) for r in j.rizeni_plomby]
            else:
                result.unit_found = False

    seen: set[int] = set()
    for scope, ref in plomby:
        if ref.id in seen:
            continue
        seen.add(ref.id)
        detail = client.rizeni(ref.id)
        result.proceedings.append(_proceeding(scope, ref, detail.data if detail else None))
    return result


def _proceeding(scope: Literal["unit", "building"], ref: RizeniDef, r: Rizeni | None) -> Proceeding:
    stav = r.stav if r else None
    if stav and stav not in KNOWN_STAV:
        log.warning("unknown řízení stav text: %r (treated as in progress)", stav)
    return Proceeding(
        id=ref.id,
        type=ref.typ_rizeni,
        number=f"{ref.typ_rizeni}-{ref.poradove_cislo}/{ref.rok}-{ref.kod_pracoviste}",
        stav=stav,
        received=r.datum_prijeti if r else None,
        scope=scope,
        in_progress=stav != RIZENI_FINISHED,
    )
