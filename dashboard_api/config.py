from __future__ import annotations

import os
import secrets
from dataclasses import dataclass


def _ids(name: str) -> frozenset[str]:
    return frozenset(value.strip() for value in os.getenv(name, "").split(",") if value.strip())


@dataclass(frozen=True)
class DashboardConfig:
    mongo_uri: str
    session_secret: str
    public_url: str
    client_url: str
    discord_client_id: str
    discord_client_secret: str
    discord_redirect_uri: str
    discord_bot_token: str
    owners: frozenset[str]
    coowners: frozenset[str]
    secure_cookies: bool


def load_config(bot) -> DashboardConfig:
    mongo_uri = os.getenv("MONGODB_URI", "").strip()
    public_url = (os.getenv("DASHBOARD_PUBLIC_URL") or os.getenv("PUBLIC_URL") or "https://xiel.flagsbot.in").rstrip("/")
    session_secret = os.getenv("SESSION_SECRET") or secrets.token_urlsafe(48)
    if not os.getenv("SESSION_SECRET"):
        print("⚠️ SESSION_SECRET is not set; dashboard logins will reset when the bot restarts.")
    client_id = os.getenv("DISCORD_CLIENT_ID") or (str(bot.user.id) if bot.user else "")
    client_secret = os.getenv("DISCORD_CLIENT_SECRET", "").strip()
    return DashboardConfig(
        mongo_uri=mongo_uri,
        session_secret=session_secret,
        public_url=public_url,
        client_url=(os.getenv("CLIENT_URL") or public_url).rstrip("/"),
        discord_client_id=client_id,
        discord_client_secret=client_secret,
        discord_redirect_uri=os.getenv("DISCORD_REDIRECT_URI") or f"{public_url}/api/auth/callback",
        discord_bot_token=os.getenv("DISCORD_BOT_TOKEN") or os.getenv("DISCORD_TOKEN", ""),
        owners=_ids("OWNER_IDS"),
        coowners=_ids("CO_OWNER_IDS"),
        secure_cookies=public_url.startswith("https://"),
    )
