"""Initial schema: addresses, MF rent map, API KN cache, ingest state.

Revision ID: 0001
Revises:
Create Date: 2026-11-14
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    # unaccent() is STABLE; an IMMUTABLE wrapper is needed for use in indexes/generated columns.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION f_unaccent(text) RETURNS text
        LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
        AS $$ SELECT public.unaccent('public.unaccent'::regdictionary, $1) $$
        """
    )

    op.execute(
        """
        CREATE TABLE ingest_state (
            source      text PRIMARY KEY,
            version     text NOT NULL,
            fingerprint text NOT NULL,
            row_count   integer NOT NULL,
            loaded_at   timestamptz NOT NULL DEFAULT now()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE address_point (
            ruian_code       bigint PRIMARY KEY,
            obec_code        integer NOT NULL,
            obec_name        text NOT NULL,
            momc_name        text,
            cast_obce_name   text,
            ulice_name       text,
            so_type          text NOT NULL,
            cislo_domovni    integer NOT NULL,
            cislo_orientacni integer,
            znak_co          text,
            psc              text,
            label            text NOT NULL,
            search_text      text GENERATED ALWAYS AS (lower(f_unaccent(label))) STORED,
            geom             geometry(Point, 4326) NOT NULL,
            valid_from       date
        )
        """
    )
    op.execute(
        "CREATE INDEX address_point_search_trgm ON address_point "
        "USING gin (search_text gin_trgm_ops)"
    )
    op.execute("CREATE INDEX address_point_geom ON address_point USING gist (geom)")
    op.execute("CREATE INDEX address_point_obec ON address_point (obec_code)")

    op.execute(
        """
        CREATE TABLE rent_map_dataset (
            id          serial PRIMARY KEY,
            period_end  date NOT NULL,
            source_url  text,
            sha256      text NOT NULL UNIQUE,
            loaded_at   timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE rent_map_value (
            dataset_id          integer NOT NULL REFERENCES rent_map_dataset ON DELETE CASCADE,
            unit_code           integer NOT NULL,
            unit_kind           text NOT NULL CHECK (unit_kind IN ('ku', 'obec')),
            kraj                text NOT NULL,
            unit_name           text NOT NULL,
            obec_name           text NOT NULL,
            size_category       smallint NOT NULL CHECK (size_category BETWEEN 1 AND 4),
            reference           integer NOT NULL,
            band_low            integer NOT NULL,
            band_high           integer NOT NULL,
            reference_new_build integer NOT NULL,
            raw_min             integer NOT NULL,
            raw_max             integer NOT NULL,
            raw_median          integer NOT NULL,
            coverage            smallint NOT NULL CHECK (coverage BETWEEN 1 AND 5),
            PRIMARY KEY (dataset_id, unit_code, size_category)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE rent_map_surcharge (
            dataset_id    integer NOT NULL REFERENCES rent_map_dataset ON DELETE CASCADE,
            new_build     boolean NOT NULL,
            size_category smallint NOT NULL CHECK (size_category BETWEEN 1 AND 4),
            balcony       integer NOT NULL,
            terrace       integer NOT NULL,
            furnished     integer NOT NULL,
            garage        integer NOT NULL,
            lift          integer NOT NULL,
            PRIMARY KEY (dataset_id, new_build, size_category)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE api_kn_cache (
            key         text PRIMARY KEY,
            status      smallint NOT NULL,
            body        jsonb,
            fetched_at  timestamptz NOT NULL DEFAULT now(),
            expires_at  timestamptz NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX api_kn_cache_expires ON api_kn_cache (expires_at)")


def downgrade() -> None:
    for t in (
        "api_kn_cache",
        "rent_map_surcharge",
        "rent_map_value",
        "rent_map_dataset",
        "address_point",
        "ingest_state",
    ):
        op.execute(f"DROP TABLE IF EXISTS {t}")
    op.execute("DROP FUNCTION IF EXISTS f_unaccent(text)")
