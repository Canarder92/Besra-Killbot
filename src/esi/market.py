# src/esi/market.py
from __future__ import annotations

from datetime import datetime

import httpx  # ⬅️ NEW

from src.config import settings
from src.esi.client import AsyncESIClient

_client: AsyncESIClient | None = None


async def _get_client() -> AsyncESIClient:
    global _client
    if _client is None:
        _client = AsyncESIClient()
    return _client


async def fetch_price(type_id: int) -> float:
    """
    Calcule la moyenne pondérée (poids=volume) des 7 derniers jours disponibles
    sur 'average' du /markets/{region_id}/history. Si l'endpoint renvoie 400/404,
    on considère le prix comme 0 et on laisse le cache l'enregistrer (TTL 7j).
    """
    client = await _get_client()
    region_id = settings.MARKET_REGION_ID
    url = f"/latest/markets/{region_id}/history/?type_id={type_id}"

    try:
        data = await client.get_json(url)
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        if status in (400, 404):
            # type_id invalide pour la région / données indisponibles → prix 0
            return 0.0
        raise

    if not isinstance(data, list) or not data:
        return 0.0

    def parse_day(x):
        return datetime.fromisoformat(x["date"])

    data_sorted = sorted(data, key=parse_day)
    last7 = data_sorted[-7:] if len(data_sorted) > 7 else data_sorted

    num = 0.0
    den = 0.0
    for d in last7:
        avg = float(d.get("average", 0.0))
        vol = float(d.get("volume", 0.0))
        num += avg * vol
        den += vol

    return (num / den) if den > 0 else float(last7[-1].get("average", 0.0))
