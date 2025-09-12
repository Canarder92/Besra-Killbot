[![GitHub release](https://img.shields.io/github/v/release/Canarder92/Besra-Killbot?logo=github)](https://github.com/Canarder92/Besra-Killbot/releases)
[![Docker Image Version](https://img.shields.io/docker/v/ghcr.io/canarder92/besra-killbot?label=ghcr.io&logo=docker)](https://ghcr.io/canarder92/besra-killbot:latest)
[![CI](https://github.com/Canarder92/Besra-Killbot/actions/workflows/release.yml/badge.svg)](https://github.com/Canarder92/Besra-Killbot/actions)
[![License](https://img.shields.io/github/license/Canarder92/Besra-Killbot)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue?logo=python)](https://www.python.org/) 

# Besra-Killbot — Installation & Setup (English)

This guide shows **two ways** to run the bot that posts **EVE Online killmails** to Discord with an *Insight–5 Utility* style embed (victim, final blow, system/region, ISK value, zKillboard/DOTLAN links):

- **Path A – From Git repo (dev / local build)**  
- **Path B – From Docker image (prod / simple)**

All steps below are ordered to avoid back-and-forth: prepare files → set secrets → run container → obtain refresh token → restart → verify.

---

## 1) Get the project

- **Path A (Git):** clone the repository locally.  
```bash
    git clone https://github.com/Canarder92/Besra-Killbot.git
    cd Besra-Killbot
```

- **Path B (Docker image only):** create a new empty folder on your server (e.g. `/opt/besra-killbot`) and put a **minimal docker-compose.yml** there.  
```yaml
services:
    killmailbot:
        image: ghcr.io/canarder92/besra-killbot:latest
        env_file:
          - .env
        volumes:
          - killmailbot_data:/app/data
        restart: unless-stopped
        ports:
          - "${CALLBACK_PORT:-53682}:${CALLBACK_PORT:-53682}"


volumes:
    killmailbot_data:
```
> You will keep your `.env` next to your compose file in both paths.

---

## 2) Create the `.env`

- **Path A (Git):** copy the example file shipped in the repo, then edit it.  
```bash
    cp .env.example .env
    #and edit it with "sudo nano .env"
  ```
- **Path B (Docker image):** create a **new** `.env` by pasting the template below.  
```env
    # Discord
    DISCORD_TOKEN=
    DISCORD_CHANNEL_ID=

    # EVE ESI / SSO
    EVE_CLIENT_ID=
    EVE_CLIENT_SECRET=
    EVE_REFRESH_TOKEN=
    CORPORATION_ID=
    COMPAT_DATE=2025-08-26

    #Europe/Paris Berlin Rome Moscow Madrid ...
    #America/New_York Toronto Chicago ...
    #Asia/Dubai Tokyo Shanghai Seoul
    TIMEZONE=Europe/London

    # Auth local callback (PKCE helper)
    CALLBACK_PORT=53682

    # App
    LOG_LEVEL=INFO
    POLL_INTERVAL_SECONDS=120
    CLEANUP_INTERVAL_MINUTES=60

    # Pricing
    MARKET_REGION_ID=10000002   # The Forge
    PRICE_TTL_DAYS=7
  ```
In both cases, **leave `EVE_REFRESH_TOKEN=` empty for now**. You’ll generate it later.

---

## 3) Create & configure the Discord bot

1) Go to Discord Developer Portal → create an **Application**, then **Add Bot**.  
2) Copy the **Bot Token** → put it in `.env` → `DISCORD_TOKEN=...`  
3) OAuth2 → URL Generator → check `bot` and `applications.commands`, grant **Send Messages** and **Embed Links**. Use that URL to invite the bot to your server.  
4) In Discord, enable **Developer Mode** → right-click your **target channel** → **Copy Channel ID** → put it in `.env` → `DISCORD_CHANNEL_ID=...`

---

## 4) Create & configure the EVE SSO application

1) Go to EVE Developers Portal → create an **EVE SSO** app:  
   - Type: **Website**  
   - Callback: `http://localhost:53682/callback` (matches `CALLBACK_PORT` in `.env`)  
   - Scope required: `esi-killmails.read_corporation_killmails.v1`
2) Put the **Client ID** and **Client Secret** in `.env` → `EVE_CLIENT_ID=...`, `EVE_CLIENT_SECRET=...`
3) Put your **corporation ID** in `.env` → `CORPORATION_ID=...`

> Keep `COMPAT_DATE=2025-08-26` unless CCP changes compatibility headers.

---

## 5) Launch the container (without refresh token), get the token, and store it

1) **Start the container with your current `.env`** (remember `EVE_REFRESH_TOKEN` is still empty):

- **Path A (Git):** use the compose file from the repo.  
```bash
    docker compose -f docker/docker-compose.yml up --build -d
  ```
- **Path B (Docker image):** use your minimal compose file.  
```bash
    docker compose up -d
  ```
2) **Run the PKCE auth helper inside the running container** to generate a refresh token:  
```bash
    #use docker ps to get the container id
    docker ps
    #then copy it here
    docker exec -it [ContainerID] python -m src.esi.auth
  ```
3) The helper prints a **URL**. Open it in a browser, log in, and authorize. You’ll see a “OK. You can close this tab.” page, and the terminal will print a **refresh token**.  
   Expected output example:  
```bash
    Refresh token:
    ...<long_token>...
  ```
> **Callback issues?** If your server doesn’t expose the `CALLBACK_PORT` publicly, create a temporary SSH tunnel from your laptop to the server so your browser can hit `http://localhost:53682/callback` properly. I personnaly use Port Forwarding from Termius (label:blabla, Localportnumber:53682 bindadress:localhost intermediatehost:yourserver destinationadress:localhost destinationportnumber:53682).
```bash
    # From your laptop to the server (replace 'user' and 'server'):
    ssh -L 53682:localhost:53682 user@serverip
    # Then run the auth helper and open the printed URL in your local browser.
```

4) **Put the token** in your `.env` → `EVE_REFRESH_TOKEN=...`

5) **Restart the container** to load the new token:  
```bash
    docker compose restart [ContainerID]
```

---

## 6) Verify it works

In your Discord server:

- Run `/status` → you should see:  
```rust
    Bot : Ok
    Communication avec l'Api de Eve online : Ok
  ```
- Run `/test_post` → the bot fetches the most recent corp killmail from ESI and posts an embed in the channel.

---

## 7) `.env` knobs (quick reference)

- `LOG_LEVEL` — bot log verbosity (e.g. `INFO`, `DEBUG`).  
- `POLL_INTERVAL_SECONDS` — how often the scheduler polls ESI for new corp killmails (default `120`).  
- `CLEANUP_INTERVAL_MINUTES` — periodically refresh the local index to match ESI’s “recent” page (default `60`).  
- `MARKET_REGION_ID` — EVE region used to price items (default `10000002` “The Forge”).  
- `PRICE_TTL_DAYS` — cache time for computed average prices (default `7`).  
- `CALLBACK_PORT` — local HTTP port used by the one-shot PKCE flow (default `53682`). Must match the SSO app callback and be reachable from your browser (use port-forwarding if needed).  
- `COMPAT_DATE` — sent as `X-Compatibility-Date` to ESI (default `2025-08-26`).  
- `TIMEZONE` — is used to convert the date and hour to your timezone.  

---

## 8) Commands (quick facts)

- `/status` — checks ESI status and replies with a simple “Bot: Ok / ESI: Ok” when healthy.  
- `/test_post` — fetches the first killmail from ESI “recent” and posts the full embed; also sends a private step-by-step report.  
- `/ping` — “Pong!” sanity check.  
- `/force_refresh_prices` — disabled for now.
