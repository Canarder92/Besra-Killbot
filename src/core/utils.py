def format_isk(value: float) -> str:
    """Format ISK with separators like zKill."""
    if value >= 1e9:
        return f"**{value/1e9:,.2f} B** ISK"
    if value >= 1e6:
        return f"**{value/1e6:,.2f} M** ISK"
    if value >= 1e3:
        return f"**{value/1e3:,.2f} k** ISK"
    return f"**{value:.0f}** ISK"


def discord_timestamp(dt, style: str = "f") -> str:
    """
    Return a Discord dynamic timestamp code:
      style: 't','T','d','D','f','F','R'  (Discord render codes)
      default 'f' -> 'Aujourd’hui à 14:15' (selon locale utilisateur)
    """
    epoch = int(dt.timestamp())
    return f"<t:{epoch}:{style}>"
