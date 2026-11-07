from __future__ import annotations

import secrets

from fastapi import APIRouter, Query, Request
from fastapi.responses import RedirectResponse, Response

from ..dependencies import require_dashboard_ready, role_for
from ..discord_service import DiscordAuthorizationError, exchange_code, fetch_guilds, fetch_user, oauth_url
from ..errors import ApiError
from ..session import allow_session_creation, destroy_session, rotate_session, touch_session


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/discord")
async def login(request: Request):
    try:
        require_dashboard_ready(request)
    except ApiError:
        return RedirectResponse(f"{request.app.state.config.client_url}/?error=dashboard_unavailable")
    state = secrets.token_urlsafe(32)
    request.state.session["oauthState"] = state
    allow_session_creation(request)
    touch_session(request)
    return RedirectResponse(oauth_url(request.app.state.config, state))


@router.get("/callback")
async def callback(request: Request, code: str = Query(min_length=1), state: str = Query(min_length=1)):
    require_dashboard_ready(request)
    if not request.state.session.get("oauthState") or request.state.session["oauthState"] != state:
        return RedirectResponse(f"{request.app.state.config.client_url}/?error=oauth_state")
    token = await exchange_code(request.app.state.config, code)
    try:
        user, guilds = await fetch_user(token["access_token"]), await fetch_guilds(token["access_token"])
    except DiscordAuthorizationError:
        destroy_session(request)
        raise
    avatar = f"https://cdn.discordapp.com/avatars/{user['id']}/{user['avatar']}.webp?size=128" if user.get("avatar") else None
    request.state.session.clear()
    request.state.session.update({
        "user": {"id": user["id"], "username": user.get("global_name") or user["username"], "avatar": avatar},
        "accessToken": token["access_token"],
        "guilds": guilds,
    })
    rotate_session(request)
    return RedirectResponse(f"{request.app.state.config.client_url}/dashboard")


@router.get("/me")
async def me(request: Request):
    user = request.state.session.get("user")
    if not user:
        return {"data": None}
    return {"data": {**user, "role": role_for(request.app.state.config, user["id"])}}


@router.post("/logout", status_code=204)
async def logout(request: Request):
    destroy_session(request)
    return Response(status_code=204)
