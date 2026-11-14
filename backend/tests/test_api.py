import hashlib
import json
import re
import zipfile

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.deps import Services
from app.api.protection import DisabledAttestation, RateLimiter
from app.config import Settings
from app.ingest import mf_rent_map, ruian_addresses
from app.main import create_app
from tests.api_kn_fake import FakeApiKn
from tests.conftest import FIXTURES
from tests.mf_factory import build

REG = FIXTURES / "registers"
PII_KEYS = re.compile(r'"(rc|jmeno|prijmeni|datumNarozeni|titulPred|titulZa|ulice|psc)"')


def registers_handler(request: httpx.Request) -> httpx.Response:
    if request.method == "GET" and "/ekonomicke-subjekty/" in request.url.path:
        ico = request.url.path.rsplit("/", 1)[-1]
        f = REG / f"ares_{ico}.json"
        return httpx.Response(200, content=f.read_bytes()) if f.exists() else httpx.Response(404)
    if request.method == "POST" and "isir" in str(request.url):
        ico = re.search(rb"<ic>(\d+)</ic>", request.content).group(1).decode()
        return httpx.Response(200, content=(REG / f"isir_{ico}.xml").read_bytes())
    return httpx.Response(500)


@pytest.fixture
def data(db, tmp_path):
    path = build(tmp_path / "mf.xlsx")
    mf_rent_map.load(
        db, mf_rent_map.parse_workbook(path), hashlib.sha256(path.read_bytes()).hexdigest(), None
    )
    z = tmp_path / "adr.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for f in (FIXTURES / "ruian").glob("*_ADR.csv"):
            zf.write(f, f"CSV/{f.name}")
    ruian_addresses.load(db, z, "20261031", {554782, 582786})
    return db


def make_client(db, fake_kn=None, **protection) -> tuple[TestClient, FakeApiKn, list[str]]:
    fake_kn = fake_kn or FakeApiKn()
    settings = Settings(_env_file=None, cuzk_api_key="test-key")
    for k, v in protection.items():
        setattr(settings.protection, k, v)
    reg_calls: list[str] = []

    def reg(request):
        reg_calls.append(f"{request.method} {request.url.host}")
        return registers_handler(request)

    svc = Services(
        settings=settings,
        engine=db,
        http_kn=fake_kn.client().http,
        http_registers=httpx.Client(transport=httpx.MockTransport(reg)),
        attestation=DisabledAttestation(),
        limiter=RateLimiter(db),
    )
    client = TestClient(create_app(settings, svc))
    return client, fake_kn, reg_calls


BASE = {"ruian_code": 21951977, "disposition": "2+kk", "area_m2": 55}


def post(client, **body):
    return client.post("/v1/report", json=BASE | body)


def test_suggest(data):
    client, *_ = make_client(data)
    with client:
        r = client.get("/v1/address/suggest", params={"q": "u krizku 14"})
        assert r.status_code == 200
        top = r.json()[0]
        assert top["ruian_code"] == 21951977
        assert top["label"] == "U křížku 1403/4, Nusle, Praha 4"
        assert 50.0 < top["lat"] < 50.1
        assert client.get("/v1/address/suggest", params={"q": "ab"}).status_code == 422


def test_report_green_company_without_isir_call(data):
    client, fake, reg_calls = make_client(data)
    with client:
        # Nusle VK2 synthetic reference 440 + lift 45 = 485 Kč/m² → 55 m² ≈ 26 675 Kč
        r = post(
            client,
            unit_number=24,
            rent_czk=26_700,
            landlord_ico="45274649",
            features={"lift": True},
        )
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["overall"] == "green"
    assert rep["price"]["verdict"] == "typical"
    assert rep["price"]["expected_per_m2"] == 485
    assert (rep["price"]["typical_low_per_m2"], rep["price"]["typical_high_per_m2"]) == (412, 558)
    assert rep["property"]["check_level"] == "unit"
    assert rep["property"]["unit_use_name"] == "byt"
    assert rep["property"]["kn_deeplink"].endswith("typ=Jednotka&id=24136425010")
    assert rep["landlord"]["name"] == "ČEZ, a. s."
    assert rep["landlord"]["insolvency"] == "none"
    assert rep["address"]["status"] == "unknown"  # no flood data loaded
    assert reg_calls == ["GET ares.gov.cz"]  # ARES says never in ISIR → no SOAP call


def test_report_red_cheap_scam_and_insolvency(data):
    client, *_ = make_client(data)
    with client:
        r = post(
            client,
            unit_number=24,
            rent_czk=12_000,
            landlord_ico="01493248",
            answers={"deposit_before_viewing": True, "owner_abroad": False},
        )
    rep = r.json()
    assert rep["overall"] == "red"
    assert rep["price"]["verdict"] == "far_below"
    assert rep["scam_flags"]["flags"] == ["deposit_before_viewing", "price_far_below_reference"]
    assert rep["landlord"]["insolvency"] == "active"
    assert rep["landlord"]["insolvency_stage"] == "KONKURS"
    assert "insolvency_in_progress" in rep["landlord"]["signals"]
    assert not PII_KEYS.search(r.text)


def test_building_level_without_unit(data):
    client, fake, _ = make_client(data)
    with client:
        rep = post(client, rent_czk=24_000).json()
    assert rep["property"]["check_level"] == "building"
    assert rep["property"]["hints"] == ["ask_unit_number"]
    assert rep["property"]["status"] == "green"
    assert fake.requests == ["/Stavby/AdresniMisto/21951977"]


def test_scam_unknown_without_answers_green_with_no_answers(data):
    client, *_ = make_client(data)
    with client:
        skipped = post(client, rent_czk=24_200).json()["scam_flags"]
        answered_no = post(client, rent_czk=24_200, answers={"owner_abroad": False}).json()
    assert skipped == {"status": "unknown", "flags": []}
    assert answered_no["scam_flags"] == {"status": "green", "flags": []}


def test_unit_number_withheld_alone_is_yellow(data):
    client, *_ = make_client(data)
    with client:
        rep = post(client, rent_czk=24_200, answers={"unit_number_withheld": True}).json()
    assert rep["scam_flags"] == {"status": "yellow", "flags": ["unit_number_withheld"]}
    assert rep["overall"] == "yellow"


def test_overpriced_alone_caps_overall_at_yellow(data):
    client, *_ = make_client(data)
    with client:
        rep = post(client, unit_number=24, rent_czk=60_000).json()
    assert rep["price"]["status"] == "red"
    assert rep["price"]["verdict"] == "far_above"
    assert rep["overall"] == "yellow"


def test_api_kn_quota_degrades_report(data):
    fake = FakeApiKn({"/Stavby/AdresniMisto/21951977": (429, None)})
    client, *_ = make_client(data, fake)
    with client:
        r = post(client, rent_czk=24_000)
    assert r.status_code == 200
    rep = r.json()
    assert rep["property"] == rep["property"] | {"available": False, "unavailable_reason": "quota"}
    assert rep["price"]["available"] is False


def test_daily_api_kn_budget(data):
    client, fake, _ = make_client(data, api_kn_daily_budget=0)
    with client:
        rep = post(client, rent_czk=24_000).json()
    assert rep["property"]["unavailable_reason"] == "quota"
    assert fake.requests == []


def test_rate_limit_per_ip(data):
    client, *_ = make_client(data, report_per_ip_per_hour=2)
    with client:
        codes = [post(client, rent_czk=24_000).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_rate_limit_keys_are_hashed(data):
    client, *_ = make_client(data)
    with client:
        post(client, rent_czk=24_000)
    with data.connect() as c:
        keys = [r[0] for r in c.execute(text("SELECT key FROM rate_limit_counter"))]
    assert all("testclient" not in k and "127.0.0.1" not in k for k in keys)


def test_validation_and_language(data):
    client, *_ = make_client(data)
    with client:
        assert post(client, rent_czk=24_000, unexpected=1).status_code == 422
        assert post(client, rent_czk=24_000, landlord_ico="123").status_code == 422
        r = client.post(
            "/v1/report", json=BASE | {"rent_czk": 24_000}, headers={"Accept-Language": "en-GB"}
        )
        assert r.json()["disclaimer"].startswith("Indicative information")


def test_openapi_contract_exposed(data):
    client, *_ = make_client(data)
    with client:
        spec = client.get("/openapi.json").json()
    assert {"/v1/report", "/v1/address/suggest", "/v1/health"} <= set(spec["paths"])
    json.dumps(spec)
