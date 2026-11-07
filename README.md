# xiel dashboard v2.1

xiel v2.1 runs inside the existing Python Discord bot. FastAPI serves the API and the prebuilt React/Three.js client on port `10300`; MongoDB stores dashboard settings, OAuth sessions, economy records, access grants, and global bans. Socket.IO publishes live status directly from the active discord.py process, so no second Discord gateway connection is created.

The active production runtime does **not** require Node.js. Node is needed only on a development machine when `web/client` is changed and rebuilt.

## Active structure

```text
dashboard_api/       FastAPI, MongoDB, OAuth, authorization, and Socket.IO
cogs/help.py         Dynamic paginated Discord help built from loaded commands
cogs/web_dashboard.py
                     Uvicorn host and bot-side dashboard event integration
web/client/          React/Vite source and committed production build
web/client/dist/     Files served by FastAPI in production
```

Dashboard edits to prefixes, aliases, and AntiNuke settings are synchronized with the bot's existing persistence layer. Welcome/leave messages, join/leave logs, and global-ban enforcement read from MongoDB in the dashboard cog.

## Required configuration

Copy `.env.example` to `.env`, then set at least:

```env
DISCORD_TOKEN=your-bot-token
DISCORD_CLIENT_ID=your-application-id
DISCORD_CLIENT_SECRET=your-oauth-secret
DISCORD_REDIRECT_URI=https://xiel.flagsbot.in/api/auth/callback
MONGODB_URI=mongodb+srv://user:password@cluster/xiel
SESSION_SECRET=a-long-random-secret
DASHBOARD_PUBLIC_URL=https://xiel.flagsbot.in
OWNER_IDS=123456789012345678
```

The redirect URI must also be added to the Discord application's OAuth2 redirect list. `OWNER_IDS` and `CO_OWNER_IDS` are the only source of dashboard owner roles.

## Pterodactyl deployment (Python-only)

1. Use a Python 3.12+ image.
2. Upload the repository, including the committed `web/client/dist` directory.
3. Install dependencies with `pip install -r requirements.txt`.
4. Configure the environment variables above.
5. Keep the startup command as `python app.py`.
6. Point the public reverse proxy or Cloudflare tunnel to port `10300`.

Successful startup includes:

```text
Starting dashboard v2.1.0 (FastAPI + React) on port 10300...
Dashboard v2.1.0 MongoDB, OAuth, and telemetry ready.
```

When MongoDB or Discord OAuth configuration is missing, the public website, live status, command atlas, and bot invite endpoint still start in public mode. Sign-in and protected management routes remain disabled, and startup lists the missing configuration. Set `MONGODB_URI`, `DISCORD_CLIENT_SECRET`, and a stable `SESSION_SECRET`, then restart to enable the full dashboard.

If startup says `web/client/dist is missing`, upload the prebuilt directory. Node.js is not installed or launched on Pterodactyl.

## Local development

Install Python packages and frontend dependencies:

```text
pip install -r requirements.txt
npm install
```

Use `npm run dev` to start the Python bot/API and Vite together. Vite runs on `http://localhost:5173` and proxies `/api` and `/socket.io` to port `10300`.

After frontend changes, run `npm run build` and commit/upload `web/client/dist`. Production continues to use `python app.py`.

Validation commands:

```text
npm run check
python -m compileall -q dashboard_api cogs/web_dashboard.py cogs/help.py
```

## Authorization and API

Discord OAuth requests `identify guilds`. Settings and economy routes require the user's `Manage Server` permission and require xiel to be present in that guild. Co-owners can manage premium/profile grants; only owners can manage global bans or make the bot leave a server.

Primary routes:

- `GET /api/health`, `/api/status`, `/api/commands`, `/api/invite`
- `/api/auth/discord`, `/api/auth/callback`, `/api/auth/me`, `/api/auth/logout`
- `GET /api/servers`
- `GET|PATCH /api/settings/{guildId}` and alias create/delete routes
- `/api/economy/{guildId}/overview`, wallet correction, and shop CRUD
- `/api/owner/*` and `/api/coowner/*`

Payloads are validated with Pydantic. API failures use `{ "error": { "code", "message", "details" } }`. OAuth sessions are opaque, HTTP-only, seven-day MongoDB sessions. HTTPS deployments receive secure cookies and all responses receive security headers and a restrictive content security policy.

`/api/commands` introspects the commands currently loaded in discord.py, including prefix commands, slash commands, groups, aliases, categories, syntax, and restrictions. Owner commands are never exposed to normal users.
