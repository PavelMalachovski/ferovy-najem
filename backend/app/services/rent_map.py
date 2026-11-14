"""MF rent map lookup and expected rent (docs/SPEC.md §5.2, §6 Scoring)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, fields
from typing import Literal

from sqlalchemy import Engine, text

Disposition = Literal["1+kk", "1+1", "2+kk", "2+1", "3+kk", "3+1", "4+kk", "4+1"]


def size_category(disposition: str) -> int:
    """MF VK: 1 = 1+kk/1+1, 2 = 2+kk/2+1, 3 = 3+kk/3+1, 4 = 4 rooms and more."""
    rooms = int(disposition.split("+", 1)[0])
    return min(max(rooms, 1), 4)


@dataclass(frozen=True)
class Features:
    lift: bool = False
    balcony: bool = False
    terrace: bool = False
    furnished: bool = False
    garage: bool = False
    new_build: bool = False


@dataclass(frozen=True)
class RentReference:
    unit_code: int
    unit_kind: Literal["ku", "obec"]
    unit_name: str
    size_category: int
    reference: int
    band_low: int
    band_high: int
    reference_new_build: int
    raw_min: int
    raw_median: int
    raw_max: int
    coverage: int
    period_end: dt.date
    surcharges: dict[bool, dict[str, int]]  # new_build → feature → Kč/m²

    def surcharge_per_m2(self, f: Features) -> int:
        table = self.surcharges.get(f.new_build, {})
        return sum(
            table.get(x.name, 0)
            for x in fields(Features)
            if x.name != "new_build" and getattr(f, x.name)
        )

    def expected_per_m2(self, f: Features) -> int:
        base = self.reference_new_build if f.new_build else self.reference
        return base + self.surcharge_per_m2(f)


_VALUE_SQL = text(
    """
    WITH ds AS (
        SELECT id, period_end FROM rent_map_dataset ORDER BY period_end DESC, loaded_at DESC LIMIT 1
    )
    SELECT v.*, ds.period_end
    FROM rent_map_value v JOIN ds ON v.dataset_id = ds.id
    WHERE v.size_category = :vk
      AND ((v.unit_kind = 'ku' AND v.unit_code = :ku)
           OR (v.unit_kind = 'obec' AND v.unit_code = :obec))
    ORDER BY (v.unit_kind = 'ku') DESC
    LIMIT 1
    """
)


def lookup(
    engine: Engine, *, ku_code: int | None, obec_code: int | None, category: int
) -> RentReference | None:
    """k.ú. row (Praha + ORP towns) wins over the obec row (rest of CZ)."""
    with engine.connect() as c:
        v = (
            c.execute(_VALUE_SQL, {"vk": category, "ku": ku_code, "obec": obec_code})
            .mappings()
            .first()
        )
        if v is None:
            return None
        rows = c.execute(
            text(
                "SELECT new_build, balcony, terrace, furnished, garage, lift "
                "FROM rent_map_surcharge WHERE dataset_id = :d AND size_category = :vk"
            ),
            {"d": v["dataset_id"], "vk": category},
        ).mappings()
        surcharges = {r["new_build"]: {k: r[k] for k in r if k != "new_build"} for r in rows}
    return RentReference(
        unit_code=v["unit_code"],
        unit_kind=v["unit_kind"],
        unit_name=v["unit_name"],
        size_category=v["size_category"],
        reference=v["reference"],
        band_low=v["band_low"],
        band_high=v["band_high"],
        reference_new_build=v["reference_new_build"],
        raw_min=v["raw_min"],
        raw_median=v["raw_median"],
        raw_max=v["raw_max"],
        coverage=v["coverage"],
        period_end=v["period_end"],
        surcharges=surcharges,
    )
