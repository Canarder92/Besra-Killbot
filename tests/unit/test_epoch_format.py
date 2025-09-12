from datetime import UTC, datetime

from src.core.utils import discord_timestamp, format_isk


def test_discord_timestamp_f_style():
    dt = datetime(2025, 9, 10, 14, 33, 6, tzinfo=UTC)
    ts = discord_timestamp(dt, style="f")
    # <t:TIMESTAMP:f>
    assert ts.startswith("<t:")
    assert ts.endswith(":f>")
    # epoch doit être cohérent
    epoch_str = ts.split(":")[1]
    assert epoch_str.isdigit()
    assert int(epoch_str) == int(dt.timestamp())


def test_format_isk_ranges():
    assert format_isk(999) == "**999** ISK"
    assert format_isk(1_200) == "**1.20 k** ISK"
    assert format_isk(12_345_678) == "**12.35 M** ISK"
    assert format_isk(9_876_543_210) == "**9.88 B** ISK"
