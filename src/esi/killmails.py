from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import Any, cast

import httpx

from src.core.models import Killmail, KillmailRef
from src.esi.client import AsyncESIClient

# Rate limiter pour fetch_killmail_details: 3 requêtes par seconde
_last_detail_requests: list[float] = []
_detail_lock = asyncio.Lock()


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

    # Retry avec Retry-After en cas de 429
    max_retries = 3
    for attempt in range(max_retries):
        try:
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
        
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 429 and attempt < max_retries - 1:
                retry_after = e.response.headers.get("Retry-After", "60")
                wait_time = int(retry_after) + 1
                print(f"ESI Error 429 for GET /v1/corporations/{corporation_id}/killmails/recent/ retrying in {wait_time} sec")
                await asyncio.sleep(wait_time)
                continue
            elif 400 <= status < 500:
                print(f"ESI Error {status} for GET /v1/corporations/{corporation_id}/killmails/recent/")
            elif 500 <= status < 600:
                print(f"ESI Error {status} for GET /v1/corporations/{corporation_id}/killmails/recent/")
            raise
    
    # Si on arrive ici, toutes les tentatives ont échoué
    raise Exception(f"Failed to fetch recent killmails after {max_retries} attempts")


async def fetch_killmail_details(client: AsyncESIClient, km_id: int, km_hash: str) -> Killmail:
    # Rate limiting: max 3 requêtes par seconde
    async with _detail_lock:
        now = time.time()
        # Garder seulement les requêtes de la dernière seconde
        while _last_detail_requests and _last_detail_requests[0] < now - 1.0:
            _last_detail_requests.pop(0)
        
        # Si on a déjà 3 requêtes dans la dernière seconde, attendre
        if len(_last_detail_requests) >= 3:
            sleep_time = 1.0 - (now - _last_detail_requests[0])
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
            # Nettoyer à nouveau après le sleep
            now = time.time()
            while _last_detail_requests and _last_detail_requests[0] < now - 1.0:
                _last_detail_requests.pop(0)
        
        _last_detail_requests.append(time.time())
    
    # Retry avec Retry-After en cas de 429
    max_retries = 3
    for attempt in range(max_retries):
        try:
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
        
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 429 and attempt < max_retries - 1:
                retry_after = e.response.headers.get("Retry-After", "60")
                wait_time = int(retry_after) + 1
                print(f"ESI Error 429 for GET /v1/killmails/{km_id}/{km_hash}/ retrying in {wait_time} sec")
                await asyncio.sleep(wait_time)
                continue
            elif 400 <= status < 500:
                print(f"ESI Error {status} for GET /v1/killmails/{km_id}/{km_hash}/")
            elif 500 <= status < 600:
                print(f"ESI Error {status} for GET /v1/killmails/{km_id}/{km_hash}/")
            raise
    
    # Si on arrive ici, toutes les tentatives ont échoué
    raise Exception(f"Failed to fetch killmail {km_id} after {max_retries} attempts")
