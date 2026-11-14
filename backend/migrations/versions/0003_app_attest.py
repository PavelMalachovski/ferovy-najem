"""App Attest: one-time challenges and attested device keys.

Only a SHA-256 of the key id is stored (pseudonymous), plus the public key and the
assertion counter. No link to reports or IPs.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-14
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE attest_challenge (
            challenge_hash text PRIMARY KEY,
            expires_at     timestamptz NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE attested_key (
            key_hash       text PRIMARY KEY,
            public_key_der bytea NOT NULL,
            counter        bigint NOT NULL,
            environment    text NOT NULL,
            created_at     timestamptz NOT NULL DEFAULT now(),
            last_used_at   timestamptz NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS attested_key")
    op.execute("DROP TABLE IF EXISTS attest_challenge")
