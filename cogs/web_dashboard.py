"""FastAPI dashboard v2 hosted inside the existing Python bot process."""

from __future__ import annotations

import asyncio
import importlib.util
import os
import subprocess
import sys

import discord
from discord.ext import commands


def _ensure_dashboard_dependencies():
    """Install dashboard dependencies when a panel starts without provisioning them."""
    required_packages = {
        "fastapi": "fastapi==0.139.2",
        "uvicorn": "uvicorn==0.51.0",
        "socketio": "python-socketio==5.16.3",
        "pymongo": "pymongo==4.17.0",
        "itsdangerous": "itsdangerous==2.2.0",
    }
    missing_modules = [
        module_name
        for module_name in required_packages
        if importlib.util.find_spec(module_name) is None
    ]
    if not missing_modules:
        return

    install_command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-cache-dir",
        *(required_packages[module_name] for module_name in missing_modules),
    ]

    print(
        "Installing missing dashboard dependencies "
        f"({', '.join(missing_modules)})..."
    )
    try:
        subprocess.run(install_command, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(
            "Dashboard dependencies could not be installed automatically. "
            f"Command failed: {' '.join(install_command)}"
        ) from exc

    importlib.invalidate_caches()
    unresolved_modules = [
        module_name
        for module_name in missing_modules
        if importlib.util.find_spec(module_name) is None
    ]
    if unresolved_modules:
        raise RuntimeError(
            "Dashboard dependency installation completed, but "
            f"{', '.join(unresolved_modules)} is still unavailable to "
            f"{sys.executable}."
        )

    print("Dashboard dependencies installed successfully.")


_ensure_dashboard_dependencies()

import uvicorn

from dashboard_api import create_dashboard_app


class WebDashboard(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.port = int(os.getenv("DASHBOARD_PORT", os.getenv("WEB_PORT", "10300")))
        self.server: uvicorn.Server | None = None
        self.server_task: asyncio.Task | None = None
        self.database = None

    async def cog_load(self):
        if self.bot.is_ready():
            self._ensure_started()

    def cog_unload(self):
        if self.server:
            self.server.should_exit = True
        elif self.server_task and not self.server_task.done():
            self.server_task.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        self._ensure_started()

    async def _guild_settings(self, guild_id: int):
        if self.database is None or not getattr(self.database, "available", False):
            return None
        try:
            return await self.database.db.guild_settings.find_one({"guildId": str(guild_id)})
        except Exception as exc:
            print(f"Dashboard settings lookup failed for {guild_id}: {exc}")
            return None

    @staticmethod
    def _render_member_message(template: str, member: discord.Member) -> str:
        return (template or "").replace("{user}", member.mention).replace(
            "{username}", str(member)
        ).replace("{server}", member.guild.name).replace(
            "{count}", str(member.guild.member_count or 0)
        )

    async def _send_member_message(self, member: discord.Member, section: dict | None, fallback: str):
        if not section or not section.get("enabled") or not str(section.get("channelId", "")).isdigit():
            return
        channel = member.guild.get_channel(int(section["channelId"]))
        if not channel or not hasattr(channel, "send"):
            return
        message = self._render_member_message(section.get("message") or fallback, member)
        if message:
            try:
                await channel.send(
                    message,
                    allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
                )
            except discord.HTTPException as exc:
                print(f"Dashboard member message failed in {member.guild.id}: {exc}")

    async def _send_invite_log(self, member: discord.Member, channel_id: str, action: str):
        if not str(channel_id or "").isdigit():
            return
        channel = member.guild.get_channel(int(channel_id))
        if channel and hasattr(channel, "send"):
            try:
                await channel.send(
                    f"{member.mention} {action} **{member.guild.name}** (`{member.id}`).",
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except discord.HTTPException as exc:
                print(f"Dashboard invite log failed in {member.guild.id}: {exc}")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if self.database is not None and getattr(self.database, "available", False):
            try:
                record = await self.database.db.global_bans.find_one({"userId": str(member.id)})
                if record and member.guild.me and member.guild.me.guild_permissions.ban_members:
                    await member.ban(reason=f"Global ban: {record.get('reason', 'Dashboard enforcement')}")
                    return
            except Exception as exc:
                print(f"Global ban enforcement failed in {member.guild.id}: {exc}")
        settings = await self._guild_settings(member.guild.id)
        if settings:
            await self._send_member_message(member, settings.get("welcome"), "Welcome {user} to {server}!")
            await self._send_invite_log(member, settings.get("inviteLog", {}).get("joinChannelId", ""), "joined")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        settings = await self._guild_settings(member.guild.id)
        if settings:
            await self._send_member_message(member, settings.get("leave"), "{username} left {server}.")
            await self._send_invite_log(member, settings.get("inviteLog", {}).get("leaveChannelId", ""), "left")

    def _ensure_started(self):
        if self.server_task and not self.server_task.done():
            return
        self.server_task = asyncio.create_task(self._serve(), name="xiel-dashboard-fastapi")

    async def _serve(self):
        try:
            asgi_app, fastapi_app = create_dashboard_app(self.bot)
            self.database = fastapi_app.state.database
            config = uvicorn.Config(
                asgi_app,
                host="0.0.0.0",
                port=self.port,
                log_level="info",
                proxy_headers=True,
                forwarded_allow_ips="*",
                access_log=False,
            )
            self.server = uvicorn.Server(config)
            print("Dashboard frontend: using prebuilt React assets (Node.js is not required at runtime).")
            print(f"Starting dashboard v2.1.0 (FastAPI + React) on port {self.port}...")
            await self.server.serve()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"Dashboard v2.1.0 failed to start: {exc}")


async def setup(bot):
    await bot.add_cog(WebDashboard(bot))
