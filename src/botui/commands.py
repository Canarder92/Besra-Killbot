# src/botui/commands.py
from __future__ import annotations

import traceback
from collections.abc import Mapping
from typing import TypeVar

import discord
import httpx
from discord import app_commands
from discord.errors import Forbidden, NotFound
from discord.errors import HTTPException as DiscordHTTPException

from src.botui.embeds import build_embed_insight5
from src.config import settings
from src.core.prices_cache import PricesCache
from src.core.pricing import compute_killmail_value
from src.esi.client import AsyncESIClient
from src.esi.killmails import fetch_killmail_details, fetch_recent_killmails
from src.esi.universe import get_region_id_for_system, resolve_names

# ---------------------- Helpers typés ----------------------

_T = TypeVar("_T")


def dict_get_opt(m: Mapping[int, _T], key: int | None) -> _T | None:
    """Comme m.get(key) mais accepte une clé optionnelle sans faire râler l'analyse statique."""
    return m.get(key) if key is not None else None


def _explain_http_status(code: int) -> str:
    if code in (401, 403):
        part1 = "Authentification EVE invalide (token expiré,"
        part2 = " client_id/secret erronés, ou scope manquant)."
        return part1 + part2
    if code in (420, 429):
        return "Limite de débit ESI atteinte (rate limit)."
    if 500 <= code <= 599:
        return "Le serveur EVE (ESI) est en erreur (5xx)."
    if code == 404:
        return "Ressource introuvable (killmail non visible/supprimé ?)."
    return f"Réponse ESI inattendue (HTTP {code})."


def _render_success_report(steps: list[tuple[str, str]]) -> str:
    lines = ["**✅ /test_post terminé**"]
    for nom, msg in steps:
        lines.append(f"- **{nom}** : {msg}")
    return "\n".join(lines)


def _render_failure_report(steps: list[tuple[str, str]], exc: BaseException) -> str:
    lines = ["**❌ Échec /test_post**"]
    for nom, msg in steps:
        lines.append(f"- **{nom}** : {msg}")
    tb = "".join(traceback.format_exception(exc))
    if len(tb) > 1500:
        tb = tb[:1500] + "\n…(tronqué)…"
    lines.append("\n**Détails techniques (trace):**")
    lines.append(f"```py\n{tb}\n```")
    return "\n".join(lines)


# ---------------------- CommandTree ----------------------

_tree: app_commands.CommandTree | None = None
_commands_installed = False  # évite une double install


def _get_tree(client: discord.Client) -> app_commands.CommandTree:
    global _tree
    if _tree is None:
        _tree = app_commands.CommandTree(client)
    return _tree


async def install_commands(client: discord.Client) -> None:
    global _commands_installed
    if _commands_installed:
        return

    tree = _get_tree(client)

    @tree.command(name="ping", description="Ping du bot")
    async def ping(interaction: discord.Interaction):
        await interaction.response.send_message("Pong!", ephemeral=True)

    @tree.command(name="status", description="Statut rapide")
    async def status(interaction: discord.Interaction):
        """
        Vérifie que le bot est vivant et que l'API EVE (ESI) répond.
        Requête : GET https://esi.evetech.net/status (avec X-Compatibility-Date via client)
        """
        await interaction.response.defer(ephemeral=True)
        esi = AsyncESIClient()
        try:
            try:
                await esi.get_json("/status")
                await interaction.followup.send(
                    "Bot : Ok\nCommunication avec l'Api de Eve online : Ok",
                    ephemeral=True,
                )
            except httpx.RequestError:
                await interaction.followup.send(
                    "**Status**\n"
                    "- **Bot** : Ok\n"
                    "- **Communication ESI** : ❌ Le serveur EVE ne répond pas (réseau/timeout)",
                    ephemeral=True,
                )
            except httpx.HTTPStatusError as e:
                msg = _explain_http_status(e.response.status_code)
                await interaction.followup.send(
                    f"**Status**\n- **Bot** : Ok\n- **Communication ESI** : ❌ {msg}",
                    ephemeral=True,
                )
            except Exception as e:
                tb = "".join(traceback.format_exception(e))
                if len(tb) > 1000:
                    tb = tb[:1000] + "\n…(tronqué)…"
                part1 = "**Status**\n- **Bot** : Ok\n- **Communication ESI** : ❌ "
                await interaction.followup.send(
                    part1 + f"Erreur inattendue\n```py\n{tb}\n```",
                    ephemeral=True,
                )
        finally:
            await esi.aclose()

    @tree.command(name="test_post", description="Récupère le 1er killmail ESI et le poste ici")
    async def test_post(interaction: discord.Interaction):
        """
        Chaîne complète :
          1) GET /corporations/{id}/killmails/recent?page=1
          2) GET /killmails/{id}/{hash}
          3) Résolution noms /universe/names + région
          4) Pricing via /markets/{region}/history
          5) Construction embed Insight 5
          6) Publication dans le channel
        Avec rapport d’erreurs détaillé.
        """
        await interaction.response.defer(ephemeral=True)

        steps: list[tuple[str, str]] = []
        corp_id = settings.CORPORATION_ID
        if not corp_id:
            await interaction.followup.send(
                _render_failure_report(
                    [("Configuration", "⚠️ CORPORATION_ID manquant dans .env")], RuntimeError()
                ),
                ephemeral=True,
            )
            return

        esi = AsyncESIClient()
        prices = PricesCache("data/prices.json")

        try:
            # 1) Récents de la corpo
            try:
                status, _etag, refs = await fetch_recent_killmails(
                    esi, int(corp_id), etag=None, force_body=True
                )
                if status != "ok":
                    steps.append(("Lecture récents", "❌ Statut ESI inattendu"))
                    raise RuntimeError("fetch_recent_killmails returned non-ok")
                if not refs:
                    steps.append(("Lecture récents", "❌ Aucun killmail récent trouvé"))
                    raise RuntimeError("No recent killmails")
                steps.append(("Lecture récents", f"OK ({len(refs)} éléments)"))
            except httpx.RequestError:
                steps.append(
                    ("Lecture récents", "❌ Le serveur EVE ne répond pas (réseau/timeout)")
                )
                raise
            except httpx.HTTPStatusError as e:
                steps.append(
                    ("Lecture récents", f"❌ {_explain_http_status(e.response.status_code)}")
                )
                raise
            except Exception:
                steps.append(("Lecture récents", "❌ Erreur inattendue"))
                raise

            first = refs[0]

            # 2) Détails du KM
            try:
                km = await fetch_killmail_details(esi, first.killmail_id, first.killmail_hash)
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
                ids = set()
                if km.victim.character_id is not None:
                    ids.add(km.victim.character_id)
                ids.add(km.victim.corporation_id)
                if km.victim.alliance_id is not None:
                    ids.add(km.victim.alliance_id)

                fb = next(
                    (a for a in km.attackers if a.final_blow),
                    km.attackers[0] if km.attackers else None,
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

                # Utilisation du helper pour toutes les clés optionnelles
                system_name = (
                    dict_get_opt(name_map, km.solar_system_id) or f"System {km.solar_system_id}"
                )
                ship_name = (
                    dict_get_opt(name_map, km.victim.ship_type_id)
                    or f"Type {km.victim.ship_type_id}"
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

            # 5) Pricing
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
                    (
                        "Estimation de la valeur",
                        f"❌ {_explain_http_status(e.response.status_code)}",
                    )
                )
                raise
            except Exception:
                steps.append(("Estimation de la valeur", "❌ Erreur inattendue"))
                raise

            # 6) Embed
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

            # 7) Envoi
            try:
                await interaction.followup.send(embed=embed, ephemeral=False)
                steps.append(("Publication Discord", "OK"))
                await interaction.followup.send(
                    _render_success_report(steps),
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
                _render_failure_report(steps, e),
                ephemeral=True,
            )
        finally:
            await esi.aclose()

    @tree.command(name="force_refresh_prices", description="Purge des prix en cache (tout)")
    async def force_refresh_prices(interaction: discord.Interaction):
        await interaction.response.send_message(
            "Hop hop hop petit margoulin, qu'est ce que tu essayais de faire?.", ephemeral=True
        )

    # Sync global
    await tree.sync()
    _commands_installed = True
