from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from .zkill import fetch_corporation_killrefs

_ZKB_COUNTER = 0  # cadence 1 fois sur N cycles ESI


async def maybe_run_zkb_after_esi(
    *,
    settings: Any,
    corporation_id: int,
    idx: Any,
    process_ref: Callable[[int, str], Awaitable[None]],
) -> None:
    """À appeler après un cycle ESI réussi. Déclenche zKill 1 fois sur N et
    passe chaque (id, hash) au pipeline partagé via process_ref."""
    global _ZKB_COUNTER
    _ZKB_COUNTER += 1

    if not getattr(settings, "ZKB_ENABLE", False):
        return
    every_n = int(getattr(settings, "ZKB_EVERY_N", 3))
    if every_n <= 0 or (_ZKB_COUNTER % every_n) != 0:
        return

    try:
        zkb_refs = await fetch_corporation_killrefs(
            int(corporation_id),
            pages=int(getattr(settings, "ZKB_PAGES", 1)),
        )
        for ref in zkb_refs:
            km_id = ref["killmail_id"] if isinstance(ref, dict) else ref.killmail_id
            km_hash = ref["killmail_hash"] if isinstance(ref, dict) else ref.killmail_hash
            if await idx.add_if_absent(int(km_id), str(km_hash)):
                await process_ref(int(km_id), str(km_hash))
    except Exception as e:
        print(f"[zKill] error: {e}")
