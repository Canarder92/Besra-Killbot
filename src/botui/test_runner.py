from __future__ import annotations

import traceback
from collections.abc import Mapping
from typing import TypeVar

import discord
import httpx
from discord.errors import Forbidden, NotFound
from discord.errors import HTTPException as DiscordHTTPException

from src.botui.embeds import build_embed_insight5
from src.config import settings
from src.core.prices_cache import PricesCache
from src.core.pricing import compute_killmail_value
from src.esi.client import AsyncESIClient
from src.esi.killmails import fetch_killmail_details, fetch_recent_killmails
from src.esi.universe import get_region_id_for_system, resolve_names
from src.zkb.zkill import fetch_corporation_killrefs

_T = TypeVar("_T")


def dict_get_opt(m: Mapping[int, _T], key: int | None) -> _T | None:
    return m.get(key) if key is not None else None


def _explain_http_status(code: int) -> str:
    if code in (401, 403):
        return (
            "Authentification EVE invalide (token expiré,"
            " client_id/secret erronés, ou scope manquant)."
        )
    if code in (420, 429):
        return "Limite de débit ESI atteinte (rate limit)."
    if 500 <= code <= 599:
        return "Le serveur EVE (ESI) est en erreur (5xx)."
    if code == 404:
        return "Ressource introuvable (killmail non visible/supprimé ?)."
    return f"Réponse ESI inattendue (HTTP {code})."


def _render_success_report(title: str, steps: list[tuple[str, str]]) -> str:
    lines = [f"**✅ {title}**"]
    for nom, msg in steps:
        lines.append(f"- **{nom}** : {msg}")
    return "\n".join(lines)


def _render_failure_report(title: str, steps: list[tuple[str, str]], exc: BaseException) -> str:
    lines = [f"**❌ {title}**"]
    for nom, msg in steps:
        lines.append(f"- **{nom}** : {msg}")
    tb = "".join(traceback.format_exception(exc))
    if len(tb) > 1500:
        tb = tb[:1500] + "\n…(tronqué)…"
    lines.append("\n**Détails techniques (trace):**")
    lines.append(f"```py\n{tb}\n```")
    return "\n".join(lines)


async def _get_first_esi_ref(esi: AsyncESIClient, corp_id: int, steps: list[tuple[str, str]]):
    try:
        status, _etag, refs = await fetch_recent_killmails(esi, corp_id, etag=None, force_body=True)
        if status != "ok":
            steps.append(("Lecture récents", "❌ Statut ESI inattendu"))
            raise RuntimeError("fetch_recent_killmails returned non-ok")
        if not refs:
            steps.append(("Lecture récents", "❌ Aucun killmail récent trouvé"))
            raise RuntimeError("No recent killmails")
        steps.append(("Lecture récents", f"OK ({len(refs)} éléments)"))
        return refs[0]
    except httpx.RequestError:
        steps.append(("Lecture récents", "❌ Le serveur EVE ne répond pas (réseau/timeout)"))
        raise
    except httpx.HTTPStatusError as e:
        steps.append(("Lecture récents", f"❌ {_explain_http_status(e.response.status_code)}"))
        raise
    except Exception:
        steps.append(("Lecture récents", "❌ Erreur inattendue"))
        raise


async def _get_first_zkb_ref(corp_id: int, pages: int, steps: list[tuple[str, str]]):
    try:
        refs = await fetch_corporation_killrefs(corp_id, pages=pages)
        if not refs:
            steps.append(("Lecture récents", "❌ Aucun killmail récent trouvé"))
            raise RuntimeError("No recent killmails from zKill")
        steps.append(("Lecture récents", f"OK ({len(refs)} éléments)"))
        r0 = refs[0]
        km_id = r0["killmail_id"] if isinstance(r0, dict) else r0.killmail_id
        km_hash = r0["killmail_hash"] if isinstance(r0, dict) else r0.killmail_hash
        return int(km_id), str(km_hash)
    except Exception:
        steps.append(("Lecture récents", "❌ Erreur (zKill)"))
        raise


async def run_test_post(interaction: discord.Interaction, source: str) -> None:
    """
    source: "esi" | "zkill"
    - Récupère le kill le plus récent depuis ESI ou zKill
    - Passe par le pipeline standard (détails ESI -> noms -> pricing -> embed)
    - Poste l'embed dans le channel, et renvoie un rapport éphémère
    """
    title = "/test_post_esi terminé" if source == "esi" else "/test_post_zkill terminé"
    await interaction.response.defer(ephemeral=True)

    steps: list[tuple[str, str]] = []
    corp_id = settings.CORPORATION_ID
    if not corp_id:
        await interaction.followup.send(
            _render_failure_report(
                title, [("Configuration", "⚠️ CORPORATION_ID manquant dans .env")], RuntimeError()
            ),
            ephemeral=True,
        )
        return

    esi = AsyncESIClient()
    prices = PricesCache("data/prices.json")

    try:
        # 1) Lecture récents -> choix du premier
        if source == "esi":
            first = await _get_first_esi_ref(esi, int(corp_id), steps)
            km_id, km_hash = first.killmail_id, first.killmail_hash
        else:
            if not getattr(settings, "ZKB_ENABLE", False):
                steps.append(("Configuration zKill", "❌ ZKB_ENABLE=false"))
                raise RuntimeError("zKill disabled")
            pages = int(getattr(settings, "ZKB_PAGES", 1))
            km_id, km_hash = await _get_first_zkb_ref(int(corp_id), pages, steps)

        # 2) Détails du killmail via ESI (même chemin dans les deux cas)
        try:
            km = await fetch_killmail_details(esi, km_id, km_hash)
            steps.append(("Détails du killmail", "OK"))
        except httpx.RequestError:
            steps.append(
                ("Détails du killmail", "❌ Le serveur EVE ne répond pas (réseau/timeout)")
            )
            raise
        except httpx.HTTPStatusError as e:
            steps.append(
                ("Détails du killmail", f"❌ {_explain_http_status(e.response.status_code)}")
            )
            raise
        except Exception:
            steps.append(("Détails du killmail", "❌ Réponse ESI inattendue / parsing"))
            raise

        # 3) Kill ou Loss ?
        is_kill = any(a.corporation_id == int(corp_id) for a in km.attackers)
        steps.append(("Détermination kill/loss", "OK"))

        # 4) Résolution des noms + région
        try:
            ids: set[int] = set()
            if km.victim.character_id is not None:
                ids.add(km.victim.character_id)
            ids.add(km.victim.corporation_id)
            if km.victim.alliance_id is not None:
                ids.add(km.victim.alliance_id)

            fb = next(
                (a for a in km.attackers if a.final_blow), km.attackers[0] if km.attackers else None
            )
            if fb:
                if fb.character_id is not None:
                    ids.add(fb.character_id)
                if fb.corporation_id is not None:
                    ids.add(fb.corporation_id)
                all_id = getattr(fb, "alliance_id", None)
                if all_id is not None:
                    ids.add(all_id)
                if fb.ship_type_id is not None:
                    ids.add(fb.ship_type_id)

            ids.add(km.victim.ship_type_id)
            ids.add(km.solar_system_id)

            region_id: int | None = await get_region_id_for_system(esi, km.solar_system_id)
            region_name = "Unknown Region"
            if region_id is not None:
                ids.add(region_id)

            name_map: dict[int, str] = {}
            try:
                names = await resolve_names(esi, ids)
                for e in names:
                    name_map[int(e["id"])] = e["name"]
                steps.append(("Résolution des noms", "OK"))
            except Exception:
                steps.append(("Résolution des noms", "⚠️ Échec (fallback IDs)"))

            system_name = (
                dict_get_opt(name_map, km.solar_system_id) or f"System {km.solar_system_id}"
            )
            ship_name = (
                dict_get_opt(name_map, km.victim.ship_type_id) or f"Type {km.victim.ship_type_id}"
            )
            final_ship_name = dict_get_opt(name_map, fb.ship_type_id if fb else None)
            victim_name = dict_get_opt(name_map, km.victim.character_id)
            victim_corp_name = dict_get_opt(name_map, km.victim.corporation_id)
            victim_all_name = dict_get_opt(name_map, km.victim.alliance_id)
            final_name = dict_get_opt(name_map, fb.character_id if fb else None) if fb else None
            final_corp_name = (
                dict_get_opt(name_map, fb.corporation_id if fb else None) if fb else None
            )
            final_all_name = (
                dict_get_opt(name_map, getattr(fb, "alliance_id", None) if fb else None)
                if fb
                else None
            )
            if region_id is not None:
                region_name = dict_get_opt(name_map, region_id) or region_name

        except httpx.RequestError:
            steps.append(
                ("Résolution des noms", "❌ Le serveur EVE ne répond pas (réseau/timeout)")
            )
            raise
        except httpx.HTTPStatusError as e:
            steps.append(
                ("Résolution des noms", f"❌ {_explain_http_status(e.response.status_code)}")
            )
            raise
        except Exception:
            steps.append(("Résolution des noms", "❌ Erreur inattendue"))
            raise

        # 5) Estimation de la valeur
        try:
            total_value = await compute_killmail_value(km, prices)
            steps.append(("Estimation de la valeur", "OK"))
        except httpx.RequestError:
            steps.append(
                ("Estimation de la valeur", "❌ Le serveur EVE ne répond pas (réseau/timeout)")
            )
            raise
        except httpx.HTTPStatusError as e:
            steps.append(
                ("Estimation de la valeur", f"❌ {_explain_http_status(e.response.status_code)}")
            )
            raise
        except Exception:
            steps.append(("Estimation de la valeur", "❌ Erreur inattendue"))
            raise

        # 6) Construction de l’embed
        try:
            embed = build_embed_insight5(
                km,
                victim_name=victim_name,
                victim_corp_name=victim_corp_name,
                victim_all_name=victim_all_name,
                final_name=final_name,
                final_corp_name=final_corp_name,
                final_all_name=final_all_name,
                system_name=system_name,
                region_name=region_name,
                ship_name=ship_name,
                final_ship_name=final_ship_name,
                total_value=total_value,
                is_kill=is_kill,
                region_id=region_id,
            )
            steps.append(("Construction de l’embed", "OK"))
        except Exception:
            steps.append(("Construction de l’embed", "❌ Impossible d’établir un embed"))
            raise

        # 7) Publication dans le channel (publique) + rapport (éphémère)
        try:
            await interaction.followup.send(embed=embed, ephemeral=False)
            steps.append(("Publication Discord", "OK"))
            await interaction.followup.send(
                _render_success_report(title, steps),
                ephemeral=True,
            )
        except Forbidden:
            steps.append(
                (
                    "Publication Discord",
                    "❌ Permissions insuffisantes (Send Messages / Embed Links)",
                )
            )
            raise
        except NotFound:
            steps.append(("Publication Discord", "❌ Channel introuvable"))
            raise
        except DiscordHTTPException as e:
            steps.append(("Publication Discord", f"❌ Erreur HTTP Discord ({e.status})"))
            raise

    except Exception as e:
        await interaction.followup.send(
            _render_failure_report(title, steps, e),
            ephemeral=True,
        )
    finally:
        await esi.aclose()
