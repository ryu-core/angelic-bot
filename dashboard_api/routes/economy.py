from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request, Response
from pymongo import DESCENDING, ReturnDocument

from ..database import object_id, public_document
from ..dependencies import managed_guild
from ..errors import ApiError
from ..schemas import SNOWFLAKE, ShopCreate, ShopPatch, WalletPatch


router = APIRouter(prefix="/api/economy/{guild_id}", tags=["economy"])


@router.get("/overview")
async def overview(request: Request, guild_id: str):
    await managed_guild(request, guild_id)
    database = request.app.state.database.db
    leaderboard = await database.economy_wallets.find({"guildId": guild_id}).sort(
        [("balance", DESCENDING), ("bank", DESCENDING)]
    ).limit(25).to_list(length=25)
    shop = await database.shop_items.find({"guildId": guild_id}).sort("price", 1).to_list(length=500)
    aggregates = await database.economy_wallets.aggregate([
        {"$match": {"guildId": guild_id}},
        {"$group": {
            "_id": None,
            "wallets": {"$sum": 1},
            "circulating": {"$sum": {"$add": ["$balance", "$bank"]}},
            "averageStreak": {"$avg": "$streak"},
        }},
    ]).to_list(length=1)
    stats = aggregates[0] if aggregates else {"wallets": 0, "circulating": 0, "averageStreak": 0}
    stats.pop("_id", None)
    return {"data": {
        "leaderboard": [public_document(item) for item in leaderboard],
        "shop": [public_document(item) for item in shop],
        "stats": stats,
    }}


@router.patch("/wallets/{user_id}")
async def patch_wallet(request: Request, guild_id: str, user_id: str, payload: WalletPatch):
    await managed_guild(request, guild_id)
    if not SNOWFLAKE.fullmatch(user_id):
        raise ApiError(422, "VALIDATION_ERROR", "userId must be a Discord ID.")
    now = datetime.now(UTC)
    changes = payload.model_dump(exclude_none=True)
    insert_defaults = {
        key: value for key, value in {
            "guildId": guild_id, "userId": user_id, "balance": 1000, "bank": 0,
            "streak": 0, "inventory": [], "createdAt": now,
        }.items() if key not in changes
    }
    document = await request.app.state.database.db.economy_wallets.find_one_and_update(
        {"guildId": guild_id, "userId": user_id},
        {"$set": {**changes, "updatedAt": now}, "$setOnInsert": insert_defaults},
        upsert=True, return_document=ReturnDocument.AFTER,
    )
    return {"data": public_document(document)}


@router.post("/shop", status_code=201)
async def create_shop_item(request: Request, guild_id: str, payload: ShopCreate):
    await managed_guild(request, guild_id)
    if await request.app.state.database.db.shop_items.find_one({"guildId": guild_id, "sku": payload.sku}):
        raise ApiError(409, "SHOP_ITEM_EXISTS", "That shop SKU already exists.")
    now = datetime.now(UTC)
    document = {**payload.model_dump(), "guildId": guild_id, "createdAt": now, "updatedAt": now}
    result = await request.app.state.database.db.shop_items.insert_one(document)
    document["_id"] = result.inserted_id
    return {"data": public_document(document)}


@router.patch("/shop/{item_id}")
async def patch_shop_item(request: Request, guild_id: str, item_id: str, payload: ShopPatch):
    await managed_guild(request, guild_id)
    try:
        record_id = object_id(item_id)
    except ValueError as exc:
        raise ApiError(422, "VALIDATION_ERROR", str(exc)) from exc
    document = await request.app.state.database.db.shop_items.find_one_and_update(
        {"_id": record_id, "guildId": guild_id},
        {"$set": {**payload.model_dump(exclude_none=True), "updatedAt": datetime.now(UTC)}},
        return_document=ReturnDocument.AFTER,
    )
    if not document:
        raise ApiError(404, "NOT_FOUND", "Shop item not found.")
    return {"data": public_document(document)}


@router.delete("/shop/{item_id}", status_code=204)
async def delete_shop_item(request: Request, guild_id: str, item_id: str):
    await managed_guild(request, guild_id)
    try:
        record_id = object_id(item_id)
    except ValueError as exc:
        raise ApiError(422, "VALIDATION_ERROR", str(exc)) from exc
    await request.app.state.database.db.shop_items.delete_one({"_id": record_id, "guildId": guild_id})
    return Response(status_code=204)
