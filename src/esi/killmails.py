from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from src.core.models import Killmail, KillmailRef
from src.esi.client import AsyncESIClient


async def fetch_recent_killmails(
    client: AsyncESIClient,
    corporation_id: int,
    etag: str | None = None,
    *,
    force_body: bool = False,
) -> tuple[str, str | None, list[KillmailRef]]:
    headers: dict[str, str] = {}
    if etag and not force_body:
        # renvoyer l'ETag tel quel (guillemets/W/ inclus) pour une revalidation correcte
        headers["If-None-Match"] = etag

    # on passe par _request pour récupérer les headers même si la payload est une LISTE
    resp = await client._request(
        "GET", f"/v1/corporations/{corporation_id}/killmails/recent/?page=1", headers=headers
    )

    if resp.status_code == 304:
        # Rien de nouveau : on renvoie "not_modified" et on conserve l'ETag
        return "not_modified", resp.headers.get("ETag", etag), []

    resp.raise_for_status()
    new_etag = resp.headers.get("ETag")
    data: Any = resp.json()

    # Normalement: une LISTE d'objets {killmail_id, killmail_hash}
    if not isinstance(data, list):
        return "ok", new_etag, []

    refs = [
        KillmailRef(killmail_id=int(x["killmail_id"]), killmail_hash=str(x["killmail_hash"]))
        for x in data
        if x and "killmail_id" in x and "killmail_hash" in x
    ]
    return "ok", new_etag, refs


async def fetch_killmail_details(client: AsyncESIClient, km_id: int, km_hash: str) -> Killmail:
    data_any: Any = await client.get_json(f"/v1/killmails/{km_id}/{km_hash}/")
    if not isinstance(data_any, dict):
        raise TypeError("Unexpected response type for /killmails details")
    data = cast(dict, data_any)

    # enrichissements
    data["killmail_id"] = km_id
    data["killmail_hash"] = km_hash

    km = Killmail.model_validate(data)

    if not isinstance(km.killmail_time, datetime):
        from datetime import datetime as _dt

        # ESI: "2025-09-10T12:33:06Z"
        t = str(data.get("killmail_time", ""))
        km.killmail_time = _dt.fromisoformat(t.replace("Z", "+00:00"))
    return km
