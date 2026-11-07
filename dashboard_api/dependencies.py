from __future__ import annotations

from fastapi import Request

from .discord_service import DiscordAuthorizationError, fetch_guilds
from .errors import ApiError
from .session import destroy_session, touch_session


MANAGE_GUILD = 1 << 5
ADMINISTRATOR = 1 << 3


def can_manage_guild(permission_value) -> bool:
    permissions = int(permission_value or 0)
    return bool(permissions & MANAGE_GUILD or permissions & ADMINISTRATOR)


def role_for(config, user_id: str) -> str:
    if user_id in config.owners:
        return "owner"
    if user_id in config.coowners:
        return "coowner"
    return "user"


def require_dashboard_ready(request: Request) -> None:
    config = request.app.state.config
    database = request.app.state.database
    if not config.mongo_uri or not config.discord_client_id or not config.discord_client_secret:
        raise ApiError(
            503,
            "DASHBOARD_CONFIGURATION_REQUIRED",
            "Dashboard sign-in is not configured yet. The public site remains available.",
        )
    if not database.available:
        raise ApiError(
            503,
            "DASHBOARD_STORAGE_UNAVAILABLE",
            "Dashboard storage is temporarily unavailable. The public site remains available.",
        )


def require_user(request: Request) -> dict:
    require_dashboard_ready(request)
    user = request.state.session.get("user")
    if not user:
        raise ApiError(401, "AUTH_REQUIRED", "Sign in with Discord to continue.")
    return user


def require_owner(request: Request) -> dict:
    user = require_user(request)
    if role_for(request.app.state.config, user["id"]) != "owner":
        raise ApiError(403, "OWNER_REQUIRED", "Owner access is required.")
    return user


def require_coowner(request: Request) -> dict:
    user = require_user(request)
    if role_for(request.app.state.config, user["id"]) not in {"owner", "coowner"}:
        raise ApiError(403, "COOWNER_REQUIRED", "Co-owner access is required.")
    return user


async def refreshed_guilds(request: Request) -> list[dict]:
    require_user(request)
    cached = getattr(request.state, "fresh_discord_guilds", None)
    if cached is not None:
        return cached
    access_token = request.state.session.get("accessToken")
    if not access_token:
        destroy_session(request)
        raise ApiError(401, "AUTH_REQUIRED", "Sign in with Discord to continue.")
    try:
        guilds = await fetch_guilds(access_token)
    except DiscordAuthorizationError:
        destroy_session(request)
        raise
    if not isinstance(guilds, list):
        raise ApiError(502, "DISCORD_API_ERROR", "Discord returned an invalid server list.")
    request.state.fresh_discord_guilds = guilds
    request.state.session["guilds"] = guilds
    touch_session(request)
    return guilds


async def managed_guild(request: Request, guild_id: str):
    require_user(request)
    guilds = await refreshed_guilds(request)
    guild_record = next((guild for guild in guilds if guild.get("id") == guild_id), None)
    if not guild_record or not can_manage_guild(guild_record.get("permissions", "0")):
        raise ApiError(403, "MANAGE_GUILD_REQUIRED", "You need Manage Server permission for this server.")
    guild = request.app.state.bot.get_guild(int(guild_id))
    if not guild:
        raise ApiError(404, "BOT_NOT_IN_GUILD", "xiel is not currently in this server.")
    return guild
