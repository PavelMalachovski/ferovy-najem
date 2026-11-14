import zipfile

import pytest
from sqlalchemy import text

from app.ingest.ruian_addresses import RuianFormatError, load
from tests.conftest import FIXTURES

RUIAN = FIXTURES / "ruian"


@pytest.fixture
def export_zip(tmp_path):
    path = tmp_path / "20261031_OB_ADR_csv.zip"
    with zipfile.ZipFile(path, "w") as zf:
        for f in RUIAN.glob("*_ADR.csv"):
            zf.write(f, f"CSV/{f.name}")
    return path


def rows(db, sql, **params):
    with db.connect() as c:
        return c.execute(text(sql), params).mappings().all()


def test_loads_selected_obce_with_labels_and_coords(db, export_zip):
    stats = load(db, export_zip, "20261031", {554782})
    assert stats.rows == 4
    assert stats.skipped_no_coords == 1

    by_code = {
        r["ruian_code"]: r
        for r in rows(db, "SELECT ruian_code, label, search_text, obec_code FROM address_point")
    }
    assert set(by_code) == {21951977, 21875995, 21736936, 21691193}
    assert by_code[21951977]["label"] == "U křížku 1403/4, Nusle, Praha 4"
    assert by_code[21875995]["label"] == "Kunratice 53, Praha 4"  # no street
    assert by_code[21736936]["label"] == "Albertov č.ev. 12, Nové Město, Praha 2"
    assert by_code[21691193]["label"] == "Jelení 91/7a, Hradčany, Praha 1"
    assert by_code[21951977]["search_text"] == "u krizku 1403/4, nusle, praha 4"

    # S-JTSK → WGS84: Nusle is around 50.06 N, 14.44 E.
    lon, lat = rows(
        db, "SELECT ST_X(geom) lon, ST_Y(geom) lat FROM address_point WHERE ruian_code = 21951977"
    )[0].values()
    assert 50.05 < lat < 50.07
    assert 14.43 < lon < 14.45


def test_idempotent_and_scoped_reload(db, export_zip):
    assert load(db, export_zip, "20261031", {554782, 582786}).rows == 6
    assert load(db, export_zip, "20261031", {554782, 582786}) is None  # same export + scope
    # Reloading Praha only must keep Brno.
    assert load(db, export_zip, "20261031", {554782}).rows == 4
    counts = rows(db, "SELECT obec_code, count(*) n FROM address_point GROUP BY 1 ORDER BY 1")
    assert [(r["obec_code"], r["n"]) for r in counts] == [(554782, 4), (582786, 2)]


def test_brno_label_uses_part_and_city(db, export_zip):
    load(db, export_zip, "20261031", {582786})
    labels = {r["label"] for r in rows(db, "SELECT label FROM address_point")}
    assert "Buková 388/24, Žebětín, Brno" in labels


def test_missing_obec_fails_without_changes(db, export_zip):
    with pytest.raises(RuianFormatError, match="not in export"):
        load(db, export_zip, "20261031", {554782, 999999})
    assert rows(db, "SELECT count(*) n FROM address_point")[0]["n"] == 0


def test_trigram_search_without_diacritics(db, export_zip):
    load(db, export_zip, "20261031", {554782, 582786})
    hits = rows(
        db,
        "SELECT ruian_code FROM address_point "
        "WHERE search_text % lower(f_unaccent(:q)) "
        "ORDER BY similarity(search_text, lower(f_unaccent(:q))) DESC LIMIT 1",
        q="u krizku 1403",
    )
    assert hits[0]["ruian_code"] == 21951977
