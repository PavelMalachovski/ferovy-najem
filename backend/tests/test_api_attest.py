import base64
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.deps import Services
from app.api.protection import AppAttestProvider, RateLimiter
from app.attest.app_attest import AppAttestVerifier
from app.config import Settings
from app.main import create_app
from tests.api_kn_fake import FakeApiKn
from tests.attest_factory import APP_ID, NOW, Device
from tests.test_api import BASE, data  # noqa: F401  (fixture reuse)

b64 = lambda b: base64.b64encode(b).decode()  # noqa: E731


@pytest.fixture
def device():
    return Device()


def make(db, device, allow_unattested=False):
    settings = Settings(_env_file=None, cuzk_api_key="test-key")
    verifier = AppAttestVerifier(APP_ID, "production", root_pem=device.root_pem, now=lambda: NOW)
    svc = Services(
        settings=settings,
        engine=db,
        http_kn=FakeApiKn().client().http,
        http_registers=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404))),
        attestation=AppAttestProvider(db, verifier, "production", allow_unattested, 300),
        limiter=RateLimiter(db),
    )
    return TestClient(create_app(settings, svc))


def register(client, device):
    ch = client.post("/v1/attest/challenge").json()
    assert ch["required"] is True
    challenge = base64.b64decode(ch["challenge"])
    r = client.post(
        "/v1/attest/register",
        json={
            "key_id": b64(device.key_id),
            "attestation": b64(device.attestation(challenge)),
            "challenge": ch["challenge"],
        },
    )
    return r, ch["challenge"]


def signed_post(client, device, body: dict, *, tamper=False, assertion=None):
    raw = json.dumps(body).encode()
    assertion = assertion or device.assertion(raw)
    sent = json.dumps(body | {"rent_czk": 1}).encode() if tamper else raw
    return client.post(
        "/v1/report",
        content=sent,
        headers={
            "Content-Type": "application/json",
            "X-App-Attest-Key": b64(device.key_id),
            "X-App-Attest-Assertion": b64(assertion),
        },
    ), assertion


def test_full_flow(data, device):  # noqa: F811
    with make(data, device) as client:
        r, challenge = register(client, device)
        assert r.status_code == 204
        body = BASE | {"rent_czk": 24_000}
        r, assertion = signed_post(client, device, body)
        assert r.status_code == 200, r.text
        # Replay of the same assertion is rejected (counter did not increase).
        r, _ = signed_post(client, device, body, assertion=assertion)
        assert (r.status_code, r.json()["detail"]["code"]) == (401, "attestation_failed")
        # Body changed after signing.
        r, _ = signed_post(client, device, body, tamper=True)
        assert r.status_code == 401
        # Challenge is single-use.
        reuse = client.post(
            "/v1/attest/register",
            json={"key_id": b64(device.key_id), "attestation": b64(b"x"), "challenge": challenge},
        )
        assert reuse.json()["detail"]["code"] == "attestation_challenge_invalid"
    with data.connect() as c:
        stored = c.execute(text("SELECT key_hash, counter FROM attested_key")).one()
    assert stored.counter == 1
    assert b64(device.key_id) not in stored.key_hash  # only a hash is stored


def test_unattested_request(data, device):  # noqa: F811
    with make(data, device) as client:
        r = client.post("/v1/report", json=BASE | {"rent_czk": 24_000})
        assert (r.status_code, r.json()["detail"]["code"]) == (401, "attestation_required")
    with make(data, device, allow_unattested=True) as client:
        assert client.post("/v1/report", json=BASE | {"rent_czk": 24_000}).status_code == 200


def test_unknown_key(data, device):  # noqa: F811
    with make(data, device) as client:
        r, _ = signed_post(client, device, BASE | {"rent_czk": 24_000})
        assert r.json()["detail"]["code"] == "attestation_unknown_key"


def test_forged_attestation_rejected(data, device):  # noqa: F811
    attacker = Device()  # signed by a CA that is not the trusted root
    with make(data, device) as client:
        ch = client.post("/v1/attest/challenge").json()["challenge"]
        r = client.post(
            "/v1/attest/register",
            json={
                "key_id": b64(attacker.key_id),
                "attestation": b64(attacker.attestation(base64.b64decode(ch))),
                "challenge": ch,
            },
        )
        assert (r.status_code, r.json()["detail"]["code"]) == (401, "attestation_failed")


def test_disabled_mode_challenge(data):  # noqa: F811
    from tests.test_api import make_client

    client, *_ = make_client(data)
    with client:
        assert client.post("/v1/attest/challenge").json() == {"required": False, "challenge": None}
