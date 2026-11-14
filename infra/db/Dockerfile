# Postgres 16 + PostGIS 3 from the official PGDG apt repo (multi-arch: amd64 + arm64).
# The postgis/postgis image has no arm64 build.
FROM postgres:16-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-16-postgis-3 \
    && rm -rf /var/lib/apt/lists/*

COPY init/ /docker-entrypoint-initdb.d/
