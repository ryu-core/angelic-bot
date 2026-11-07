from __future__ import annotations

from typing import Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from ..command_registry import command_registry
from ..dependencies import role_for
from ..status import status_payload


router = APIRouter(prefix="/api", tags=["public"])


@router.get("/health")
async def health(request: Request):
    config = request.app.state.config
    database = request.app.state.database
    management_ready = bool(
        config.mongo_uri
        and config.discord_client_id
        and config.discord_client_secret
        and database.available
    )
    return {"data": {
        "ok": True,
        "service": "xiel-dashboard",
        "version": "2.1.0",
        "runtime": "fastapi",
        "mode": "full" if management_ready else "public",
        "managementReady": management_ready,
    }}


@router.get("/status")
async def status(request: Request):
    return {"data": status_payload(request.app.state.bot)}


@router.get("/commands")
async def commands(request: Request):
    user = request.state.session.get("user")
    user_id = user["id"] if user else "0"
    data = command_registry(request.app.state.bot, user_id, request.app.state.config)
    if not user or role_for(request.app.state.config, user["id"]) != "owner":
        data = [command for command in data if command["category"] != "Owner"]
    return {"data": data, "meta": {"count": len(data)}}


@router.get("/invite")
async def invite(
    request: Request,
    permissions: Literal["8", "268823648", "274877906944"] = "8",
):
    query = urlencode({
        "client_id": request.app.state.config.discord_client_id,
        "permissions": permissions,
        "scope": "bot applications.commands",
    })
    return RedirectResponse(f"https://discord.com/oauth2/authorize?{query}")
