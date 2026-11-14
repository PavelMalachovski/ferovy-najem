import pytest

from app.clients.api_kn import (
    ApiKnAuthError,
    ApiKnQuotaExceeded,
    ApiKnUnavailable,
    PgCache,
)
from tests.api_kn_fake import FakeApiKn


def test_parses_building_from_fixture():
    res = FakeApiKn().client().stavba_by_adresni_misto(21951977)
    s = res.data
    assert s.cisla_domovni == [1403]
    assert s.obec.kod == 554782
    assert s.parcely[0].katastralni_uzemi.nazev == "Nusle"
    assert len(s.jednotky) == 30
    assert res.as_of is not None
    assert res.from_cache is False


def test_404_returns_none():
    assert FakeApiKn().client().stavba_by_adresni_misto(1) is None


def test_account_status_not_counted():
    fake = FakeApiKn()
    client = fake.client()
    st = client.account_status()
    assert st.limit_volani == 500
    assert client.calls == 0


@pytest.mark.parametrize(
    ("status", "exc"),
    [(429, ApiKnQuotaExceeded), (401, ApiKnAuthError), (503, ApiKnUnavailable)],
)
def test_error_mapping(status, exc):
    fake = FakeApiKn({"/Jednotky/1": (status, None)})
    with pytest.raises(exc):
        fake.client().jednotka(1)


def test_pg_cache_positive_and_negative(db):
    fake = FakeApiKn()
    client = fake.client(PgCache(db))
    assert client.stavba_by_adresni_misto(21951977).from_cache is False
    assert client.stavba_by_adresni_misto(21951977).from_cache is True
    assert client.stavba_by_adresni_misto(1) is None
    assert client.stavba_by_adresni_misto(1) is None  # negative cache hit
    assert fake.requests == ["/Stavby/AdresniMisto/21951977", "/Stavby/AdresniMisto/1"]
    assert client.calls == 2


def test_quota_error_is_not_cached(db):
    fake = FakeApiKn({"/Jednotky/1": (429, None)})
    client = fake.client(PgCache(db))
    for _ in range(2):
        with pytest.raises(ApiKnQuotaExceeded):
            client.jednotka(1)
    assert len(fake.requests) == 2
