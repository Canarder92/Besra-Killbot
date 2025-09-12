from __future__ import annotations

import base64
import time
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from src.config import settings

ESI_BASE = "https://esi.evetech.net"
LOGIN_BASE = "https://login.eveonline.com"
USER_AGENT = "KillMailBot/0.1 (+https://example.invalid)"  # à personnaliser si besoin


class TokenBucket:
    """Stockage mémoire pour access_token avec expiration"""

    def __init__(self):
        self.access_token: str | None = None
        self.expire_at: float = 0.0

    def is_valid(self) -> bool:
        return bool(self.access_token) and (time.time() < self.expire_at - 30)  # marge 30s

    def set(self, token: str, expires_in: int):
        self.access_token = token
        self.expire_at = time.time() + max(30, int(expires_in))


class ESIError(Exception):
    pass


class AsyncESIClient:
    def __init__(self):
        self._token = TokenBucket()
        self._client = httpx.AsyncClient(
            http2=True,
            timeout=httpx.Timeout(10.0, connect=10.0),
            headers={
                "Accept": "application/json",
                "Accept-Language": "en",
                "X-Compatibility-Date": settings.COMPAT_DATE,
                "User-Agent": USER_AGENT,
            },
            base_url=ESI_BASE,
        )

    async def aclose(self):
        await self._client.aclose()

    async def _ensure_token(self) -> None:
        if self._token.is_valid():
            return
        if (
            not settings.EVE_REFRESH_TOKEN
            or not settings.EVE_CLIENT_ID
            or not settings.EVE_CLIENT_SECRET
        ):
            raise ESIError("Missing EVE SSO credentials or refresh token.")

        data = {
            "grant_type": "refresh_token",
            "refresh_token": settings.EVE_REFRESH_TOKEN,
        }
        basic = base64.b64encode(
            f"{settings.EVE_CLIENT_ID}:{settings.EVE_CLIENT_SECRET}".encode()
        ).decode("ascii")
        headers = {
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        async with httpx.AsyncClient(http2=True, timeout=10.0) as s:
            resp = await s.post(f"{LOGIN_BASE}/v2/oauth/token", data=data, headers=headers)
            resp.raise_for_status()
            js = resp.json()
            access_token = js["access_token"]
            expires_in = int(js.get("expires_in", 1200))
            self._token.set(access_token, expires_in)

    @retry(
        wait=wait_exponential_jitter(initial=1, max=10),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type(httpx.RequestError),
        reraise=True,
    )
    async def _request(
        self, method: str, url: str, *, headers: dict[str, str] | None = None, **kwargs
    ) -> httpx.Response:
        await self._ensure_token()
        hdrs = {"Authorization": f"Bearer {self._token.access_token}"}
        if headers:
            hdrs.update(headers)
        resp = await self._client.request(method, url, headers=hdrs, **kwargs)

        # Gestion basique 429/5xx avec raise pour activer tenacity
        if resp.status_code in (429, 500, 502, 503, 504):
            resp.raise_for_status()
        return resp

    # --- public helpers ---

    async def get_json(
        self, url: str, *, headers: dict[str, str] | None = None, **kwargs
    ) -> dict | list:
        resp = await self._request("GET", url, headers=headers, **kwargs)
        if resp.status_code == 304:
            # L'appelant doit savoir gérer le 304
            return {"__not_modified__": True, "__etag__": resp.headers.get("ETag")}
        resp.raise_for_status()
        if "ETag" in resp.headers:
            data = resp.json()
            if isinstance(data, dict):
                data["__etag__"] = resp.headers["ETag"]
            return data
        return resp.json()

    async def post_json(
        self, url: str, json: Any, *, headers: dict[str, str] | None = None
    ) -> dict | list:
        resp = await self._request("POST", url, headers=headers, json=json)
        resp.raise_for_status()
        return resp.json()
