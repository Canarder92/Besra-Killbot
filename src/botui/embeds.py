from __future__ import annotations

from zoneinfo import ZoneInfo

import discord

from src.botui.colors import KILL_GREEN, LOSS_RED
from src.config import settings
from src.core.models import Killmail
from src.core.utils import format_isk

# --------- Links helpers ----------


def zkill_character(char_id: int) -> str:
    return f"https://zkillboard.com/character/{char_id}/"


def zkill_corporation(corp_id: int) -> str:
    return f"https://zkillboard.com/corporation/{corp_id}/"


def corp_logo_url(corp_id: int, size: int = 64) -> str:
    return f"https://images.evetech.net/corporations/{corp_id}/logo?size={size}"


def zkill_alliance(all_id: int) -> str:
    return f"https://zkillboard.com/alliance/{all_id}/"


def zkill_killmail(killmail_id: int) -> str:
    return f"https://zkillboard.com/kill/{killmail_id}/"


def zkill_ship(type_id: int) -> str:
    return f"https://zkillboard.com/ship/{type_id}/"


def zkill_region(region_id: int) -> str:
    return f"https://zkillboard.com/region/{region_id}/"


def dotlan_map(region_name: str, system_name: str) -> str:
    region = region_name.replace(" ", "_")
    system = system_name.replace(" ", "_")
    return f"http://evemaps.dotlan.net/map/{region}/{system}"


def zkill_related(system_id: int, killmail_time) -> str:
    """Generate zkillboard related kills link for system and time."""
    dt = killmail_time.astimezone(ZoneInfo("UTC"))
    # Format: YYYYMMDDHH00
    time_str = dt.strftime("%Y%m%d%H00")
    return f"https://zkillboard.com/related/{system_id}/{time_str}/"


def ship_render_url(type_id: int) -> str:
    # CCP images
    return f"https://images.evetech.net/types/{type_id}/render?size=128"


def row_link(label: str, text: str | None, url: str | None) -> str:
    if text and url:
        return f"{label}: [{text}]({url})"
    if text:
        return f"{label}: {text}"
    return f"{label}: —"


# --------- Main embed builder ----------


def build_embed_insight5(
    km: Killmail,
    *,
    victim_name: str | None,
    victim_corp_name: str | None,
    victim_all_name: str | None,
    final_name: str | None,
    final_corp_name: str | None,
    final_all_name: str | None,
    system_name: str,
    region_name: str,
    ship_name: str,
    final_ship_name: str | None,
    total_value: float,
    is_kill: bool,
    region_id: int | None = None,
    dropped_value: float = 0.0,
) -> discord.Embed:
    status = "Kill" if is_kill else "Loss"
    header = f"{status}: {ship_name} destroyed in {system_name}({region_name})"
    color = KILL_GREEN if is_kill else LOSS_RED
    url = zkill_killmail(km.killmail_id)

    # Pas de title pour éviter la grande police
    embed = discord.Embed(colour=color, url=url)

    # Affiche la ligne en "author" avec l'icône de la corporation victime
    embed.set_author(name=header, url=url, icon_url=corp_logo_url(km.victim.corporation_id))

    # Thumbnail: ship
    embed.set_thumbnail(url=ship_render_url(km.victim.ship_type_id))

    # --- Victim column ---
    v_lines = []
    v_lines.append(row_link("Ship", ship_name, zkill_ship(km.victim.ship_type_id)))
    v_lines.append(
        row_link(
            "Pilot",
            victim_name,
            zkill_character(km.victim.character_id) if km.victim.character_id else None,
        )
    )
    v_lines.append(row_link("Corp", victim_corp_name, zkill_corporation(km.victim.corporation_id)))
    if km.victim.alliance_id:
        v_lines.append(row_link("Alliance", victim_all_name, zkill_alliance(km.victim.alliance_id)))
    else:
        v_lines.append("Alliance: —")

    # Région cliquable vers zKill si on a l'ID
    region_part = (
        f"([{region_name}]({zkill_region(region_id)}))" if region_id else f"({region_name})"
    )
    v_lines.append(f"System: [{system_name}]({dotlan_map(region_name, system_name)}) {region_part}")
    date_tz = km.killmail_time.astimezone(ZoneInfo(settings.TIMEZONE))

    # Generate related kills link
    related_link = zkill_related(km.solar_system_id, km.killmail_time)
    v_lines.append(f"Date:  {date_tz.strftime('%d/%m/%Y - %Hh%M')} - [R]({related_link})")

    embed.add_field(
        name="Victime ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ",
        value="\n".join(v_lines),
        inline=True,
    )

    # --- Final Blow column ---
    involved = km.involved_count()
    fb = next((a for a in km.attackers if a.final_blow), km.attackers[0] if km.attackers else None)
    f_lines = []
    if fb and fb.ship_type_id and final_ship_name:
        if involved == 1:
            f_lines.append(
                row_link("Ship", final_ship_name, zkill_ship(fb.ship_type_id)) + " (solo)"
            )
        else:
            f_lines.append(
                row_link("Ship", final_ship_name, zkill_ship(fb.ship_type_id))
                + " (+"
                + str(involved - 1)
                + ")"
            )
    else:
        f_lines.append("Ship: —")
    f_lines.append(
        row_link(
            "Pilot",
            final_name,
            zkill_character(fb.character_id) if (fb and fb.character_id) else None,
        )
    )
    f_lines.append(
        row_link(
            "Corp",
            final_corp_name,
            zkill_corporation(fb.corporation_id) if (fb and fb.corporation_id) else None,
        )
    )
    if fb and fb.alliance_id:
        f_lines.append(row_link("Alliance", final_all_name, zkill_alliance(fb.alliance_id)))
    else:
        f_lines.append("Alliance: —")
    f_lines.append(f"Drop:  {format_isk(dropped_value)}")
    f_lines.append(f"Value: {format_isk(total_value)}")

    embed.add_field(
        name="Final Blow  ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎",
        value="\n".join(f_lines),
        inline=True,
    )
    return embed
