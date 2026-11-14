import hashlib

from app.ingest.mf_rent_map import load, parse_workbook
from app.services.rent_map import Features, lookup, size_category
from tests.mf_factory import build


def test_size_category():
    assert [size_category(d) for d in ("1+kk", "2+1", "3+kk", "4+1", "5+kk")] == [1, 2, 3, 4, 4]


def _load(db, tmp_path):
    path = build(tmp_path / "m.xlsx")
    load(db, parse_workbook(path), hashlib.sha256(path.read_bytes()).hexdigest(), None)


def test_ku_lookup_and_expected_rent(db, tmp_path):
    _load(db, tmp_path)
    ref = lookup(db, ku_code=728161, obec_code=554782, category=3)
    assert (ref.unit_kind, ref.unit_name, ref.reference) == ("ku", "Nusle", 430)
    assert ref.expected_per_m2(Features()) == 430
    assert ref.expected_per_m2(Features(lift=True, furnished=True)) == 430 + 48 + 27
    nb = Features(new_build=True, lift=True)
    assert ref.expected_per_m2(nb) == ref.reference_new_build + 17


def test_obec_fallback_and_missing(db, tmp_path):
    _load(db, tmp_path)
    ref = lookup(db, ku_code=111111, obec_code=536946, category=1)
    assert (ref.unit_kind, ref.unit_name) == ("obec", "Kalenice")
    assert lookup(db, ku_code=111111, obec_code=222222, category=1) is None
