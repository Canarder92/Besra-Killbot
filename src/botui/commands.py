# src/botui/commands.py
from __future__ import annotations

import discord
import httpx
from discord import app_commands

from src.botui.test_runner import run_test_post
from src.esi.client import AsyncESIClient

_tree: app_commands.CommandTree | None = None
_commands_installed = False


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
                    "**Status**\n- **Bot** : Ok\n- **Communication ESI** : "
                    "❌ Le serveur EVE ne répond pas (réseau/timeout)",
                    ephemeral=True,
                )
            except httpx.HTTPStatusError as e:
                await interaction.followup.send(
                    f"**Status**\n- **Bot** : Ok\n- **Communication ESI** : "
                    f"❌ HTTP {e.response.status_code}",
                    ephemeral=True,
                )
            except Exception as e:
                await interaction.followup.send(
                    f"**Status**\n- **Bot** : Ok\n- **Communication ESI** : ❌ "
                    f"Erreur inattendue\n```py\n{e}\n```",
                    ephemeral=True,
                )
        finally:
            await esi.aclose()

    @tree.command(
        name="test_post_esi", description="Poste le kill le plus récent via ESI (diagnostic)."
    )
    async def test_post_esi(interaction: discord.Interaction):
        await run_test_post(interaction, source="esi")

    @tree.command(
        name="test_post_zkill",
        description="Poste le kill le plus récent via zKill (diagnostic, via ESI).",
    )
    async def test_post_zkill(interaction: discord.Interaction):
        await run_test_post(interaction, source="zkill")

    @tree.command(
        name="zkill_post",
        description="Active/Désactive la soumission automatique à zKillboard (volatile)",
    )
    @app_commands.describe(action="enable | disable | status")
    async def zkill_post(interaction: discord.Interaction, action: str):
        from src.config import settings

        a = (action or "status").lower().strip()
        if a in ("enable", "on", "true", "1"):
            settings.ZKB_POST_ENABLE = True
            await interaction.response.send_message(
                "✅ zKill POST activé (non persistant).", ephemeral=True
            )
        elif a in ("disable", "off", "false", "0"):
            settings.ZKB_POST_ENABLE = False
            await interaction.response.send_message(
                "⛔ zKill POST désactivé (non persistant).", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"État actuel : {'activé ✅' if settings.ZKB_POST_ENABLE else 'désactivé ⛔'}.\n"
                "Utilisation : /zkill_post action:<enable|disable|status>",
                ephemeral=True,
            )

    await tree.sync()
    _commands_installed = True
