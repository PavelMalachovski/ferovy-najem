"""Daily housekeeping. Usage: python -m app.ops.cleanup"""

from __future__ import annotations

import logging
import sys

from sqlalchemy import Engine, text

from app.config import get_settings
from app.db import get_engine

log = logging.getLogger(__name__)


def run(engine: Engine, attested_key_retention_days: int) -> dict[str, int]:
    stmts = {
        "rate_limit_counter": "DELETE FROM rate_limit_counter WHERE expires_at < now()",
        "external_cache": "DELETE FROM external_cache WHERE expires_at < now()",
        "attest_challenge": "DELETE FROM attest_challenge WHERE expires_at < now()",
        "attested_key": "DELETE FROM attested_key "
        "WHERE last_used_at < now() - make_interval(days => :days)",
    }
    out = {}
    with engine.begin() as c:
        for name, sql in stmts.items():
            out[name] = c.execute(text(sql), {"days": attested_key_retention_days}).rowcount
    return out


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    removed = run(get_engine(), get_settings().ops.attested_key_retention_days)
    log.info("cleanup removed %s", removed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
