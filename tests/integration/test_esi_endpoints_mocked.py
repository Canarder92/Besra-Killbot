import json

import pytest

from src.esi.client import AsyncESIClient
from src.esi.market import fetch_price


@pytest.mark.asyncio
async def test_fetch_price_weighted_average(monkeypatch):
    # Utilise directement le fixture fourni dans le repo
    with open("tests/fixtures/market_history_full.json", encoding="utf-8") as f:
        payload = json.load(f)

    async def fake_get_json(self, url, headers=None, **kwargs):
        assert "/markets/" in url and "history" in url
        return payload

    monkeypatch.setattr(AsyncESIClient, "get_json", fake_get_json)

    price = await fetch_price(31117)
    # Vérifie que la moyenne pondérée tombe dans une plage plausible
    assert 38_000 <= price <= 50_000


@pytest.mark.asyncio
async def test_fetch_price_short_series(monkeypatch):
    with open("tests/fixtures/market_history_short.json", encoding="utf-8") as f:
        payload = json.load(f)

    async def fake_get_json(self, url, headers=None, **kwargs):
        return payload

    monkeypatch.setattr(AsyncESIClient, "get_json", fake_get_json)

    price = await fetch_price(11129)
    # Peu de jours => moyenne pondérée de ce qui existe
    # tolérance large car c'est un test de plage
    assert 35_000 <= price <= 50_000
