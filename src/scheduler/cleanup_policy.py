from __future__ import annotations


def should_rewrite_cleanup_index(
    *,
    esi_snapshot_ok: bool,
    zkb_enabled: bool,
    zkb_snapshot_ok: bool,
) -> bool:
    return esi_snapshot_ok and (not zkb_enabled or zkb_snapshot_ok)
