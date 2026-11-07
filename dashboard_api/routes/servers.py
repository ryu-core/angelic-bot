from __future__ import annotations

from fastapi import APIRouter, Request

from ..dependencies import can_manage_guild, refreshed_guilds, require_user


router = APIRouter(prefix="/api/servers", tags=["servers"])


@router.get("")
async def servers(request: Request):
    require_user(request)
    guilds = await refreshed_guilds(request)
    bot_guilds = {str(guild.id): guild for guild in request.app.state.bot.guilds}
    data = []
    for record in guilds:
        if not can_manage_guild(record.get("permissions", "0")) or record["id"] not in bot_guilds:
            continue
        guild = bot_guilds[record["id"]]
        data.append({
            "id": record["id"], "name": guild.name,
            "icon": str(guild.icon.url) if guild.icon else None,
            "owner": record.get("owner", False), "memberCount": guild.member_count or 0,
        })
    return {"data": data}
