"""Ingest VÚV TGM flood zones: Q100 and aktivní zóna (docs/SPEC.md §5.4).

Source: heis.vuv.cz "Záplavová území" shapefiles, S-JTSK EPSG:5514, CC BY 4.0
("Záplavová území, VÚV TGM, v.v.i. / MŽP"). One multipolygon per river → subdivided
into small polygons for fast point/distance queries.

Usage:
    python -m app.ingest.flood_zones
    python -m app.ingest.flood_zones --q100-file Q100.zip --active-file AZ.zip

Idempotent: same pair of archives (sha256) → skipped.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import sys
import tempfile
import zipfile
from pathlib import Path

import httpx
import pyogrio.raw
from sqlalchemy import Engine, text

from app.db import get_engine

log = logging.getLogger(__name__)

SOURCE = "flood_zones"
BASE_URL = "https://heis.vuv.cz/data/webmap/datovesady/isvs/ZaplavUzemi/"
ARCHIVES = {"q100": "E_ISVS$ZAPL_UZ100.zip", "active": "E_ISVS$ZAPL_UZAZ.zip"}
SUBDIVIDE_MAX_VERTICES = 256


class FloodFormatError(ValueError):
    pass


def read_zone_archive(zip_path: Path) -> list[tuple[str | None, bytes]]:
    """(river name, WKB) per feature from the single shapefile inside the archive."""
    with zipfile.ZipFile(zip_path) as zf:
        shps = [n for n in zf.namelist() if n.lower().endswith(".shp")]
    if len(shps) != 1:
        raise FloodFormatError(f"{zip_path.name}: expected one .shp, found {shps}")
    meta, _, geometry, fields = pyogrio.raw.read(f"/vsizip/{zip_path}/{shps[0]}", force_2d=True)
    crs = (meta.get("crs") or "").upper()
    if "5514" not in crs:
        raise FloodFormatError(f"{zip_path.name}: expected EPSG:5514, got {crs!r}")
    names = list(meta["fields"])
    river = fields[names.index("NAZ_TOK")] if "NAZ_TOK" in names else [None] * len(geometry)
    return [(r, bytes(g)) for r, g in zip(river, geometry, strict=True) if g is not None]


def load(engine: Engine, archives: dict[str, Path], version: str) -> int | None:
    fingerprint = ",".join(
        f"{k}:{hashlib.sha256(p.read_bytes()).hexdigest()}" for k, p in sorted(archives.items())
    )
    with engine.connect() as c:
        if (
            c.execute(
                text("SELECT fingerprint FROM ingest_state WHERE source = :s"), {"s": SOURCE}
            ).scalar()
            == fingerprint
        ):
            return None

    features = {zone: read_zone_archive(path) for zone, path in archives.items()}
    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        cur.execute(
            "CREATE TEMP TABLE stage_flood (zone_type text, river text, wkb bytea) ON COMMIT DROP"
        )
        with cur.copy("COPY stage_flood (zone_type, river, wkb) FROM STDIN") as copy:
            for zone, rows in features.items():
                for river, wkb in rows:
                    copy.write_row((zone, river, wkb))
        cur.execute("TRUNCATE flood_zone")
        cur.execute(
            "INSERT INTO flood_zone (zone_type, river, geom) "
            "SELECT zone_type, river, ST_SetSRID(geom, 5514) FROM ("
            "  SELECT zone_type, river, (ST_Dump(s.geom)).geom AS geom"
            "  FROM stage_flood, LATERAL ST_Subdivide("
            "    ST_CollectionExtract(ST_MakeValid(ST_GeomFromWKB(wkb)), 3), %s) AS s(geom)"
            ") parts WHERE GeometryType(geom) = 'POLYGON'",
            (SUBDIVIDE_MAX_VERTICES,),
        )
        cur.execute("SELECT count(*) FROM flood_zone")
        pieces = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO ingest_state (source, version, fingerprint, row_count) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (source) DO UPDATE SET "
            "version = EXCLUDED.version, fingerprint = EXCLUDED.fingerprint, "
            "row_count = EXCLUDED.row_count, loaded_at = now()",
            (SOURCE, version, fingerprint, pieces),
        )
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()
    cur_counts = {z: len(r) for z, r in features.items()}
    log.info("features per zone: %s → %d polygons after subdivide", cur_counts, pieces)
    return pieces


def download(client: httpx.Client, dest_dir: Path) -> tuple[dict[str, Path], str]:
    paths, versions = {}, []
    for zone, name in ARCHIVES.items():
        path = dest_dir / name.replace("$", "_")
        with client.stream("GET", BASE_URL + name) as r:
            r.raise_for_status()
            versions.append(r.headers.get("last-modified", ""))
            with path.open("wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
        log.info("downloaded %s (%d MB)", name, path.stat().st_size // 1_000_000)
        paths[zone] = path
    return paths, " / ".join(versions)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Ingest VÚV flood zones (Q100, aktivní zóna)")
    ap.add_argument("--q100-file", type=Path)
    ap.add_argument("--active-file", type=Path)
    ap.add_argument("--version", help="version label when using local files")
    args = ap.parse_args(argv)

    with tempfile.TemporaryDirectory() as tmp:
        if args.q100_file and args.active_file:
            archives = {"q100": args.q100_file, "active": args.active_file}
            version = args.version or "local"
        else:
            with httpx.Client(timeout=300, follow_redirects=True) as client:
                archives, version = download(client, Path(tmp))
        pieces = load(get_engine(), archives, version)
    if pieces is None:
        log.info("flood zones already loaded, nothing to do")
    return 0


if __name__ == "__main__":
    sys.exit(main())
