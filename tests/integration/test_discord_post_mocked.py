import types
from datetime import datetime

import discord
import pytest

from src.botui.embeds import build_embed_insight5
from src.core.models import Attacker, Killmail, Victim
from src.core.utils import format_isk


class DummyChannel:
    def __init__(self):
        self.last_embed: discord.Embed | None = None

    async def send(self, *, embed: discord.Embed):
        self.last_embed = embed
        return types.SimpleNamespace(id=42)


@pytest.mark.asyncio
async def test_send_embed_to_channel():
    channel = DummyChannel()

    km = Killmail(
        killmail_id=129783397,
        killmail_hash="deadbeef",
        killmail_time=datetime.fromisoformat("2025-09-10T12:33:06+00:00"),
        solar_system_id=30004563,
        victim=Victim(
            character_id=2123410399,
            corporation_id=98420562,
            alliance_id=1900696668,
            ship_type_id=11129,
            damage_taken=463,
            items=[],
        ),
        attackers=[
            Attacker(
                character_id=2117825129,
                corporation_id=98092494,
                ship_type_id=20125,
                final_blow=True,
                damage_done=463,
            )
        ],
    )

    total_value = 1_000_000.0
    dropped_value = 250_000.0

    embed = build_embed_insight5(
        km,
        victim_name="Victim",
        victim_corp_name="Victim Corp",
        victim_all_name="Victim All",
        final_name="Final Blow",
        final_corp_name="Killer Corp",
        final_all_name=None,
        system_name="L-A5XP",
        region_name="Fountain",
        ship_name="Shuttle",
        final_ship_name="Raven",
        total_value=total_value,
        is_kill=True,
        region_id=10000058,
        dropped_value=dropped_value,
    )

    msg = await channel.send(embed=embed)

    # Assure Pylance que last_embed n'est plus None
    assert isinstance(channel.last_embed, discord.Embed)

    # Assure Pylance que url n'est pas None (discord.Embed.url est Optional[str])
    assert channel.last_embed.url is not None
    assert channel.last_embed.url.endswith("/129783397/")
    assert msg.id == 42

    # Final Blow field contient la Value totale ET la ligne Drop
    ff = channel.last_embed.fields[1]
    assert ff.value is not None
    assert f"Value: {format_isk(total_value)}" in ff.value
    assert f"Drop:  {format_isk(dropped_value)}" in ff.value
