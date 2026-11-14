"""Ingest RÚIAN address points for autocomplete (docs/SPEC.md §5).

Source: ČÚZK monthly CSV export, one file per obec, cp1250, ';'-separated,
coordinates in S-JTSK (positive Y/X). Licence CC BY 4.0.

Usage:
    python -m app.ingest.ruian_addresses                  # obce from config (Praha, Brno)
    python -m app.ingest.ruian_addresses --obec 554782
    python -m app.ingest.ruian_addresses --all
    python -m app.ingest.ruian_addresses --file export.zip --date 20261031

Idempotent: same export + same obce → skipped. Reloading replaces the selected obce only.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import logging
import re
import sys
import tempfile
import zipfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx
from sqlalchemy import Engine, text

from app.config import get_settings
from app.db import get_engine

log = logging.getLogger(__name__)

SOURCE = "ruian_adr"
HEADER = [
    "Kód ADM",
    "Kód obce",
    "Název obce",
    "Kód MOMC",
    "Název MOMC",
    "Kód obvodu Prahy",
    "Název obvodu Prahy",
    "Kód části obce",
    "Název části obce",
    "Kód ulice",
    "Název ulice",
    "Typ SO",
    "Číslo domovní",
    "Číslo orientační",
    "Znak čísla orientačního",
    "PSČ",
    "Souřadnice Y",
    "Souřadnice X",
    "Platí Od",
]
FILE_RE = re.compile(r"_OB_(\d+)_ADR\.csv$")
COLUMNS = (
    "ruian_code",
    "obec_code",
    "obec_name",
    "momc_name",
    "cast_obce_name",
    "ulice_name",
    "so_type",
    "cislo_domovni",
    "cislo_orientacni",
    "znak_co",
    "psc",
    "label",
    "x5514",
    "y5514",
    "valid_from",
)


class RuianFormatError(ValueError):
    pass


@dataclass
class ParseStats:
    rows: int = 0
    skipped_no_coords: int = 0


def make_label(r: dict[str, str]) -> str:
    """Czech-style one-line address, e.g. 'U křížku 1403/4, Nusle, Praha 4'."""
    number = r["Číslo domovní"]
    if r["Typ SO"] == "č.ev.":
        number = f"č.ev. {number}"
    if r["Číslo orientační"]:
        number += f"/{r['Číslo orientační']}{r['Znak čísla orientačního']}"
    street = r["Název ulice"]
    part = r["Název části obce"]
    city = r["Název obvodu Prahy"] or r["Název obce"]
    if street:
        head = f"{street} {number}"
        parts = [head] + ([part] if part and part not in (city, r["Název obce"]) else [])
    else:
        parts = [f"{part} {number}"]
    return ", ".join([*parts, city])


def parse_csv(data: bytes, stats: ParseStats) -> Iterator[tuple]:
    reader = csv.DictReader(io.StringIO(data.decode("cp1250")), delimiter=";")
    if reader.fieldnames != HEADER:
        raise RuianFormatError(f"unexpected header: {reader.fieldnames}")
    for r in reader:
        if not r["Souřadnice Y"] or not r["Souřadnice X"]:
            stats.skipped_no_coords += 1
            continue
        stats.rows += 1
        yield (
            int(r["Kód ADM"]),
            int(r["Kód obce"]),
            r["Název obce"],
            r["Název MOMC"] or None,
            r["Název části obce"] or None,
            r["Název ulice"] or None,
            r["Typ SO"],
            int(r["Číslo domovní"]),
            int(r["Číslo orientační"]) if r["Číslo orientační"] else None,
            r["Znak čísla orientačního"] or None,
            r["PSČ"] or None,
            make_label(r),
            # S-JTSK export uses positive Y/X; EPSG:5514 is (x, y) = (-Y, -X).
            -float(r["Souřadnice Y"]),
            -float(r["Souřadnice X"]),
            r["Platí Od"][:10] or None,
        )


def iter_obec_files(zf: zipfile.ZipFile, obce: set[int] | None) -> Iterator[tuple[int, bytes]]:
    for name in sorted(zf.namelist()):
        m = FILE_RE.search(name)
        if m and (obce is None or int(m.group(1)) in obce):
            yield int(m.group(1)), zf.read(name)


def load(engine: Engine, zip_path: Path, version: str, obce: set[int] | None) -> ParseStats | None:
    """Load selected obce (None = all). Returns None if this export was already loaded."""
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    scope = "all" if obce is None else ",".join(map(str, sorted(obce)))
    fingerprint = f"{digest}:{scope}"
    with engine.connect() as c:
        current = c.execute(
            text("SELECT fingerprint FROM ingest_state WHERE source = :s"), {"s": SOURCE}
        ).scalar()
    if current == fingerprint:
        return None

    stats = ParseStats()
    found: set[int] = set()
    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        cur.execute(
            "CREATE TEMP TABLE stage_adr ("
            "ruian_code bigint, obec_code int, obec_name text, momc_name text, "
            "cast_obce_name text, ulice_name text, so_type text, cislo_domovni int, "
            "cislo_orientacni int, znak_co text, psc text, label text, "
            "x5514 double precision, y5514 double precision, valid_from date) ON COMMIT DROP"
        )
        with (
            zipfile.ZipFile(zip_path) as zf,
            cur.copy(f"COPY stage_adr ({', '.join(COLUMNS)}) FROM STDIN") as copy,
        ):
            for obec, data in iter_obec_files(zf, obce):
                found.add(obec)
                for row in parse_csv(data, stats):
                    copy.write_row(row)
        if obce is not None and (missing := obce - found):
            raise RuianFormatError(f"obce not in export: {sorted(missing)}")
        if obce is None:
            cur.execute("TRUNCATE address_point")
        else:
            cur.execute("DELETE FROM address_point WHERE obec_code = ANY(%s)", (sorted(obce),))
        cur.execute(
            "INSERT INTO address_point (ruian_code, obec_code, obec_name, momc_name, "
            "cast_obce_name, ulice_name, so_type, cislo_domovni, cislo_orientacni, znak_co, "
            "psc, label, geom, valid_from) "
            "SELECT ruian_code, obec_code, obec_name, momc_name, cast_obce_name, ulice_name, "
            "so_type, cislo_domovni, cislo_orientacni, znak_co, psc, label, "
            "ST_Transform(ST_SetSRID(ST_MakePoint(x5514, y5514), 5514), 4326), valid_from "
            "FROM stage_adr"
        )
        cur.execute(
            "INSERT INTO ingest_state (source, version, fingerprint, row_count) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (source) DO UPDATE SET "
            "version = EXCLUDED.version, fingerprint = EXCLUDED.fingerprint, "
            "row_count = EXCLUDED.row_count, loaded_at = now()",
            (SOURCE, version, fingerprint, stats.rows),
        )
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()
    return stats


def last_export_dates(today: dt.date, n: int = 2) -> Iterable[str]:
    """Exports are dated the last day of a month; try the latest ones first."""
    d = today.replace(day=1)
    for _ in range(n):
        d -= dt.timedelta(days=1)
        yield d.strftime("%Y%m%d")
        d = d.replace(day=1)


def download(client: httpx.Client, url_template: str, dest: Path) -> str:
    for date in last_export_dates(dt.date.today()):
        url = url_template.format(date=date)
        with client.stream("GET", url) as r:
            if r.status_code == 404:
                continue
            r.raise_for_status()
            with dest.open("wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
        log.info("downloaded %s", url)
        return date
    raise RuntimeError("no RÚIAN export found for the last two months")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Ingest RÚIAN address points")
    scope = ap.add_mutually_exclusive_group()
    scope.add_argument("--obec", type=lambda s: {int(x) for x in s.split(",")})
    scope.add_argument("--all", action="store_true")
    ap.add_argument("--file", type=Path, help="local export zip (skips download)")
    ap.add_argument("--date", help="export date YYYYMMDD (with --file)")
    args = ap.parse_args(argv)
    settings = get_settings()
    obce = None if args.all else (args.obec or set(settings.ruian_obce))

    with tempfile.TemporaryDirectory() as tmp:
        if args.file:
            path, version = args.file, args.date or args.file.stem
        else:
            path = Path(tmp) / "adr.zip"
            with httpx.Client(timeout=120, follow_redirects=True) as client:
                version = download(client, settings.ruian_csv_url_template, path)
        stats = load(get_engine(), path, version, obce)

    if stats is None:
        log.info("export %s already loaded for this scope, nothing to do", version)
    else:
        log.info(
            "loaded %d addresses (%d skipped without coordinates) from export %s",
            stats.rows,
            stats.skipped_no_coords,
            version,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
