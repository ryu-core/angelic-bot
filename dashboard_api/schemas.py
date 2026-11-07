from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SNOWFLAKE = re.compile(r"^\d{16,22}$")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MessageConfig(StrictModel):
    enabled: bool = False
    channelId: str = ""
    message: str = Field(default="", max_length=1500)

    @field_validator("channelId")
    @classmethod
    def valid_channel(cls, value):
        if value and not SNOWFLAKE.fullmatch(value):
            raise ValueError("channelId must be a Discord ID")
        return value


class AntiNukeModule(StrictModel):
    enabled: bool = False
    threshold: int = Field(default=3, ge=1, le=20)
    punishment: Literal["ban", "kick", "strip", "timeout", "warn"] = "strip"


class AntiNukeModules(StrictModel):
    ban: AntiNukeModule = Field(default_factory=AntiNukeModule)
    kick: AntiNukeModule = Field(default_factory=AntiNukeModule)
    channel: AntiNukeModule = Field(default_factory=AntiNukeModule)
    role: AntiNukeModule = Field(default_factory=AntiNukeModule)
    webhook: AntiNukeModule = Field(default_factory=AntiNukeModule)
    botadd: AntiNukeModule = Field(default_factory=AntiNukeModule)


class AntiNukeConfig(StrictModel):
    enabled: bool = False
    logChannelId: str = ""
    modules: AntiNukeModules = Field(default_factory=AntiNukeModules)

    @field_validator("logChannelId")
    @classmethod
    def valid_log_channel(cls, value):
        if value and not SNOWFLAKE.fullmatch(value):
            raise ValueError("logChannelId must be a Discord ID")
        return value


class InviteLog(StrictModel):
    joinChannelId: str = ""
    leaveChannelId: str = ""

    @field_validator("joinChannelId", "leaveChannelId")
    @classmethod
    def valid_channel(cls, value):
        if value and not SNOWFLAKE.fullmatch(value):
            raise ValueError("invite log channels must be Discord IDs")
        return value


class AccessLists(StrictModel):
    admins: list[str] = Field(default_factory=list, max_length=100)
    whitelist: list[str] = Field(default_factory=list, max_length=250)
    trust: list[str] = Field(default_factory=list, max_length=250)

    @field_validator("admins", "whitelist", "trust")
    @classmethod
    def valid_ids(cls, values):
        if any(not SNOWFLAKE.fullmatch(value) for value in values):
            raise ValueError("access entries must be Discord IDs")
        return list(dict.fromkeys(values))


class SettingsPatch(StrictModel):
    prefix: str | None = Field(default=None, min_length=1, max_length=5)
    antiNuke: AntiNukeConfig | None = None
    welcome: MessageConfig | None = None
    leave: MessageConfig | None = None
    inviteLog: InviteLog | None = None
    access: AccessLists | None = None


class AliasCreate(StrictModel):
    name: str = Field(pattern=r"^[a-z0-9_-]{1,32}$")
    command: str = Field(min_length=1, max_length=160)


class WalletPatch(StrictModel):
    balance: int | None = Field(default=None, ge=0, le=1_000_000_000)
    bank: int | None = Field(default=None, ge=0, le=1_000_000_000)
    streak: int | None = Field(default=None, ge=0, le=100_000)

    @model_validator(mode="after")
    def at_least_one(self):
        if self.balance is None and self.bank is None and self.streak is None:
            raise ValueError("At least one wallet field is required")
        return self


class ShopCreate(StrictModel):
    sku: str = Field(pattern=r"^[a-z0-9_-]{1,40}$")
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=240)
    price: int = Field(ge=0, le=1_000_000_000)
    enabled: bool = True


class ShopPatch(StrictModel):
    sku: str | None = Field(default=None, pattern=r"^[a-z0-9_-]{1,40}$")
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=240)
    price: int | None = Field(default=None, ge=0, le=1_000_000_000)
    enabled: bool | None = None

    @model_validator(mode="after")
    def at_least_one(self):
        if not self.model_fields_set:
            raise ValueError("At least one shop field is required")
        return self


class PremiumGrantCreate(StrictModel):
    userId: str
    guildId: str
    commandName: str = Field(default="all", min_length=1, max_length=80)

    @field_validator("userId", "guildId")
    @classmethod
    def valid_ids(cls, value):
        if not SNOWFLAKE.fullmatch(value):
            raise ValueError("value must be a Discord ID")
        return value


class ProfileGrantCreate(StrictModel):
    userId: str
    guildId: str

    @field_validator("userId", "guildId")
    @classmethod
    def valid_ids(cls, value):
        if not SNOWFLAKE.fullmatch(value):
            raise ValueError("value must be a Discord ID")
        return value


class GlobalBanCreate(StrictModel):
    userId: str
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("userId")
    @classmethod
    def valid_id(cls, value):
        if not SNOWFLAKE.fullmatch(value):
            raise ValueError("userId must be a Discord ID")
        return value


def default_settings(guild_id: str) -> dict:
    return {
        "guildId": guild_id,
        "prefix": ",",
        "antiNuke": AntiNukeConfig().model_dump(),
        "welcome": MessageConfig().model_dump(),
        "leave": MessageConfig().model_dump(),
        "inviteLog": InviteLog().model_dump(),
        "access": AccessLists().model_dump(),
        "aliases": [],
        "updatedBy": "",
    }
