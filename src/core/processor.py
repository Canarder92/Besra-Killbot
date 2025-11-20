from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any

import discord

from src.esi.killmails import fetch_killmail_details


def _lookup(name_map: dict[int, str], key: int | None) -> str | None:
    return name_map.get(key) if key else None


@dataclass
class PipelineContext:
    # Services
    esi: Any
    prices: Any
    channel: discord.abc.Messageable
    settings: Any
    # Helpers (callbacks)
    resolve_names: Callable[[Any, Iterable[int]], Awaitable[list[dict]]]
    get_region_id_for_system: Callable[[Any, int], Awaitable[int | None]]
    compute_killmail_value: Callable[[Any, Any], Awaitable[float]]
    compute_killmail_drop: Callable[[Any, Any], Awaitable[float]]
    build_embed_insight5: Callable[..., Any]


async def process_ref(ctx: PipelineContext, killmail_id: int, killmail_hash: str) -> None:
    """Pipeline unique: ESI -> noms -> pricing -> embed -> post."""
    km = await fetch_killmail_details(ctx.esi, killmail_id, killmail_hash)
    is_kill = any(a.corporation_id == int(ctx.settings.CORPORATION_ID) for a in km.attackers)

    # IDs à résoudre
    ids: set[int] = set()
    if km.victim.character_id:
        ids.add(km.victim.character_id)
    ids.add(km.victim.corporation_id)
    if km.victim.alliance_id:
        ids.add(km.victim.alliance_id)

    fb = next((a for a in km.attackers if a.final_blow), km.attackers[0] if km.attackers else None)
    if fb:
        if fb.character_id:
            ids.add(fb.character_id)
        if fb.corporation_id:
            ids.add(fb.corporation_id)
        if fb.alliance_id:
            ids.add(fb.alliance_id)
        if fb.ship_type_id:
            ids.add(fb.ship_type_id)

    ids.add(km.victim.ship_type_id)
    ids.add(km.solar_system_id)

    region_id = await ctx.get_region_id_for_system(ctx.esi, km.solar_system_id)
    region_name = "Unknown Region"
    if region_id:
        ids.add(region_id)

    # Noms (tolérance aux erreurs)
    name_map: dict[int, str] = {}
    try:
        names = await ctx.resolve_names(ctx.esi, ids)  # [{"id":..., "name":...}]
        for e in names:
            _id = e.get("id")
            _nm = e.get("name")
            if isinstance(_id, int) and isinstance(_nm, str):
                name_map[_id] = _nm

        system_name = name_map.get(km.solar_system_id, f"System {km.solar_system_id}")
        ship_name = name_map.get(km.victim.ship_type_id, f"Type {km.victim.ship_type_id}")
        final_ship_name = _lookup(name_map, fb.ship_type_id if fb else None)
        victim_name = _lookup(name_map, km.victim.character_id)
        victim_corp_name = _lookup(name_map, km.victim.corporation_id)
        victim_all_name = _lookup(name_map, km.victim.alliance_id)
        if region_id:
            region_name = name_map.get(region_id, region_name)
    except Exception as e:
        import traceback

        print(f"[processor] resolve_names error for killmail {killmail_id}: {e}")
        print(f"[processor] traceback:\n{traceback.format_exc()}")
        system_name = f"System {km.solar_system_id}"
        ship_name = f"Type {km.victim.ship_type_id}"
        final_ship_name = None
        victim_name = None
        victim_corp_name = None
        victim_all_name = None

    # Pricing
    total_value = await ctx.compute_killmail_value(km, ctx.prices)
    dropped_value = await ctx.compute_killmail_drop(km, ctx.prices)

    # Embed + post
    embed = ctx.build_embed_insight5(
        km,
        victim_name=victim_name,
        victim_corp_name=victim_corp_name,
        victim_all_name=victim_all_name,
        final_name=(fb and fb.character_id and name_map.get(fb.character_id)) or None,
        final_corp_name=(fb and fb.corporation_id and name_map.get(fb.corporation_id)) or None,
        final_all_name=(fb and fb.alliance_id and name_map.get(fb.alliance_id)) or None,
        system_name=system_name,
        region_name=region_name,
        ship_name=ship_name,
        final_ship_name=final_ship_name,
        total_value=total_value,
        is_kill=is_kill,
        region_id=region_id,
        dropped_value=dropped_value,
    )
    await ctx.channel.send(embed=embed)
