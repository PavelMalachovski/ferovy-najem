import json

import httpx
import pytest
from sqlalchemy import text

from app.clients.api_kn import NullCache, PgCache
from app.clients.registers import (
    AresClient,
    IsirClient,
    RegisterUnavailable,
    parse_ares,
    parse_isir,
    valid_ico,
)
from tests.conftest import FIXTURES

REG = FIXTURES / "registers"


def ares_json(ico: str) -> dict:
    return json.loads((REG / f"ares_{ico}.json").read_text(encoding="utf-8"))


def test_valid_ico():
    assert valid_ico("45274649")
    assert valid_ico("01493248")
    assert not valid_ico("45274648")
    assert not valid_ico("1234567")
    assert not valid_ico("abcdefgh")


def test_parse_ares_company():
    c = parse_ares(ares_json("45274649"))
    assert (c.name, c.legal_form, c.natural_person, c.active) == ("ČEZ, a. s.", "121", False, True)
    assert c.isir_source_state == "NEEXISTUJICI"
    assert parse_ares(ares_json("01493248")).isir_source_state == "AKTIVNI"


def test_parse_ares_natural_person_drops_name():
    synthetic = {
        "ico": "12345679",
        "obchodniJmeno": "Jan Novák",
        "pravniForma": "101",
        "datumVzniku": "2010-01-01",
        "seznamRegistraci": {"stavZdrojeRos": "AKTIVNI"},
    }
    c = parse_ares(synthetic)
    assert c.natural_person is True
    assert c.name is None


def test_parse_ares_unknown_form_treated_as_person():
    assert parse_ares({"ico": "12345679", "obchodniJmeno": "X"}).natural_person is True


def test_parse_isir_active_whitelists_fields():
    ins = parse_isir((REG / "isir_01493248.xml").read_bytes(), "01493248")
    assert ins.status == "active"
    p = ins.proceedings[0]
    assert p["druhStavKonkursu"] == "KONKURS"
    assert set(p) == {
        "druhStavKonkursu",
        "bcVec",
        "rocnik",
        "cisloSenatu",
        "nazevOrganizace",
        "datumPmZahajeniUpadku",
        "datumPmUkonceniUpadku",
        "urlDetailRizeni",
    }  # no address, name or personal fields


def test_parse_isir_empty_and_error():
    assert parse_isir((REG / "isir_45274649.xml").read_bytes(), "45274649").status == "none"
    err = (
        b'<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>'
        b'<ns2:getIsirWsCuzkDataResponse xmlns:ns2="http://isirws.cca.cz/types/">'
        b"<stav><kodChyby>WS4</kodChyby></stav></ns2:getIsirWsCuzkDataResponse>"
        b"</soap:Body></soap:Envelope>"
    )
    assert parse_isir(err, "45274649").status == "unknown"


def mock(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_ares_client_404_and_errors():
    client = AresClient(mock(lambda r: httpx.Response(404)), NullCache())
    assert client.company("00000019") is None
    client = AresClient(mock(lambda r: httpx.Response(503)), NullCache())
    with pytest.raises(RegisterUnavailable):
        client.company("45274649")


def test_ares_cache_holds_no_person_name(db):
    calls = []

    def handler(r):
        calls.append(r.url.path)
        return httpx.Response(
            200,
            json={"ico": "12345679", "obchodniJmeno": "Jan Novák", "pravniForma": "101"},
        )

    client = AresClient(mock(handler), PgCache(db, prefix="ares:"))
    assert client.company("12345679").name is None
    assert client.company("12345679").name is None
    assert len(calls) == 1
    with db.connect() as c:
        body = c.execute(text("SELECT body::text FROM external_cache")).scalar()
    assert "Novák" not in body


def test_isir_client_network_error_is_unknown_and_not_cached(db):
    def boom(r):
        raise httpx.ConnectError("down")

    client = IsirClient(mock(boom), PgCache(db, prefix="isir:"))
    assert client.check_company("45274649").status == "unknown"
    with db.connect() as c:
        assert c.execute(text("SELECT count(*) FROM external_cache")).scalar() == 0


def test_isir_client_caches_result(db):
    calls = []

    def handler(r):
        calls.append(1)
        return httpx.Response(200, content=(REG / "isir_01493248.xml").read_bytes())

    client = IsirClient(mock(handler), PgCache(db, prefix="isir:"))
    assert client.check_company("01493248").status == "active"
    assert client.check_company("01493248").proceedings[0]["druhStavKonkursu"] == "KONKURS"
    assert len(calls) == 1
