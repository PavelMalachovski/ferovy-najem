"""httpx MockTransport that serves recorded API KN fixtures (no live calls in tests)."""

import json
from pathlib import Path

import httpx

from app.clients.api_kn import ApiKnClient, Cache, NullCache
from app.config import Settings

FIX = Path(__file__).parent / "fixtures" / "api_kn"

ROUTES = {
    "/Stavby/AdresniMisto/21951977": "stavba_adresni_misto_21951977.json",
    "/Jednotky/24136425010": "jednotka_24136425010.json",
    "/Rizeni/110041154010": "rizeni_110041154010.json",
    "/Rizeni/110039944010": "rizeni_110039944010.json",
    "/CiselnikyISKN/ZpusobyVyuzitiJednotky": "ciselnik_ZpusobyVyuzitiJednotky.json",
    "/AplikacniSluzby/StavUctu": "stav_uctu_after.json",
}


def load(name: str) -> dict:
    return json.loads((FIX / name).read_text(encoding="utf-8"))


class FakeApiKn:
    def __init__(self, overrides: dict[str, tuple[int, dict | None]] | None = None) -> None:
        self.overrides = overrides or {}
        self.requests: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/api/v1")
        self.requests.append(path)
        assert request.headers["ApiKey"] == "test-key"
        if path in self.overrides:
            status, body = self.overrides[path]
            return httpx.Response(status, json=body)
        if path in ROUTES:
            return httpx.Response(200, json=load(ROUTES[path]))
        return httpx.Response(404)

    def client(self, cache: Cache | None = None) -> ApiKnClient:
        settings = Settings(cuzk_api_key="test-key", _env_file=None)
        http = httpx.Client(
            base_url=settings.cuzk_api_base_url,
            headers={"ApiKey": "test-key"},
            transport=httpx.MockTransport(self.handler),
        )
        return ApiKnClient(http, cache or NullCache(), settings)
