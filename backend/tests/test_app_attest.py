import pytest

from app.attest.app_attest import AAGUID, AppAttestVerifier, AttestationError
from tests.attest_factory import APP_ID, NOW, Device

CHALLENGE = b"server-challenge-0123456789abcdef"


@pytest.fixture
def dev():
    return Device()


def verifier(dev, env="production"):
    return AppAttestVerifier(APP_ID, env, root_pem=dev.root_pem, now=lambda: NOW)


def test_apple_root_ca_bundled():
    v = AppAttestVerifier(APP_ID, "production")
    assert "Apple App Attestation Root CA" in v.root.subject.rfc4514_string()


def test_attestation_and_assertions(dev):
    v = verifier(dev)
    key = v.verify_attestation(dev.key_id, dev.attestation(CHALLENGE), CHALLENGE)
    assert key.counter == 0
    body = b'{"ruian_code": 21951977}'
    c1 = v.verify_assertion(key, dev.assertion(body), body)
    assert c1 == 1
    key2 = type(key)(key.key_id, key.public_key_der, c1)
    assert v.verify_assertion(key2, dev.assertion(body), body) == 2


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"app_id": "OTHER.cz.evil.app"}, "rpIdHash"),
        ({"counter": 1}, "counter must be 0"),
        ({"aaguid": AAGUID["development"]}, "aaguid"),
        ({"cred_id": b"x" * 32}, "credentialId"),
        ({"nonce_override": b"\x00" * 32}, "nonce"),
    ],
)
def test_attestation_rejections(dev, kwargs, match):
    with pytest.raises(AttestationError, match=match):
        verifier(dev).verify_attestation(
            dev.key_id, dev.attestation(CHALLENGE, **kwargs), CHALLENGE
        )


def test_attestation_wrong_challenge(dev):
    with pytest.raises(AttestationError, match="nonce"):
        verifier(dev).verify_attestation(dev.key_id, dev.attestation(CHALLENGE), b"other")


def test_attestation_wrong_key_id(dev):
    with pytest.raises(AttestationError, match="keyId"):
        verifier(dev).verify_attestation(b"\x01" * 32, dev.attestation(CHALLENGE), CHALLENGE)


def test_attestation_untrusted_chain(dev):
    other_root = Device()
    v = AppAttestVerifier(APP_ID, "production", root_pem=other_root.root_pem, now=lambda: NOW)
    with pytest.raises(AttestationError, match="chain"):
        v.verify_attestation(dev.key_id, dev.attestation(CHALLENGE), CHALLENGE)


def test_development_environment(dev):
    att = dev.attestation(CHALLENGE, aaguid=AAGUID["development"])
    assert verifier(dev, "development").verify_attestation(dev.key_id, att, CHALLENGE)


def test_assertion_rejections(dev):
    v = verifier(dev)
    key = v.verify_attestation(dev.key_id, dev.attestation(CHALLENGE), CHALLENGE)
    body = b"{}"
    with pytest.raises(AttestationError, match="signature"):
        v.verify_assertion(key, dev.assertion(body), b"tampered body")
    with pytest.raises(AttestationError, match="counter"):
        v.verify_assertion(key, dev.assertion(body, counter=0), body)
    with pytest.raises(AttestationError, match="rpIdHash"):
        v.verify_assertion(key, dev.assertion(body, app_id="X.y"), body)
    with pytest.raises(AttestationError, match="CBOR"):
        v.verify_assertion(key, b"garbage", body)
