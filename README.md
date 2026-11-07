![Xiel — shape chaos into clarity. Discord command center.](web/client/public/og.png)

# Angelic Bot · Xiel

**A Discord community toolkit for moderation, games, music, and server management — with a dashboard built in.**

![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![discord.py](https://img.shields.io/badge/discord.py-2.7-5865F2?style=flat-square&logo=discord&logoColor=white)
![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/Dashboard-React-149ECA?style=flat-square&logo=react&logoColor=white)
![MongoDB](https://img.shields.io/badge/Database-MongoDB-47A248?style=flat-square&logo=mongodb&logoColor=white)

[Features](#features) · [Get started](#get-started) · [Dashboard](#dashboard) · [Development](#development) · [Project structure](#project-structure)

---

## Features

| | What’s inside |
|---|---|
| 🛡️ **Moderation & protection** | Moderation commands, anti-nuke protections, staff supervision and logs. |
| 🧩 **Community tools** | Welcome flows, auto roles, private voice channels, ticket sorting and giveaways. |
| 🎮 **Games & economy** | Multiplayer games, an economy system, games of chance and community activities. |
| 🎵 **Music & voice** | Music queues, Spotify metadata, YouTube search, audio filters and text-to-speech. |
| ✨ **More ways to connect** | AI chat, roleplay, AFK status, reminders, translation and utility commands. |
| 🪐 **Xiel dashboard** | A React dashboard for status, commands, server settings and economy management. |

Availability depends on the bot’s configuration, Discord permissions, and any optional services used by a feature.

## Get started

### Prerequisites

- **Python 3.12+** and `pip`
- A Discord application and bot token
- **FFmpeg** on your system `PATH` for voice features
- MongoDB and Discord OAuth credentials for the full dashboard
- Node.js **22.22+** only if developing or rebuilding the dashboard

### 1. Clone and install

```bash
git clone https://github.com/ryu-core/angelic-bot.git
cd angelic-bot
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure

Copy `.env.example` to `.env` and fill in your own values. For the bot and full dashboard, configure at least:

```env
DISCORD_TOKEN=your-bot-token
DISCORD_CLIENT_ID=your-application-id
DISCORD_CLIENT_SECRET=your-oauth-secret
DISCORD_REDIRECT_URI=https://your-domain.example/api/auth/callback
MONGODB_URI=mongodb+srv://user:password@cluster/your-database
SESSION_SECRET=a-long-random-secret
DASHBOARD_PUBLIC_URL=https://your-domain.example
OWNER_IDS=123456789012345678
```

Add the redirect URI to your Discord application’s OAuth2 settings. `OWNER_IDS` and `CO_OWNER_IDS` define dashboard owner roles. Other integrations are listed in [`.env.example`](.env.example); configure them only if you use their features.

> **Keep secrets private.** Never commit your `.env`, bot token, API keys, database credentials or session secret.

### 3. Start the bot

```bash
python app.py
```

The default command prefix is `,` and can be configured with `PREFIX`. The dashboard is served on port **10300** by default. Set up the appropriate Discord intents and permissions for the features you enable.

## Dashboard

Xiel runs inside the bot process: FastAPI serves the API and the prebuilt React client, MongoDB stores dashboard data, and Socket.IO streams live status. There is no second Discord gateway connection.

The prebuilt client in `web/client/dist/` is included, so a production deployment does **not** need Node.js. Without MongoDB or Discord OAuth configuration, the public site and public endpoints can start, but sign-in and protected management routes stay disabled.

### Pterodactyl / production

1. Use a Python 3.12+ image and include `web/client/dist/` when deploying.
2. Install `requirements.txt` and configure your environment variables.
3. Start with `python app.py`.
4. Point your reverse proxy or tunnel to port `10300` (or your configured `DASHBOARD_PORT`).
5. Use HTTPS and a stable `SESSION_SECRET` for dashboard sessions.

### API at a glance

- **Public:** `/api/health`, `/api/status`, `/api/commands`, `/api/invite`
- **Authentication:** `/api/auth/discord`, `/api/auth/callback`, `/api/auth/me`, `/api/auth/logout`
- **Server management:** `/api/servers`, `/api/settings/{guildId}`, `/api/economy/{guildId}/overview`
- **Privileged controls:** `/api/owner/*` and `/api/coowner/*`

Discord OAuth requests `identify` and `guilds`. Server settings and economy routes require Manage Server permission and the bot’s presence in the server. Owner commands are not exposed to normal users.

## Development

To work on the dashboard, install frontend dependencies from the repository root:

```bash
npm install
npm run dev
```

Vite runs at `http://localhost:5173` and proxies `/api` and `/socket.io` to the bot on port `10300`. After changing the frontend, rebuild and commit the production client:

```bash
npm run build
npm run check
```

The `check` script runs the Python compilation check and the client’s lint, unit test, build and bundle checks. It does not replace testing with your own Discord application and service configuration.

## Project structure

```text
app.py                 Bot entry point and extension loading
config.py              Environment-based configuration
cogs/                  Discord commands, listeners and dashboard host
utils/                 Shared helpers, persistence and feature logic
database/              Database models
dashboard_api/         FastAPI routes, OAuth, authorization and Socket.IO
web/client/            React/Vite dashboard source
web/client/dist/       Prebuilt dashboard served in production
assets/                Bot assets
```

---

**Built for communities that want a little more clarity and a lot more control.**
