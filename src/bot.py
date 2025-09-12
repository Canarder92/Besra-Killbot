# src/bot.py
from __future__ import annotations

import discord

from src.botui.commands import install_commands
from src.config import settings
from src.scheduler.loop import start_scheduler

intents = discord.Intents.none()
intents.guilds = True
intents.messages = True

client = discord.Client(intents=intents)


@client.event
async def on_ready():
    user = client.user
    assert user is not None
    print(f"Logged in as {user} (ID: {user.id})")

    try:
        await install_commands(client)  # ⬅️ plus de client.tree ici
    except Exception as e:
        print(f"Slash commands setup failed: {e}")

    try:
        channel_id = int(settings.DISCORD_CHANNEL_ID)
        await start_scheduler(client, channel_id)
    except Exception as e:
        print(f"Scheduler start failed: {e}")


def main():
    token = settings.DISCORD_TOKEN
    if not token:
        raise SystemExit("DISCORD_TOKEN manquant dans .env")
    client.run(token, log_handler=None)


if __name__ == "__main__":
    main()
