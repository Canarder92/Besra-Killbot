from __future__ import annotations

import asyncio
import os

import discord

from src.botui.embeds import build_embed_insight5
from src.config import settings
from src.core.prices_cache import PricesCache
from src.core.pricing import compute_killmail_drop, compute_killmail_value
from src.core.store import JSONStore
from src.esi.client import AsyncESIClient
from src.esi.killmails import fetch_killmail_details, fetch_recent_killmails
from src.esi.universe import get_region_id_for_system, resolve_names

KILLS_INDEX_PATH = os.path.join("data", "kills_index.json")
PRICES_PATH = os.path.join("data", "prices.json")
NAMES_PATH = os.path.join("data", "names.json")  # dyn names cache


def _lookup(name_map: dict[int, str], key: int | None) -> str | None:
    """Retourne name_map[key] si key est non-nul/non-None, sinon None."""
    return name_map.get(key) if key else None


class KillIndex:
    """Un seul JSON: [{id, hash, posted}]"""

    def __init__(self, path: str):
        self.path = path
        self.store = JSONStore(path, [])
        self._lock = asyncio.Lock()

    async def load(self) -> list[dict]:
        # synchrone mais léger
        return self.store.read()

    async def add_and_mark_posted(self, km_id: int, km_hash: str):
        # (conservé pour compatibilité, plus utilisé par le scheduler)
        async with self._lock:
            arr = self.store.read()
            arr.append({"id": km_id, "hash": km_hash, "posted": True})
            self.store.write(arr)

    async def add_if_absent(self, km_id: int, km_hash: str) -> bool:
        """Ajoute (id, hash) s'il est absent (claim). True si on vient de l'ajouter."""
        async with self._lock:
            arr = self.store.read()
            for x in arr:
                if int(x.get("id")) == km_id and str(x.get("hash")) == km_hash:
                    return False
            arr.append({"id": km_id, "hash": km_hash, "posted": True})
            self.store.write(arr)
            return True

    async def rewrite_with(self, current_set: set[tuple[int, str]]):
        async with self._lock:
            arr = self.store.read()
            arr2 = [x for x in arr if (x.get("id"), x.get("hash")) in current_set]
            self.store.write(arr2)

    async def known_set(self) -> set[tuple[int, str]]:
        # on peut garder ce helper; pas nécessaire pour la déduplication désormais
        async with self._lock:
            arr = self.store.read()
            return {(int(x.get("id")), str(x.get("hash"))) for x in arr}


async def start_scheduler(discord_client: discord.Client, channel_id: int):
    """
    Démarre deux tâches:
      - poll_task: toutes les POLL_INTERVAL_SECONDS,
      on fetch la page 1 et on poste les nouveaux
      - cleanup_task: toutes CLEANUP_INTERVAL_MINUTES,
      on force un body et on réécrit kills_index pour refléter ESI
    """
    channel = discord_client.get_channel(channel_id)
    if not isinstance(
        channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel)
    ) and hasattr(discord_client, "fetch_channel"):
        channel = await discord_client.fetch_channel(channel_id)  # type: ignore[assignment]

    if not isinstance(channel, discord.abc.Messageable):
        print("Channel introuvable ou non postable.")
        return

    idx = KillIndex(KILLS_INDEX_PATH)
    prices = PricesCache(PRICES_PATH)
    esi = AsyncESIClient()

    async def poll_task():
        while True:
            try:
                status, etag, refs = await fetch_recent_killmails(esi, int(settings.CORPORATION_ID))
                if status == "ok":
                    # CLAIM AVANT ENVOI : on tente d'ajouter chaque ref sous lock.
                    # Si déjà présente, on skip -> évite les doublons inter-iterations/instances.
                    for ref in refs:
                        is_new = await idx.add_if_absent(ref.killmail_id, ref.killmail_hash)
                        if not is_new:
                            continue  # déjà traité (ou en cours par une autre instance)

                        # détails
                        km = await fetch_killmail_details(esi, ref.killmail_id, ref.killmail_hash)

                        # déterminer "is_kill" (corp impliquée côté attackers ?)
                        is_kill = any(
                            a.corporation_id == int(settings.CORPORATION_ID) for a in km.attackers
                        )

                        # Résolution des noms dynamiques + types + système + région
                        # IDs à résoudre via /universe/names:
                        ids = set()
                        if km.victim.character_id:
                            ids.add(km.victim.character_id)
                        ids.add(km.victim.corporation_id)
                        if km.victim.alliance_id:
                            ids.add(km.victim.alliance_id)
                        # final blow (si présent)
                        fb = next(
                            (a for a in km.attackers if a.final_blow),
                            km.attackers[0] if km.attackers else None,
                        )
                        if fb:
                            if fb.character_id:
                                ids.add(fb.character_id)
                            if fb.corporation_id:
                                ids.add(fb.corporation_id)
                            if fb.alliance_id:
                                ids.add(fb.alliance_id)
                            if fb.ship_type_id:
                                ids.add(fb.ship_type_id)
                        # ship victim
                        ids.add(km.victim.ship_type_id)
                        # system + region
                        ids.add(km.solar_system_id)
                        region_id = await get_region_id_for_system(esi, km.solar_system_id)
                        region_name = "Unknown Region"
                        if region_id:
                            ids.add(region_id)

                        name_map: dict[int, str] = {}
                        try:
                            names = await resolve_names(esi, ids)
                            for e in names:
                                name_map[int(e["id"])] = e["name"]
                            system_name = name_map.get(
                                km.solar_system_id, f"System {km.solar_system_id}"
                            )
                            ship_name = name_map.get(
                                km.victim.ship_type_id, f"Type {km.victim.ship_type_id}"
                            )
                            final_ship_name = _lookup(name_map, fb.ship_type_id if fb else None)
                            victim_name = _lookup(name_map, km.victim.character_id)
                            victim_corp_name = _lookup(
                                name_map, km.victim.corporation_id
                            )  # corp_id jamais None mais OK
                            victim_all_name = _lookup(name_map, km.victim.alliance_id)
                            if region_id:
                                region_name = name_map.get(region_id, region_name)
                        except Exception:
                            system_name = f"System {km.solar_system_id}"
                            ship_name = f"Type {km.victim.ship_type_id}"
                            final_ship_name = None
                            victim_name = None
                            victim_corp_name = None
                            victim_all_name = None

                        # Pricing
                        total_value = await compute_killmail_value(km, prices)
                        dropped_value = await compute_killmail_drop(km, prices)

                        # Embed
                        embed = build_embed_insight5(
                            km,
                            victim_name=victim_name,
                            victim_corp_name=victim_corp_name,
                            victim_all_name=victim_all_name,
                            final_name=(fb and fb.character_id and name_map.get(fb.character_id))
                            or None,
                            final_corp_name=(
                                fb and fb.corporation_id and name_map.get(fb.corporation_id)
                            )
                            or None,
                            final_all_name=(fb and fb.alliance_id and name_map.get(fb.alliance_id))
                            or None,
                            system_name=system_name,
                            region_name=region_name,
                            ship_name=ship_name,
                            final_ship_name=final_ship_name,
                            total_value=total_value,
                            is_kill=is_kill,
                            region_id=region_id,
                            dropped_value=dropped_value,
                        )

                        await channel.send(embed=embed)

                # sinon 304 -> rien à faire
            except Exception as e:
                print(f"[poll] error: {e}")
            await asyncio.sleep(settings.POLL_INTERVAL_SECONDS)

    async def cleanup_task():
        while True:
            try:
                # force un body frais (pas de If-None-Match)
                status, _etag, refs = await fetch_recent_killmails(
                    esi, int(settings.CORPORATION_ID), etag=None, force_body=True
                )
                if status == "ok":
                    current = {(r.killmail_id, r.killmail_hash) for r in refs}
                    await idx.rewrite_with(current)
            except Exception as e:
                print(f"[cleanup] error: {e}")
            await asyncio.sleep(settings.CLEANUP_INTERVAL_MINUTES * 60)

    # lancer les tâches
    asyncio.create_task(poll_task())
    asyncio.create_task(cleanup_task())
