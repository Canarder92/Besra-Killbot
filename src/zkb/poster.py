from __future__ import annotations

import asyncio

import httpx

from src.config import settings

POST_URL = "https://zkillboard.com/post/"


def _build_headers(user_agent: str | None) -> dict[str, str]:
    ua = user_agent or settings.ZKB_POST_USER_AGENT
    if not ua:
        # Sécurité : log si l'UA est manquant
        print("[zKill POST] Aucun User-Agent défini (ZKB_POST_USER_AGENT manquant dans .env)")
    return {
        "User-Agent": ua or "Unset-UA",
        "Accept-Encoding": "gzip",
        "Content-Type": "application/x-www-form-urlencoded",
    }


async def _post_worker(
    killmail_id: int, killmail_hash: str, *, user_agent: str | None = None
) -> None:
    """
    Tâche asynchrone qui envoie le kill à zKill.
    Ne lève pas vers l'appelant : log uniquement.
    """
    try:
        headers = _build_headers(user_agent)
        killmail_url = (
            f"https://esi.evetech.net/latest/killmails/{int(killmail_id)}/{killmail_hash}/"
        )
        data = {"killmailurl": killmail_url}

        async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
            resp = await client.post(POST_URL, data=data)

            # 302 = déjà présent / redirection côté zKill => on considère comme succès
            if resp.status_code == 302:
                # Optionnel: debug léger, sinon silence total
                # print(f"[zKill POST] Already present (302) for kill {killmail_id}")
                return

            # 2xx = succès
            if 200 <= resp.status_code < 300:
                return

            # Autres cas = on log (3xx≠302, 4xx, 5xx)
            body = (resp.text or "").strip()
            if len(body) > 300:
                body = body[:300] + "…"
            print(f"[zKill POST] Non-OK HTTP {resp.status_code} for kill {killmail_id} :: {body}")

    except Exception as e:
        # Ne bloque jamais l’exécution du bot : on log et c’est tout
        print(f"[zKill POST] error: {e}")


def post_main(killmail_id: int, killmail_hash: str, *, user_agent: str | None = None) -> None:
    """
    Lance l’envoi à zKill en arrière-plan (fire-and-forget) si ZKB_POST_ENABLE est actif.
    Fonction synchrone volontairement — pour pouvoir être appelée sans await.
    """
    if not getattr(settings, "ZKB_POST_ENABLE", False):
        return
    try:
        asyncio.get_running_loop()
        asyncio.create_task(_post_worker(killmail_id, killmail_hash, user_agent=user_agent))
    except RuntimeError:
        # Pas de boucle en cours (cas improbable dans le bot) : on ne fait rien
        print("[zKill POST] No running event loop; skipped")
