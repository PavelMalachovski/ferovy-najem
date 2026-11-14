import datetime as dt
import hashlib

import pytest
from sqlalchemy import text

from app.ingest.mf_rent_map import RentMapFormatError, load, parse_workbook
from tests.mf_factory import build


def test_parse_values_units_and_categories(tmp_path):
    rm = parse_workbook(build(tmp_path / "m.xlsx"))
    assert rm.period_end == dt.date(2026, 9, 30)
    assert len(rm.values) == 3 * 4
    nusle_vk2 = next(v for v in rm.values if v["unit_code"] == 728161 and v["size_category"] == 2)
    assert nusle_vk2["unit_kind"] == "ku"
    assert nusle_vk2["unit_name"] == "Nusle"
    assert nusle_vk2["reference"] == 440
    assert (nusle_vk2["band_low"], nusle_vk2["band_high"]) == (430, 450)
    kalenice = next(v for v in rm.values if v["unit_code"] == 536946)
    assert kalenice["unit_kind"] == "obec"
    assert kalenice["unit_name"] == "Kalenice"


def test_parse_surcharges(tmp_path):
    rm = parse_workbook(build(tmp_path / "m.xlsx"))
    by_key = {(s["new_build"], s["size_category"]): s for s in rm.surcharges}
    assert len(by_key) == 8
    assert by_key[(False, 3)]["lift"] == 48
    assert by_key[(False, 3)]["furnished"] == 27
    assert by_key[(True, 1)]["garage"] == 36


def test_rejects_invariant_violation(tmp_path):
    with pytest.raises(RentMapFormatError, match="band"):
        parse_workbook(build(tmp_path / "m.xlsx", broken_band=True))


def test_rejects_missing_period(tmp_path):
    with pytest.raises(RentMapFormatError, match="period"):
        parse_workbook(build(tmp_path / "m.xlsx", period_text="nothing here"))


def test_load_is_idempotent(db, tmp_path):
    path = build(tmp_path / "m.xlsx")
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    rm = parse_workbook(path)
    assert load(db, rm, sha, "https://example.test/x.xlsx") is True
    assert load(db, rm, sha, "https://example.test/x.xlsx") is False
    with db.connect() as c:
        assert c.execute(text("SELECT count(*) FROM rent_map_dataset")).scalar() == 1
        assert c.execute(text("SELECT count(*) FROM rent_map_value")).scalar() == 12
        assert c.execute(text("SELECT count(*) FROM rent_map_surcharge")).scalar() == 8
