"""Ingest the MF "Cenová mapa nájemního bydlení" XLSX (docs/SPEC.md §5.2).

Usage:
    python -m app.ingest.mf_rent_map                 # discover latest file on mf.gov.cz
    python -m app.ingest.mf_rent_map --url URL
    python -m app.ingest.mf_rent_map --file PATH

Idempotent: a file with an already loaded SHA-256 is skipped.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import logging
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

import httpx
import openpyxl
from sqlalchemy import Engine, insert, text

from app.config import get_settings
from app.db import get_engine
from app.ingest.tables import rent_map_dataset, rent_map_surcharge, rent_map_value

log = logging.getLogger(__name__)

INFO_SHEET = "Základní informace"
DATA_SHEET = "Cenové mapy nájemného"
META_HEADER = ["Kraj", "Katastrální území", "Obec", "Kód obce"]
BLOCK_STARTS = (4, 14, 24, 34)  # one block per size category (VK1..VK4)
BLOCK_FIELDS = (
    "reference",
    "band_low",
    "band_high",
    "reference_new_build",
    "raw_min",
    "raw_max",
    "raw_median",
    "coverage",
)
SURCHARGE_COLUMNS = {
    "balkón": "balcony",
    "terasa": "terrace",
    "vybaven": "furnished",
    "garáž": "garage",
    "výtah": "lift",
}
PERIOD_RE = re.compile(r"období\s+od\s+[\d.\s]+\s+do\s+(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})")
XLSX_LINK_RE = re.compile(r'href="([^"]*_Cenova-mapa[^"]*\.xlsx)"', re.IGNORECASE)


class RentMapFormatError(ValueError):
    """The file does not match the structure verified in SPEC §5.2."""


@dataclass(frozen=True)
class RentMap:
    period_end: dt.date
    values: list[dict]
    surcharges: list[dict]


def parse_workbook(path: Path) -> RentMap:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        if INFO_SHEET not in wb.sheetnames or DATA_SHEET not in wb.sheetnames:
            raise RentMapFormatError(f"unexpected sheets: {wb.sheetnames}")
        info_rows = [list(r) for r in wb[INFO_SHEET].iter_rows(values_only=True)]
        period_end = _parse_period_end(info_rows)
        surcharges = _parse_surcharges(info_rows)
        values = _parse_values(wb[DATA_SHEET].iter_rows(values_only=True))
    finally:
        wb.close()
    return RentMap(period_end=period_end, values=values, surcharges=surcharges)


def _parse_period_end(rows: list[list]) -> dt.date:
    for row in rows:
        for cell in row:
            if isinstance(cell, str) and (m := PERIOD_RE.search(cell)):
                d, mth, y = (int(g) for g in m.groups())
                return dt.date(y, mth, d)
    raise RentMapFormatError("data period ('z období od … do …') not found on info sheet")


def _parse_surcharges(rows: list[list]) -> list[dict]:
    out: list[dict] = []
    tables = 0
    for i, row in enumerate(rows):
        # Tables don't start in column A (real file: column C) → locate the title cell.
        col = next(
            (
                j
                for j, c in enumerate(row)
                if isinstance(c, str) and c.startswith("Přehled cen cenotvorných parametrů")
            ),
            None,
        )
        if col is None:
            continue
        tables += 1
        new_build = "novostavb" in row[col]
        header = [str(c or "") for c in rows[i + 1]]
        cols = {}
        for idx, h in enumerate(header):
            for needle, field in SURCHARGE_COLUMNS.items():
                if needle in h:
                    cols[field] = idx
        if set(cols) != set(SURCHARGE_COLUMNS.values()):
            raise RentMapFormatError(f"surcharge header incomplete: {header}")
        for vk in range(1, 5):
            r = rows[i + 1 + vk]
            if r[col] != f"VK{vk}":
                raise RentMapFormatError(f"expected VK{vk} row, got {r[col]!r}")
            out.append(
                {"new_build": new_build, "size_category": vk}
                | {f: int(r[idx]) for f, idx in cols.items()}
            )
    if tables != 2:
        raise RentMapFormatError(f"expected 2 surcharge tables, found {tables}")
    return out


def _parse_values(rows) -> list[dict]:
    header = list(next(rows))
    if header[:4] != META_HEADER or any(header[s] != "VK" for s in BLOCK_STARTS):
        raise RentMapFormatError(f"unexpected data header: {header[:15]}")
    out: list[dict] = []
    errors: list[str] = []
    for n, r in enumerate(rows, start=2):
        if r[0] is None:
            continue
        kraj, ku_name, obec_name, code = r[0], r[1], r[2], r[3]
        unit_kind = "ku" if ku_name else "obec"
        for vk, start in enumerate(BLOCK_STARTS, start=1):
            if r[start] != vk:
                errors.append(f"row {n}: VK cell {r[start]!r} != {vk}")
                continue
            v = dict(zip(BLOCK_FIELDS, (int(x) for x in r[start + 1 : start + 9]), strict=True))
            if not (v["band_low"] <= v["reference"] <= v["band_high"]):
                errors.append(f"row {n} VK{vk}: band")
            if not (v["raw_min"] <= v["raw_median"] <= v["raw_max"]):
                errors.append(f"row {n} VK{vk}: raw min/median/max")
            if not 1 <= v["coverage"] <= 5:
                errors.append(f"row {n} VK{vk}: coverage {v['coverage']}")
            out.append(
                {
                    "unit_code": int(code),
                    "unit_kind": unit_kind,
                    "kraj": kraj,
                    "unit_name": ku_name or obec_name,
                    "obec_name": obec_name,
                    "size_category": vk,
                }
                | v
            )
    if errors:
        raise RentMapFormatError(f"{len(errors)} invariant violations, e.g. {errors[:5]}")
    if not out:
        raise RentMapFormatError("no data rows")
    return out


def load(engine: Engine, rent_map: RentMap, sha256: str, source_url: str | None) -> bool:
    """Insert one dataset. Returns False if this file was already loaded."""
    with engine.begin() as c:
        exists = c.execute(
            text("SELECT 1 FROM rent_map_dataset WHERE sha256 = :s"), {"s": sha256}
        ).first()
        if exists:
            return False
        ds_id = c.execute(
            insert(rent_map_dataset)
            .values(period_end=rent_map.period_end, source_url=source_url, sha256=sha256)
            .returning(rent_map_dataset.c.id)
        ).scalar_one()
        c.execute(insert(rent_map_value), [v | {"dataset_id": ds_id} for v in rent_map.values])
        c.execute(
            insert(rent_map_surcharge), [s | {"dataset_id": ds_id} for s in rent_map.surcharges]
        )
    return True


def discover_latest_url(client: httpx.Client, page_url: str) -> str:
    """First XLSX link on the official MF download page (one page fetch, not scraping
    a listing portal)."""
    r = client.get(page_url)
    r.raise_for_status()
    m = XLSX_LINK_RE.search(r.text)
    if not m:
        raise RentMapFormatError(f"no *_Cenova-mapa*.xlsx link on {page_url}")
    return urljoin(page_url, m.group(1))


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Ingest MF rent map XLSX")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--url")
    src.add_argument("--file", type=Path)
    args = ap.parse_args(argv)
    settings = get_settings()

    with tempfile.TemporaryDirectory() as tmp:
        url = args.url
        if args.file:
            path = args.file
        else:
            with httpx.Client(timeout=60, follow_redirects=True) as client:
                url = url or discover_latest_url(client, settings.mf_rent_map_page_url)
                log.info("downloading %s", url)
                r = client.get(url)
                r.raise_for_status()
                path = Path(tmp) / "rent_map.xlsx"
                path.write_bytes(r.content)

        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        rent_map = parse_workbook(path)
        loaded = load(get_engine(), rent_map, sha, url)

    if loaded:
        log.info(
            "loaded period ending %s: %d values, %d surcharges",
            rent_map.period_end,
            len(rent_map.values),
            len(rent_map.surcharges),
        )
    else:
        log.info("already loaded (sha256 %s…), nothing to do", sha[:12])
    return 0


if __name__ == "__main__":
    sys.exit(main())
