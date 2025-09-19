from __future__ import annotations

import asyncio
import os

import discord

from src.botui.embeds import build_embed_insight5
from src.config import settings
from src.core.prices_cache import PricesCache
from src.core.pricing import compute_killmail_drop, compute_killmail_value
from src.core.processor import PipelineContext, process_ref
from src.core.store import JSONStore
from src.esi.client import AsyncESIClient
from src.esi.killmails import fetch_recent_killmails
from src.esi.universe import get_region_id_for_system, resolve_names
from src.zkb.runner import maybe_run_zkb_after_esi
from src.zkb.zkill import fetch_corporation_killrefs

KILLS_INDEX_PATH = os.path.join("data", "kills_index.json")
PRICES_PATH = os.path.join("data", "prices.json")


class KillIndex:
    def __init__(self, path: str):
        self.path = path
        self.store = JSONStore(path, [])
        self._lock = asyncio.Lock()

    async def load(self) -> list[dict]:
        return self.store.read()

    async def add_if_absent(self, km_id: int, km_hash: str) -> bool:
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
        async with self._lock:
            arr = self.store.read()
            return {(int(x.get("id")), str(x.get("hash"))) for x in arr}


async def start_scheduler(discord_client: discord.Client, channel_id: int):
    # Channel
    channel = discord_client.get_channel(channel_id)
    if not isinstance(
        channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel)
    ) and hasattr(discord_client, "fetch_channel"):
        channel = await discord_client.fetch_channel(channel_id)  # type: ignore[assignment]
    if not isinstance(channel, discord.abc.Messageable):
        print("Channel introuvable ou non postable.")
        return

    # Stores / clients
    idx = KillIndex(KILLS_INDEX_PATH)
    prices = PricesCache(PRICES_PATH)
    esi = AsyncESIClient()

    # Contexte pipeline partagé (ESI + zKill)
    ctx = PipelineContext(
        esi=esi,
        prices=prices,
        channel=channel,
        settings=settings,
        resolve_names=resolve_names,
        get_region_id_for_system=get_region_id_for_system,
        compute_killmail_value=compute_killmail_value,
        compute_killmail_drop=compute_killmail_drop,
        build_embed_insight5=build_embed_insight5,
    )

    async def poll_task():
        while True:
            try:
                status, etag, refs = await fetch_recent_killmails(esi, int(settings.CORPORATION_ID))
                if status == "ok":
                    # ESI: claim -> pipeline partagé
                    for ref in refs:
                        if await idx.add_if_absent(ref.killmail_id, ref.killmail_hash):
                            await process_ref(ctx, ref.killmail_id, ref.killmail_hash)

                    # Après ESI: zKill 1 fois sur N, via le même pipeline
                    await maybe_run_zkb_after_esi(
                        settings=settings,
                        corporation_id=int(settings.CORPORATION_ID),
                        idx=idx,
                        process_ref=lambda km_id, km_hash: process_ref(ctx, km_id, km_hash),
                    )
            except Exception as e:
                print(f"[poll] error: {e}")
            await asyncio.sleep(settings.POLL_INTERVAL_SECONDS)

    async def cleanup_task():
        while True:
            try:
                # ESI: snapshot
                status, _etag, refs = await fetch_recent_killmails(
                    esi, int(settings.CORPORATION_ID), etag=None, force_body=True
                )
                current: set[tuple[int, str]] = set()
                if status == "ok":
                    current |= {(r.killmail_id, r.killmail_hash) for r in refs}

                # zKill: union pour garder les kills zKill-only
                if getattr(settings, "ZKB_ENABLE", False):
                    try:
                        zkb_refs = await fetch_corporation_killrefs(
                            int(settings.CORPORATION_ID),
                            pages=int(getattr(settings, "ZKB_PAGES", 1)),
                        )
                        for r in zkb_refs:
                            km_id = r["killmail_id"] if isinstance(r, dict) else r.killmail_id
                            km_hash = r["killmail_hash"] if isinstance(r, dict) else r.killmail_hash
                            current.add((int(km_id), str(km_hash)))
                    except Exception as e:
                        print(f"[cleanup][zkb] error: {e}")

                if current:
                    await idx.rewrite_with(current)
            except Exception as e:
                print(f"[cleanup] error: {e}")
            await asyncio.sleep(settings.CLEANUP_INTERVAL_MINUTES * 60)

    asyncio.create_task(poll_task())
    asyncio.create_task(cleanup_task())
