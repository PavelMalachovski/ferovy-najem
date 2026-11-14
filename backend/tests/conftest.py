import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

from app.config import get_settings

BACKEND = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"


def _test_db_url() -> str:
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        return explicit
    return (
        make_url(get_settings().database_url)
        .set(database="ferovy_test")
        .render_as_string(hide_password=False)
    )


@pytest.fixture(scope="session")
def db_engine() -> Iterator[Engine]:
    """Fresh test database with migrations applied. Skips locally if Postgres is down;
    fails in CI (REQUIRE_DB=1)."""
    url = make_url(_test_db_url())
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)'))
            c.execute(text(f'CREATE DATABASE "{url.database}"'))
    except Exception as e:
        if os.environ.get("REQUIRE_DB") == "1":
            raise
        pytest.skip(f"Postgres not available: {e}")
    finally:
        admin.dispose()

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.attributes["url"] = url.render_as_string(hide_password=False)
    command.upgrade(cfg, "head")

    engine = create_engine(url)
    yield engine
    engine.dispose()


@pytest.fixture
def db(db_engine: Engine) -> Iterator[Engine]:
    """Per-test isolation: truncate data tables."""
    with db_engine.begin() as c:
        c.execute(
            text(
                "TRUNCATE ingest_state, address_point, rent_map_dataset, external_cache, "
                "rate_limit_counter, flood_zone CASCADE"
            )
        )
    yield db_engine
