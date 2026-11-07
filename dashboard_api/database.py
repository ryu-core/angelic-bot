from __future__ import annotations

from bson import ObjectId
from pymongo import ASCENDING, AsyncMongoClient
from pymongo.errors import ConfigurationError


COLLECTION_NAMES = {
    "guild_settings": "guildsettings",
    "economy_wallets": "economywallets",
    "shop_items": "shopitems",
    "premium_grants": "premiumgrants",
    "profile_access": "profileaccesses",
    "global_bans": "globalbans",
    "web_sessions": "webSessions",
}


class DashboardCollections:
    """Expose Python-friendly names while retaining the original Mongoose collections."""

    def __init__(self, database):
        self.database = database

    def __getattr__(self, name: str):
        return self.database[COLLECTION_NAMES.get(name, name)]

    def __getitem__(self, name: str):
        return self.database[COLLECTION_NAMES.get(name, name)]


class DashboardDatabase:
    def __init__(self, uri: str):
        self.uri = uri.strip()
        self.client = None
        self.raw_db = None
        self.db = None
        self.available = False
        if not self.uri:
            return
        self.client = AsyncMongoClient(self.uri, serverSelectionTimeoutMS=8_000)
        try:
            database_name = self.client.get_default_database().name
        except ConfigurationError:
            database_name = "xiel"
        self.raw_db = self.client[database_name]
        self.db = DashboardCollections(self.raw_db)

    async def connect(self):
        if self.client is None or self.db is None:
            return False
        await self.client.admin.command("ping")
        await self.db.guild_settings.create_index([("guildId", ASCENDING)], unique=True)
        await self.db.economy_wallets.create_index([("guildId", ASCENDING), ("userId", ASCENDING)], unique=True)
        await self.db.shop_items.create_index([("guildId", ASCENDING), ("sku", ASCENDING)], unique=True)
        await self.db.premium_grants.create_index(
            [("userId", ASCENDING), ("guildId", ASCENDING), ("commandName", ASCENDING)], unique=True
        )
        await self.db.profile_access.create_index([("userId", ASCENDING), ("guildId", ASCENDING)], unique=True)
        await self.db.global_bans.create_index([("userId", ASCENDING)], unique=True)
        await self.db.web_sessions.create_index(
            [("sid", ASCENDING)],
            unique=True,
            partialFilterExpression={"sid": {"$type": "string"}},
        )
        await self.db.web_sessions.create_index([("familyId", ASCENDING)])
        await self.db.web_sessions.create_index([("expiresAt", ASCENDING)], expireAfterSeconds=0)
        self.available = True
        return True

    async def close(self):
        self.available = False
        if self.client is not None:
            await self.client.close()


def public_document(document):
    if document is None:
        return None
    result = dict(document)
    if "_id" in result:
        result["_id"] = str(result["_id"])
    return result


def object_id(value: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise ValueError("Invalid record ID")
    return ObjectId(value)
