import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

# Charge le .env situé à la racine du projet, où que soit lancé Python
ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


class Settings(BaseModel):
    DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN", "")
    DISCORD_CHANNEL_ID: str = os.getenv("DISCORD_CHANNEL_ID", "")
    EVE_CLIENT_ID: str = os.getenv("EVE_CLIENT_ID", "")
    EVE_CLIENT_SECRET: str = os.getenv("EVE_CLIENT_SECRET", "")
    EVE_REFRESH_TOKEN: str = os.getenv("EVE_REFRESH_TOKEN", "")
    CORPORATION_ID: str = os.getenv("CORPORATION_ID", "")
    CALLBACK_PORT: int = int(os.getenv("CALLBACK_PORT", "53682"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    POLL_INTERVAL_SECONDS: int = int(os.getenv("POLL_INTERVAL_SECONDS", "120"))
    CLEANUP_INTERVAL_MINUTES: int = int(os.getenv("CLEANUP_INTERVAL_MINUTES", "60"))
    MARKET_REGION_ID: int = int(os.getenv("MARKET_REGION_ID", "10000002"))
    PRICE_TTL_DAYS: int = int(os.getenv("PRICE_TTL_DAYS", "7"))
    COMPAT_DATE: str = os.getenv("COMPAT_DATE", "2025-08-26")
    TIMEZONE: str = os.getenv("TIMEZONE", "UTC")
    ZKB_ENABLE: bool = os.getenv("ZKB_ENABLE", "false").lower() in ("1", "true", "yes")
    ZKB_PAGES: int = int(os.getenv("ZKB_PAGES", "1"))
    ZKB_EVERY_N: int = int(os.getenv("ZKB_EVERY_N", "3"))  # => 1 fois sur 3 cycles ESI


settings = Settings()
