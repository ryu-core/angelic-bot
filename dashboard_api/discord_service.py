from __future__ import annotations

from urllib.parse import urlencode

import aiohttp

from .errors import ApiError


DISCORD_API = "https://discord.com/api/v10"


class DiscordAuthorizationError(ApiError):
    """The user's Discord OAuth grant is no longer usable."""


async def discord_request(method: str, path: str, *, headers=None, data=None, json=None, user_authorization=False):
    timeout = aiohttp.ClientTimeout(total=12)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(method, f"{DISCORD_API}{path}", headers=headers, data=data, json=json) as response:
                try:
                    payload = None if response.status == 204 else await response.json(content_type=None)
                except ValueError:
                    payload = {}
                if response.status >= 400:
                    message = payload.get("message") if isinstance(payload, dict) else None
                    if user_authorization and response.status in {401, 403}:
                        raise DiscordAuthorizationError(
                            401, "DISCORD_AUTH_EXPIRED", "Your Discord authorization expired. Please sign in again."
                        )
                    if response.status == 429:
                        raise ApiError(503, "DISCORD_RATE_LIMITED", "Discord is busy. Please try again shortly.")
                    raise ApiError(
                        502,
                        "DISCORD_API_ERROR",
                        message or "Discord rejected the request.",
                    )
                return payload
    except (aiohttp.ClientError, TimeoutError) as exc:
        raise ApiError(502, "DISCORD_UNAVAILABLE", "Discord is temporarily unavailable.") from exc


def oauth_url(config, state: str) -> str:
    query = urlencode({
        "client_id": config.discord_client_id,
        "redirect_uri": config.discord_redirect_uri,
        "response_type": "code",
        "scope": "identify guilds",
        "state": state,
        "prompt": "none",
    })
    return f"https://discord.com/oauth2/authorize?{query}"


async def exchange_code(config, code: str):
    return await discord_request("POST", "/oauth2/token", data={
        "client_id": config.discord_client_id,
        "client_secret": config.discord_client_secret,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": config.discord_redirect_uri,
    })


async def fetch_user(access_token: str):
    return await discord_request(
        "GET", "/users/@me", headers={"Authorization": f"Bearer {access_token}"}, user_authorization=True
    )


async def fetch_guilds(access_token: str):
    return await discord_request(
        "GET", "/users/@me/guilds", headers={"Authorization": f"Bearer {access_token}"}, user_authorization=True
    )


async def leave_guild(config, guild_id: str):
    await discord_request("DELETE", f"/users/@me/guilds/{guild_id}", headers={"Authorization": f"Bot {config.discord_bot_token}"})
