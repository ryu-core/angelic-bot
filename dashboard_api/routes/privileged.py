from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

import discord
from fastapi import APIRouter, Request, Response
from pymongo import DESCENDING, ReturnDocument

from ..database import object_id, public_document
from ..dependencies import require_coowner, require_owner
from ..errors import ApiError
from ..runtime_sync import (
    normalize_premium_name,
    sync_global_ban,
    sync_global_unban,
    sync_premium_grant,
    sync_premium_revoke,
    sync_profile_grant,
    sync_profile_revoke,
)
from ..schemas import GlobalBanCreate, PremiumGrantCreate, ProfileGrantCreate
from ..status import guild_snapshot


owner_router = APIRouter(prefix="/api/owner", tags=["owner"])
coowner_router = APIRouter(prefix="/api/coowner", tags=["coowner"])
LOGGER = logging.getLogger("xiel.dashboard.global_bans")


def public_ban(document: dict) -> dict:
    result = dict(document)
    result.pop("enforcement", None)
    return public_document(result)


async def overview_data(request: Request):
    database = request.app.state.database.db
    premium = await database.premium_grants.find().sort("createdAt", DESCENDING).to_list(length=5000)
    profiles = await database.profile_access.find().sort("createdAt", DESCENDING).to_list(length=5000)
    servers = sorted(guild_snapshot(request.app.state.bot), key=lambda server: server["memberCount"], reverse=True)
    return {
        "servers": servers,
        "premium": [public_document(item) for item in premium],
        "profiles": [public_document(item) for item in profiles],
    }


async def overview(request: Request, owner: bool):
    (require_owner if owner else require_coowner)(request)
    return {"data": await overview_data(request)}


async def grant_premium(request: Request, payload: PremiumGrantCreate, owner: bool):
    user = (require_owner if owner else require_coowner)(request)
    canonical_name = await asyncio.to_thread(normalize_premium_name, payload.commandName)
    if not canonical_name:
        raise ApiError(422, "VALIDATION_ERROR", "That is not a recognized premium command.")
    now = datetime.now(UTC)
    document = await request.app.state.database.db.premium_grants.find_one_and_update(
        {"userId": payload.userId, "guildId": payload.guildId, "commandName": canonical_name},
        {"$setOnInsert": {**payload.model_dump(), "commandName": canonical_name, "grantedBy": user["id"], "createdAt": now}},
        upsert=True, return_document=ReturnDocument.AFTER,
    )
    await asyncio.to_thread(sync_premium_grant, payload.userId, payload.guildId, canonical_name, user["id"])
    return {"data": public_document(document)}


async def grant_profile(request: Request, payload: ProfileGrantCreate, owner: bool):
    user = (require_owner if owner else require_coowner)(request)
    now = datetime.now(UTC)
    document = await request.app.state.database.db.profile_access.find_one_and_update(
        payload.model_dump(), {"$setOnInsert": {**payload.model_dump(), "grantedBy": user["id"], "createdAt": now}},
        upsert=True, return_document=ReturnDocument.AFTER,
    )
    await asyncio.to_thread(sync_profile_grant, payload.userId, payload.guildId, user["id"])
    return {"data": public_document(document)}


async def delete_record(request: Request, collection: str, record_id: str, owner: bool):
    (require_owner if owner else require_coowner)(request)
    try:
        parsed_id = object_id(record_id)
    except ValueError as exc:
        raise ApiError(422, "VALIDATION_ERROR", str(exc)) from exc
    target = request.app.state.database.db[collection]
    document = await target.find_one({"_id": parsed_id})
    if not document:
        raise ApiError(404, "NOT_FOUND", "Access record not found.")
    await target.delete_one({"_id": parsed_id})
    if collection == "premium_grants":
        await asyncio.to_thread(
            sync_premium_revoke, document["userId"], document["guildId"], document["commandName"]
        )
    elif collection == "profile_access":
        await asyncio.to_thread(sync_profile_revoke, document["userId"], document["guildId"])
    return Response(status_code=204)


@owner_router.get("/overview")
async def owner_overview(request: Request): return await overview(request, True)


@coowner_router.get("/overview")
async def coowner_overview(request: Request): return await overview(request, False)


@owner_router.post("/premium", status_code=201)
async def owner_premium(request: Request, payload: PremiumGrantCreate): return await grant_premium(request, payload, True)


@coowner_router.post("/premium", status_code=201)
async def coowner_premium(request: Request, payload: PremiumGrantCreate): return await grant_premium(request, payload, False)


@owner_router.delete("/premium/{record_id}", status_code=204)
async def owner_premium_delete(request: Request, record_id: str): return await delete_record(request, "premium_grants", record_id, True)


@coowner_router.delete("/premium/{record_id}", status_code=204)
async def coowner_premium_delete(request: Request, record_id: str): return await delete_record(request, "premium_grants", record_id, False)


@owner_router.post("/profiles", status_code=201)
async def owner_profile(request: Request, payload: ProfileGrantCreate): return await grant_profile(request, payload, True)


@coowner_router.post("/profiles", status_code=201)
async def coowner_profile(request: Request, payload: ProfileGrantCreate): return await grant_profile(request, payload, False)


@owner_router.delete("/profiles/{record_id}", status_code=204)
async def owner_profile_delete(request: Request, record_id: str): return await delete_record(request, "profile_access", record_id, True)


@coowner_router.delete("/profiles/{record_id}", status_code=204)
async def coowner_profile_delete(request: Request, record_id: str): return await delete_record(request, "profile_access", record_id, False)


@owner_router.get("/bans")
async def bans(request: Request):
    require_owner(request)
    records = await request.app.state.database.db.global_bans.find().sort("createdAt", DESCENDING).to_list(length=5000)
    return {"data": [public_ban(item) for item in records]}


@owner_router.post("/bans", status_code=201)
async def create_ban(request: Request, payload: GlobalBanCreate):
    user = require_owner(request)
    document = await request.app.state.database.db.global_bans.find_one_and_update(
        {"userId": payload.userId},
        {"$set": {**payload.model_dump(), "bannedBy": user["id"], "createdAt": datetime.now(UTC)}},
        upsert=True, return_document=ReturnDocument.AFTER,
    )
    await asyncio.to_thread(sync_global_ban, request.app.state.bot, payload.userId, payload.reason, user["id"])
    enforcement = await enforce_global_ban(request.app.state.bot, payload.userId, payload.reason)
    await request.app.state.database.db.global_bans.update_one(
        {"_id": document["_id"]},
        {"$set": {"enforcement": enforcement}},
    )
    return {"data": public_ban(document)}


async def enforce_global_ban(bot, user_id: str, reason: str):
    failures = []
    failed = 0
    succeeded = 0
    target = discord.Object(id=int(user_id))
    for guild in bot.guilds:
        try:
            await guild.ban(target, reason=f"Global ban: {reason}")
            succeeded += 1
        except Exception as exc:
            failed += 1
            LOGGER.warning("Could not enforce global ban for user %s in guild %s: %s", user_id, guild.id, exc)
            if len(failures) < 100:
                failures.append({"guildId": str(guild.id), "error": str(exc)[:200] or exc.__class__.__name__})
    return {
        "checkedAt": datetime.now(UTC),
        "attempted": len(bot.guilds),
        "succeeded": succeeded,
        "failed": failed,
        "failures": failures,
    }


@owner_router.delete("/bans/{user_id}", status_code=204)
async def delete_ban(request: Request, user_id: str):
    require_owner(request)
    await request.app.state.database.db.global_bans.delete_one({"userId": user_id})
    await asyncio.to_thread(sync_global_unban, request.app.state.bot, user_id)
    return Response(status_code=204)


@owner_router.delete("/servers/{guild_id}", status_code=204)
async def owner_leave(request: Request, guild_id: str):
    require_owner(request)
    guild = request.app.state.bot.get_guild(int(guild_id)) if guild_id.isdigit() else None
    if not guild:
        raise ApiError(404, "NOT_FOUND", "Server not found.")
    await guild.leave()
    return Response(status_code=204)
