"""Report support: generic external cache, rate-limit counters, flood zones.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-14
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # One cache for API KN, ARES and ISIR; keys are prefixed (kn:, ares:, isir:).
    op.execute("ALTER TABLE api_kn_cache RENAME TO external_cache")
    op.execute("ALTER INDEX api_kn_cache_expires RENAME TO external_cache_expires")
    op.execute("TRUNCATE external_cache")  # old keys had no prefix

    # Short-lived counters; UNLOGGED: losing them on crash is acceptable.
    # Keys are hashes (salted IP / device key id), never raw identifiers.
    op.execute(
        """
        CREATE UNLOGGED TABLE rate_limit_counter (
            key          text NOT NULL,
            window_start timestamptz NOT NULL,
            count        integer NOT NULL,
            expires_at   timestamptz NOT NULL,
            PRIMARY KEY (key, window_start)
        )
        """
    )
    op.execute("CREATE INDEX rate_limit_counter_expires ON rate_limit_counter (expires_at)")

    # Flood zones in S-JTSK (metres) for cheap distance queries; subdivided polygons.
    op.execute(
        """
        CREATE TABLE flood_zone (
            id         bigserial PRIMARY KEY,
            zone_type  text NOT NULL CHECK (zone_type IN ('q100', 'active')),
            river      text,
            geom       geometry(Polygon, 5514) NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX flood_zone_geom ON flood_zone USING gist (geom)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS flood_zone")
    op.execute("DROP TABLE IF EXISTS rate_limit_counter")
    op.execute("ALTER INDEX external_cache_expires RENAME TO api_kn_cache_expires")
    op.execute("ALTER TABLE external_cache RENAME TO api_kn_cache")
