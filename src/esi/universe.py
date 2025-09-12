from __future__ import annotations

from collections.abc import Iterable
from typing import Any, cast

from src.esi.client import AsyncESIClient


async def resolve_names(client: AsyncESIClient, ids: Iterable[int]) -> list[dict]:
    ids_list = list({int(x) for x in ids if x is not None})
    if not ids_list:
        return []
    data: Any = await client.post_json("/latest/universe/names/", json=ids_list)
    # L'API renvoie une liste de dicts
    if isinstance(data, list):
        return cast(list[dict], data)
    return []


async def get_system(client: AsyncESIClient, system_id: int) -> dict:
    data: Any = await client.get_json(f"/latest/universe/systems/{system_id}/")
    if isinstance(data, dict):
        return cast(dict, data)
    raise TypeError("Unexpected response type for /universe/systems")


async def get_constellation(client: AsyncESIClient, constellation_id: int) -> dict:
    data: Any = await client.get_json(f"/latest/universe/constellations/{constellation_id}/")
    if isinstance(data, dict):
        return cast(dict, data)
    raise TypeError("Unexpected response type for /universe/constellations")


async def get_region_id_for_system(client: AsyncESIClient, system_id: int) -> int | None:
    sys = await get_system(client, system_id)
    constellation_id = sys.get("constellation_id")
    if not constellation_id:
        return None
    const = await get_constellation(client, int(constellation_id))
    rid = const.get("region_id")
    return int(rid) if rid is not None else None
