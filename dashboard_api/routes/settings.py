from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from pymongo import ReturnDocument

from ..database import public_document
from ..dependencies import managed_guild
from ..errors import ApiError
from ..schemas import AliasCreate, SettingsPatch, default_settings
from ..runtime_sync import sync_alias_add, sync_alias_delete, sync_prefix, sync_security


router = APIRouter(prefix="/api/settings/{guild_id}", tags=["settings"])


async def settings_document(request: Request, guild_id: str):
    collection = request.app.state.database.db.guild_settings
    return await collection.find_one({"guildId": guild_id}) or default_settings(guild_id)


async def ensure_settings_document(request: Request, guild_id: str):
    collection = request.app.state.database.db.guild_settings
    await collection.update_one(
        {"guildId": guild_id},
        {"$setOnInsert": default_settings(guild_id)},
        upsert=True,
    )


def dot_paths(value: dict, prefix: str = "") -> dict:
    flattened = {}
    for key, item in value.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(item, dict):
            flattened.update(dot_paths(item, path))
        else:
            flattened[path] = item
    return flattened


@router.get("")
async def get_settings(request: Request, guild_id: str):
    await managed_guild(request, guild_id)
    return {"data": public_document(await settings_document(request, guild_id))}


@router.patch("")
async def patch_settings(request: Request, guild_id: str, payload: SettingsPatch):
    await managed_guild(request, guild_id)
    await ensure_settings_document(request, guild_id)
    changes = dot_paths(payload.model_dump(exclude_unset=True, exclude_none=True))
    changes.update({"updatedBy": request.state.session["user"]["id"], "updatedAt": datetime.now(UTC)})
    document = await request.app.state.database.db.guild_settings.find_one_and_update(
        {"guildId": guild_id},
        {"$set": changes},
        return_document=ReturnDocument.AFTER,
    )
    if "prefix" in changes:
        await asyncio.to_thread(
            sync_prefix, request.app.state.bot, guild_id, changes["prefix"], request.state.session["user"]["id"]
        )
    if any(path.startswith("antiNuke.") for path in changes) or any(path.startswith("access.") for path in changes):
        await asyncio.to_thread(
            sync_security,
            guild_id,
            document.get("antiNuke") if any(path.startswith("antiNuke.") for path in changes) else None,
            document.get("access") if any(path.startswith("access.") for path in changes) else None,
        )
    return {"data": public_document(document)}


@router.post("/aliases", status_code=201)
async def add_alias(request: Request, guild_id: str, payload: AliasCreate):
    await managed_guild(request, guild_id)
    await ensure_settings_document(request, guild_id)
    document = await request.app.state.database.db.guild_settings.find_one_and_update(
        {"guildId": guild_id, "aliases.name": {"$ne": payload.name}},
        {"$push": {"aliases": payload.model_dump()}},
        return_document=ReturnDocument.AFTER,
    )
    if not document:
        raise ApiError(409, "ALIAS_EXISTS", "That alias already exists.")
    await asyncio.to_thread(
        sync_alias_add, guild_id, payload.model_dump(), request.state.session["user"]["id"]
    )
    return {"data": document.get("aliases", [])}


@router.delete("/aliases/{name}")
async def delete_alias(request: Request, guild_id: str, name: str):
    await managed_guild(request, guild_id)
    document = await request.app.state.database.db.guild_settings.find_one_and_update(
        {"guildId": guild_id}, {"$pull": {"aliases": {"name": name.lower()}}}, return_document=ReturnDocument.AFTER
    )
    await asyncio.to_thread(sync_alias_delete, guild_id, name.lower())
    return {"data": document.get("aliases", []) if document else []}
