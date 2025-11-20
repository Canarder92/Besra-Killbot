from __future__ import annotations

import httpx

ZKB_BASE = "https://zkillboard.com/api"
USER_AGENT = "Besra-Killbot/1.0 (+https://zkillboard.com)"  # ✅ la '}' supprimée


class ZKBError(Exception):
    pass


class KillmailRef(dict):
    """Petit conteneur lightweight (killmail_id, killmail_hash)."""

    __slots__ = ()

    def __init__(self, killmail_id: int, killmail_hash: str) -> None:
        super().__init__(killmail_id=int(killmail_id), killmail_hash=str(killmail_hash))

    @property
    def killmail_id(self) -> int:
        return int(self["killmail_id"])

    @property
    def killmail_hash(self) -> str:
        return str(self["killmail_hash"])


async def fetch_corporation_killrefs(
    corporation_id: int,
    *,
    pages: int = 1,
    timeout_s: float = 10.0,
) -> list[KillmailRef]:
    headers = {
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }

    results: list[KillmailRef] = []

    async with httpx.AsyncClient(
        http2=True, timeout=httpx.Timeout(timeout_s, connect=timeout_s)
    ) as s:
        for page in range(1, max(1, pages) + 1):
            url = f"{ZKB_BASE}/corporationID/{corporation_id}/page/{page}/"
            resp = await s.get(url, headers=headers)

            if resp.status_code == 404:
                break
            
            if resp.status_code != 200:
                print(f"[zKill] HTTP {resp.status_code} for {url}")
                print(f"[zKill]   Response headers: {dict(resp.headers)}")
                try:
                    print(f"[zKill]   Response body: {resp.text[:500]}")
                except Exception:
                    pass

            resp.raise_for_status()
            data = resp.json()

            if not isinstance(data, list) or not data:
                break

            for it in data:
                km_id = (
                    it.get("killmail_id")
                    or it.get("killID")
                    or it.get("killId")
                    or it.get("killid")
                )
                zkb_hash = (it.get("zkb") or {}).get("hash") or it.get("hash")

                if km_id and zkb_hash:
                    results.append(KillmailRef(int(km_id), str(zkb_hash)))

    return results
