"""Synthetic App Attest objects signed by a test CA (mirrors Apple's structure)."""

import datetime as dt
import hashlib
import struct

import cbor2
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from app.attest.app_attest import AAGUID, NONCE_OID, _expected_nonce_extension

APP_ID = "TEAMID1234.cz.ferovynajem.app"
NOW = dt.datetime(2026, 11, 14, tzinfo=dt.UTC)


def _cert(subject, issuer_name, pub, signer, *, ca, ext=None, days=365):
    b = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, subject)]))
        .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer_name)]))
        .public_key(pub)
        .serial_number(x509.random_serial_number())
        .not_valid_before(NOW - dt.timedelta(days=1))
        .not_valid_after(NOW + dt.timedelta(days=days))
        .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
    )
    if ext is not None:
        b = b.add_extension(x509.UnrecognizedExtension(NONCE_OID, ext), critical=False)
    return b.sign(signer, hashes.SHA256())


class Device:
    def __init__(self, root_key=None):
        self.root_key = root_key or ec.generate_private_key(ec.SECP384R1())
        self.root = _cert(
            "Test Root", "Test Root", self.root_key.public_key(), self.root_key, ca=True
        )
        self.inter_key = ec.generate_private_key(ec.SECP384R1())
        self.inter = _cert(
            "Test Inter", "Test Root", self.inter_key.public_key(), self.root_key, ca=True
        )
        self.key = ec.generate_private_key(ec.SECP256R1())
        point = self.key.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        self.key_id = hashlib.sha256(point).digest()
        self.counter = 0

    @property
    def root_pem(self) -> bytes:
        return self.root.public_bytes(serialization.Encoding.PEM)

    def auth_data(
        self, counter, *, app_id=APP_ID, aaguid=AAGUID["production"], cred_id=None, attested=True
    ) -> bytes:
        rp = hashlib.sha256(app_id.encode()).digest()
        if not attested:
            return rp + bytes([0x01]) + struct.pack(">I", counter)
        cid = self.key_id if cred_id is None else cred_id
        return (
            rp
            + bytes([0x41])
            + struct.pack(">I", counter)
            + aaguid
            + struct.pack(">H", len(cid))
            + cid
        )

    def attestation(
        self, challenge: bytes, *, nonce_override=None, signer=None, **auth_kw
    ) -> bytes:
        auth = self.auth_data(auth_kw.pop("counter", 0), **auth_kw)
        nonce = nonce_override or hashlib.sha256(auth + hashlib.sha256(challenge).digest()).digest()
        cred = _cert(
            "Leaf",
            "Test Inter",
            self.key.public_key(),
            signer or self.inter_key,
            ca=False,
            ext=_expected_nonce_extension(nonce),
        )
        x5c = [
            cred.public_bytes(serialization.Encoding.DER),
            self.inter.public_bytes(serialization.Encoding.DER),
        ]
        return cbor2.dumps(
            {"fmt": "apple-appattest", "attStmt": {"x5c": x5c, "receipt": b""}, "authData": auth}
        )

    def assertion(self, client_data: bytes, *, counter=None, app_id=APP_ID) -> bytes:
        if counter is None:
            self.counter += 1
            counter = self.counter
        auth = self.auth_data(counter, app_id=app_id, attested=False)
        nonce = hashlib.sha256(auth + hashlib.sha256(client_data).digest()).digest()
        sig = self.key.sign(nonce, ec.ECDSA(hashes.SHA256()))
        return cbor2.dumps({"signature": sig, "authenticatorData": auth})
