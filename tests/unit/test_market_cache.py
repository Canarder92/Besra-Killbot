import json
from datetime import datetime, timedelta

from src.core.prices_cache import PricesCache


def test_prices_cache_ttl_valid(tmp_path, monkeypatch):
    p = tmp_path / "prices.json"
    cache = PricesCache(str(p))

    # Force une TTL courte pour le test
    monkeypatch.setattr(cache, "ttl", timedelta(days=7))

    now_iso = datetime.utcnow().isoformat()
    data = {"31117": {"avg_price": 123.45, "updated_at": now_iso}}
    p.write_text(json.dumps(data))

    assert cache.get(31117) == 123.45


def test_prices_cache_ttl_expired(tmp_path, monkeypatch):
    p = tmp_path / "prices.json"
    cache = PricesCache(str(p))

    monkeypatch.setattr(cache, "ttl", timedelta(days=7))

    old_iso = (datetime.utcnow() - timedelta(days=8)).isoformat()
    data = {"31117": {"avg_price": 123.45, "updated_at": old_iso}}
    p.write_text(json.dumps(data))

    assert cache.get(31117) is None


def test_prices_cache_set_and_get(tmp_path):
    p = tmp_path / "prices.json"
    cache = PricesCache(str(p))
    cache.set(32880, 42.0)
    assert cache.get(32880) == 42.0
