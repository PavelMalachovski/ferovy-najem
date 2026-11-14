import datetime as dt

import httpx
from sqlalchemy import text

from app.api.protection import RateLimiter
from app.clients.api_kn import StavUctu
from app.config import OpsSettings, Settings
from app.ops import cleanup
from app.ops.alerts import Alerter
from app.ops.quota_watch import check


def status(used, limit=500, expires="2027-05-13T17:16:38"):
    return StavUctu(
        aktualni_obdobi="2026.11.14",
        provedeno_volani=used,
        limit_volani=limit,
        expirace_api_key=dt.datetime.fromisoformat(expires),
    )


def test_quota_levels_and_dedup(db):
    s = Settings(_env_file=None)
    a = Alerter(s.ops, RateLimiter(db))
    today = dt.date(2026, 11, 14)
    assert check(status(100), s, a, today) == []
    assert check(status(360), s, a, today) == ["quota70:2026.11.14"]
    assert check(status(370), s, a, today) == []  # same level, same day → deduplicated
    assert check(status(460), s, a, today) == ["quota90:2026.11.14"]


def test_key_expiry(db):
    s = Settings(_env_file=None)
    a = Alerter(s.ops, RateLimiter(db))
    assert check(status(1), s, a, dt.date(2027, 4, 20)) == ["key_expiry:2027-05-13"]
    assert check(status(1), s, a, dt.date(2027, 1, 1)) == []


def test_telegram_sent_when_configured(db):
    sent = []
    http = httpx.Client(
        transport=httpx.MockTransport(lambda r: sent.append(r) or httpx.Response(200))
    )
    ops = OpsSettings(alert_telegram_bot_token="t0k3n", alert_telegram_chat_id="42")
    assert Alerter(ops, RateLimiter(db), http).send("x", "hello") is True
    assert sent[0].url.path == "/bott0k3n/sendMessage"


def test_cleanup(db):
    with db.begin() as c:
        c.execute(text("INSERT INTO attest_challenge VALUES ('a', now() - interval '1 minute')"))
        c.execute(text("INSERT INTO attest_challenge VALUES ('b', now() + interval '1 minute')"))
        c.execute(
            text(
                "INSERT INTO attested_key "
                "(key_hash, public_key_der, counter, environment, last_used_at) "
                "VALUES ('old', '\\x00', 1, 'production', now() - interval '200 days'), "
                "('new', '\\x00', 1, 'production', now())"
            )
        )
    removed = cleanup.run(db, 180)
    assert removed["attest_challenge"] == 1
    assert removed["attested_key"] == 1
