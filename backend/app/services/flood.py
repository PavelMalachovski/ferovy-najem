"""Flood-zone check for a point (docs/SPEC.md §5.4). Indicative only."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import Engine, text

FloodZone = Literal["none", "near", "q100", "active"]


@dataclass(frozen=True)
class FloodCheck:
    zone: FloodZone | None  # None = no flood data loaded
    distance_m: int | None
    data_version: str | None


_SQL = text(
    """
    WITH p AS (SELECT ST_SetSRID(ST_MakePoint(:x, :y), 5514) AS g)
    SELECT f.zone_type, min(ST_Distance(f.geom, p.g)) AS d
    FROM flood_zone f, p
    WHERE ST_DWithin(f.geom, p.g, :near)
    GROUP BY f.zone_type
    """
)


def check_point(engine: Engine, x: float, y: float, near_m: int) -> FloodCheck:
    with engine.connect() as c:
        version = c.execute(
            text("SELECT version FROM ingest_state WHERE source = 'flood_zones'")
        ).scalar()
        if version is None:
            return FloodCheck(None, None, None)
        dist = {r.zone_type: r.d for r in c.execute(_SQL, {"x": x, "y": y, "near": near_m})}
    if dist.get("active") == 0:
        return FloodCheck("active", 0, version)
    if dist.get("q100") == 0:
        return FloodCheck("q100", 0, version)
    if dist:
        return FloodCheck("near", round(min(dist.values())), version)
    return FloodCheck("none", None, version)


def point_for_address(engine: Engine, ruian_code: int) -> tuple[float, float] | None:
    """Fallback when API KN gave no definiční bod: our RÚIAN copy (Praha/Brno)."""
    with engine.connect() as c:
        row = c.execute(
            text(
                "SELECT ST_X(g) x, ST_Y(g) y FROM (SELECT ST_Transform(geom, 5514) g "
                "FROM address_point WHERE ruian_code = :r) t"
            ),
            {"r": ruian_code},
        ).first()
    return (row.x, row.y) if row else None
