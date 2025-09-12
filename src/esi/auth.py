from __future__ import annotations

import base64
import hashlib
import secrets
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx

from src.config import settings

LOGIN_BASE = "https://login.eveonline.com"
REDIRECT_URI = f"http://localhost:{settings.CALLBACK_PORT}/callback"
SCOPE = "esi-killmails.read_corporation_killmails.v1"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return _b64url(digest)


class _AuthHandler(BaseHTTPRequestHandler):
    server_version = "KillMailBotAuth/0.1"

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return
        qs = urllib.parse.parse_qs(parsed.query)
        code = qs.get("code", [None])[0]
        state = qs.get("state", [None])[0]
        self.server.code = code  # type: ignore[attr-defined]
        self.server.state = state  # type: ignore[attr-defined]
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK. You can close this tab.")
        # shutdown soon
        threading.Thread(target=self.server.shutdown, daemon=True).start()

    def log_message(self, *args, **kwargs):
        # silence
        pass


def run_local_pkce() -> str:
    """
    Lance un mini serveur HTTP local et effectue le flow PKCE pour récupérer un refresh_token.
    Retourne le refresh_token (string).
    """
    verifier = _b64url(secrets.token_bytes(32))
    challenge = _code_challenge(verifier)
    state = _b64url(secrets.token_bytes(16))

    params = {
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "client_id": settings.EVE_CLIENT_ID,
        "scope": SCOPE,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    url = f"{LOGIN_BASE}/v2/oauth/authorize?{urllib.parse.urlencode(params)}"

    print("\n=== EVE SSO ===")
    print("Ouvre cette URL dans un navigateur (port-forward si headless) :\n")
    print(url, "\n")

    server = HTTPServer(("0.0.0.0", settings.CALLBACK_PORT), _AuthHandler)
    server.code = None  # type: ignore[attr-defined]
    server.state = None  # type: ignore[attr-defined]

    # Block jusqu'au callback
    server.serve_forever()

    code = server.code  # type: ignore[attr-defined]
    got_state = server.state  # type: ignore[attr-defined]

    if not code or got_state != state:
        raise RuntimeError("Auth failed or state mismatch.")

    # Échange du code contre tokens
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": settings.EVE_CLIENT_ID,
        "code_verifier": verifier,
        "redirect_uri": REDIRECT_URI,
    }

    with httpx.Client(timeout=10.0) as s:
        resp = s.post(f"{LOGIN_BASE}/v2/oauth/token", data=data)
        resp.raise_for_status()
        js = resp.json()
        refresh = js.get("refresh_token")
        if not refresh:
            raise RuntimeError("No refresh_token returned.")
        print("\nRefresh token:\n", refresh)
        print("\nAjoute-le à ton .env comme EVE_REFRESH_TOKEN.\n")
        return refresh


if __name__ == "__main__":
    if not settings.EVE_CLIENT_ID:
        raise SystemExit("EVE_CLIENT_ID manquant dans l'env.")
    run_local_pkce()
