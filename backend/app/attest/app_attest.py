"""Apple App Attest server-side verification (docs/SPEC.md §4.2).

Follows Apple's "Validating apps that connect to your server":

Attestation (once per key):
  1. x5c = [credCert, intermediate] chains to Apple App Attestation Root CA.
  2. clientDataHash = SHA256(challenge); nonce = SHA256(authData || clientDataHash).
  3. credCert extension 1.2.840.113635.100.8.2 contains that nonce.
  4. SHA256(credCert public key, uncompressed point) == keyId.
  5. authData.rpIdHash == SHA256("<TeamID>.<bundle id>").
  6. authData.counter == 0.
  7. aaguid == "appattestdevelop" (development) or "appattest" + 7×0x00 (production).
  8. authData.credentialId == keyId.

Assertion (every protected request):
  1. clientDataHash = SHA256(clientData); nonce = SHA256(authenticatorData || clientDataHash).
  2. ECDSA-P256-SHA256 signature over nonce verifies with the stored public key.
  3. rpIdHash == SHA256(App ID).
  4. counter > stored counter (replay protection).

Our clientData for assertions is the raw HTTP request body: the signature binds the request
content, the strictly increasing counter prevents replays (no extra challenge round trip).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import cbor2
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

APPLE_ROOT_PEM = Path(__file__).with_name("Apple_App_Attestation_Root_CA.pem")
NONCE_OID = x509.ObjectIdentifier("1.2.840.113635.100.8.2")
AAGUID = {
    "development": b"appattestdevelop",
    "production": b"appattest" + b"\x00" * 7,
}
Environment = Literal["development", "production"]


class AttestationError(Exception):
    """Verification failed. Message is for logs only, never for the client."""


@dataclass(frozen=True)
class AttestedKey:
    key_id: bytes
    public_key_der: bytes  # SubjectPublicKeyInfo DER
    counter: int


@dataclass(frozen=True)
class AuthData:
    rp_id_hash: bytes
    flags: int
    counter: int
    aaguid: bytes | None
    credential_id: bytes | None


def parse_auth_data(raw: bytes) -> AuthData:
    if len(raw) < 37:
        raise AttestationError("authData too short")
    rp_id_hash, flags, counter = raw[:32], raw[32], struct.unpack(">I", raw[33:37])[0]
    aaguid = cred_id = None
    if flags & 0x40:  # AT: attested credential data present
        if len(raw) < 55:
            raise AttestationError("attested credential data truncated")
        aaguid = raw[37:53]
        (cred_len,) = struct.unpack(">H", raw[53:55])
        cred_id = raw[55 : 55 + cred_len]
        if len(cred_id) != cred_len:
            raise AttestationError("credentialId truncated")
    return AuthData(rp_id_hash, flags, counter, aaguid, cred_id)


def _expected_nonce_extension(nonce: bytes) -> bytes:
    """DER: SEQUENCE { [1] EXPLICIT OCTET STRING (32 bytes) }."""
    return bytes([0x30, 0x24, 0xA1, 0x22, 0x04, 0x20]) + nonce


def _uncompressed_point(cert: x509.Certificate) -> bytes:
    pub = cert.public_key()
    if not isinstance(pub, ec.EllipticCurvePublicKey) or not isinstance(pub.curve, ec.SECP256R1):
        raise AttestationError("credential key is not P-256")
    return pub.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )


class AppAttestVerifier:
    def __init__(
        self,
        app_id: str,
        environment: Environment,
        root_pem: bytes | None = None,
        now: callable = lambda: dt.datetime.now(dt.UTC),
    ) -> None:
        self.rp_id_hash = hashlib.sha256(app_id.encode()).digest()
        self.aaguid = AAGUID[environment]
        self.root = x509.load_pem_x509_certificate(root_pem or APPLE_ROOT_PEM.read_bytes())
        self.now = now

    # ---------- attestation ----------

    def verify_attestation(
        self, key_id: bytes, attestation: bytes, challenge: bytes
    ) -> AttestedKey:
        try:
            obj = cbor2.loads(attestation)
        except Exception as e:
            raise AttestationError(f"attestation is not CBOR: {e}") from e
        if not isinstance(obj, dict) or obj.get("fmt") != "apple-appattest":
            raise AttestationError("unexpected attestation format")
        x5c = (obj.get("attStmt") or {}).get("x5c") or []
        auth_raw = obj.get("authData")
        if len(x5c) < 2 or not isinstance(auth_raw, bytes):
            raise AttestationError("missing x5c or authData")

        # 1. certificate chain
        try:
            cred = x509.load_der_x509_certificate(x5c[0])
            inter = x509.load_der_x509_certificate(x5c[1])
            cred.verify_directly_issued_by(inter)
            inter.verify_directly_issued_by(self.root)
        except (ValueError, TypeError, InvalidSignature) as e:
            raise AttestationError(f"certificate chain invalid: {e}") from e
        now = self.now()
        for c in (cred, inter, self.root):
            if not (c.not_valid_before_utc <= now <= c.not_valid_after_utc):
                raise AttestationError(
                    f"certificate outside validity: {c.subject.rfc4514_string()}"
                )

        # 2–3. nonce in credCert extension
        nonce = hashlib.sha256(auth_raw + hashlib.sha256(challenge).digest()).digest()
        try:
            ext = cred.extensions.get_extension_for_oid(NONCE_OID).value
        except x509.ExtensionNotFound as e:
            raise AttestationError("nonce extension missing") from e
        if getattr(ext, "value", None) != _expected_nonce_extension(nonce):
            raise AttestationError("nonce mismatch")

        # 4. key id = SHA256(public key)
        point = _uncompressed_point(cred)
        if hashlib.sha256(point).digest() != key_id:
            raise AttestationError("keyId does not match credential public key")

        # 5–8. authenticator data
        auth = parse_auth_data(auth_raw)
        if auth.rp_id_hash != self.rp_id_hash:
            raise AttestationError("rpIdHash does not match App ID")
        if auth.counter != 0:
            raise AttestationError("attestation counter must be 0")
        if auth.aaguid != self.aaguid:
            raise AttestationError("aaguid does not match environment")
        if auth.credential_id != key_id:
            raise AttestationError("credentialId does not match keyId")

        der = cred.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        return AttestedKey(key_id=key_id, public_key_der=der, counter=0)

    # ---------- assertion ----------

    def verify_assertion(self, key: AttestedKey, assertion: bytes, client_data: bytes) -> int:
        """Returns the new counter to store."""
        try:
            obj = cbor2.loads(assertion)
            signature, auth_raw = obj["signature"], obj["authenticatorData"]
        except Exception as e:
            raise AttestationError(f"assertion is not valid CBOR: {e}") from e

        nonce = hashlib.sha256(auth_raw + hashlib.sha256(client_data).digest()).digest()
        pub = serialization.load_der_public_key(key.public_key_der)
        try:
            pub.verify(signature, nonce, ec.ECDSA(hashes.SHA256()))
        except InvalidSignature as e:
            raise AttestationError("assertion signature invalid") from e

        auth = parse_auth_data(auth_raw)
        if auth.rp_id_hash != self.rp_id_hash:
            raise AttestationError("rpIdHash does not match App ID")
        if auth.counter <= key.counter:
            raise AttestationError("assertion counter did not increase (replay?)")
        return auth.counter
