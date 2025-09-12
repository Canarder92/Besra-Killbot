from datetime import datetime

import discord

from src.botui.embeds import build_embed_insight5
from src.core.models import Attacker, Killmail, Victim
from src.core.utils import format_isk


def make_minimal_km():
    return Killmail(
        killmail_id=129775987,
        killmail_hash="abc123",
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
                alliance_id=None,
                ship_type_id=20125,
                damage_done=463,
                final_blow=True,
            )
        ],
    )


def test_embed_contains_expected_links():
    km = make_minimal_km()
    total_value = 3_210_000.0
    dropped_value = 420_000.0

    embed = build_embed_insight5(
        km,
        victim_name="Victim Name",
        victim_corp_name="Victim Corp",
        victim_all_name="Victim Alliance",
        final_name="Killer",
        final_corp_name="Killer Corp",
        final_all_name=None,
        system_name="L-A5XP",
        region_name="Fountain",
        ship_name="Caldari Shuttle",
        final_ship_name="Raven",
        total_value=total_value,
        is_kill=True,
        region_id=10000058,
        dropped_value=dropped_value,
    )

    assert isinstance(embed, discord.Embed)
    assert embed.url == "https://zkillboard.com/kill/129775987/"

    # author.name est Optional[str]
    assert embed.author.name is not None
    assert "Fountain" in embed.author.name
    assert "L-A5XP" in embed.author.name

    # --- Victim column (renommée "Victime ..." avec padding) ---
    vf = embed.fields[0]
    assert vf.name is not None
    assert vf.name.strip().startswith("Victime")
    assert vf.value is not None
    assert "Caldari Shuttle" in vf.value
    assert "Victim Name" in vf.value
    assert "Victim Corp" in vf.value
    assert "Victim Alliance" in vf.value
    assert "https://zkillboard.com/character/2123410399/" in vf.value
    assert "https://zkillboard.com/corporation/98420562/" in vf.value
    assert "https://zkillboard.com/alliance/1900696668/" in vf.value

    # Les liens System/Dotlan + Region sont dans Victim
    assert "http://evemaps.dotlan.net/map/Fountain/L-A5XP" in vf.value
    assert "https://zkillboard.com/region/10000058/" in vf.value

    # La Value N’EST PAS dans Victim (elle est dans Final Blow)
    assert f"Value: {format_isk(total_value)}" not in vf.value
    # Et Drop non plus (dans ton embed actuel, Drop est dans Final Blow)
    assert f"Drop:  {format_isk(dropped_value)}" not in vf.value

    # --- Final Blow column (nom avec padding, on teste avec startswith) ---
    ff = embed.fields[1]
    assert ff.name is not None
    assert ff.name.strip().startswith("Final Blow")
    assert ff.value is not None
    assert "Killer" in ff.value
    assert "Killer Corp" in ff.value
    assert "Raven" in ff.value
    assert "https://zkillboard.com/character/2117825129/" in ff.value

    # Comme involved == 1, on doit voir "Solo !" au lieu de (+N)
    assert "Solo !" in ff.value

    # La Value ET le Drop sont maintenant dans la colonne Final Blow
    assert f"Value: {format_isk(total_value)}" in ff.value
    assert f"Drop:  {format_isk(dropped_value)}" in ff.value

    # Plus de 3e field "Details" et plus de footer avec la value
    assert len(embed.fields) == 2
    assert embed.footer.text in (None, "")
