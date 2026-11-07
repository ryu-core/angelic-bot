from __future__ import annotations

import asyncio
import ipaddress
import logging
import time
from collections import OrderedDict, deque
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from urllib.parse import urlsplit

import socketio
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pymongo.errors import DuplicateKeyError
from starlette.exceptions import HTTPException

from .config import load_config
from .database import DashboardDatabase
from .errors import (
    ApiError,
    api_error_handler,
    duplicate_key_handler,
    http_error_handler,
    validation_error_handler,
)
from .routes.auth import router as auth_router
from .routes.economy import router as economy_router
from .routes.privileged import coowner_router, owner_router
from .routes.public import router as public_router
from .routes.servers import router as servers_router
from .routes.settings import router as settings_router
from .runtime_sync import sync_global_ban, sync_premium_grant, sync_profile_grant, sync_settings_document
from .session import COOKIE_NAME, MongoSessionMiddleware
from .status import status_payload


LOGGER = logging.getLogger("xiel.dashboard")


class RateLimiter:
    def __init__(self, limit=120, window=60, max_keys=10_000):
        self.limit = limit
        self.window = window
        self.max_keys = max_keys
        self.hits = OrderedDict()
        self.lock = asyncio.Lock()

    async def allow(self, key: str) -> bool:
        now = time.monotonic()
        cutoff = now - self.window
        async with self.lock:
            while self.hits:
                oldest_key, oldest_hits = next(iter(self.hits.items()))
                while oldest_hits and oldest_hits[0] < cutoff:
                    oldest_hits.popleft()
                if oldest_hits:
                    break
                self.hits.pop(oldest_key)
            hits = self.hits.get(key)
            if hits is None:
                while len(self.hits) >= self.max_keys:
                    self.hits.popitem(last=False)
                hits = deque()
                self.hits[key] = hits
            else:
                self.hits.move_to_end(key)
            while hits and hits[0] < cutoff:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True


def client_address(request: Request) -> str:
    raw_host = request.client.host if request.client else ""
    try:
        return ipaddress.ip_address(raw_host).compressed
    except ValueError:
        return "unknown"


def normalized_origin(value: str) -> str | None:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def create_dashboard_app(bot):
    root = Path(__file__).resolve().parent.parent
    client_dist = root / "web" / "client" / "dist"
    index_file = client_dist / "index.html"
    if not index_file.is_file():
        raise RuntimeError("web/client/dist is missing; upload the prebuilt React client")

    config = load_config(bot)
    database = DashboardDatabase(config.mongo_uri)
    sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins=[config.client_url, config.public_url])
    telemetry_task = None

    async def broadcast_status():
        while True:
            await sio.emit("status:update", status_payload(bot))
            await asyncio.sleep(5)

    async def restore_runtime_record(label: str, function, *args):
        try:
            await asyncio.to_thread(function, *args)
        except Exception:
            LOGGER.exception("Could not restore %s into the legacy bot store", label)

    @asynccontextmanager
    async def lifespan(_app):
        nonlocal telemetry_task
        if config.mongo_uri:
            try:
                await database.connect()
            except Exception as exc:
                print(f"Dashboard MongoDB unavailable; continuing in public mode: {exc}")

        if database.available:
            settings_documents = await database.db.guild_settings.find({}).to_list(length=None)
            if not hasattr(bot, "prefix_cache"):
                bot.prefix_cache = {}
            for document in settings_documents:
                await restore_runtime_record(
                    f"guild settings {document.get('guildId')}",
                    sync_settings_document,
                    bot,
                    document,
                )
            premium_documents = await database.db.premium_grants.find({}).to_list(length=None)
            for document in premium_documents:
                await restore_runtime_record(
                    f"premium grant {document.get('_id')}",
                    sync_premium_grant,
                    document.get("userId", "0"), document.get("guildId", "0"),
                    document.get("commandName", ""), document.get("grantedBy", "0"),
                )
            profile_documents = await database.db.profile_access.find({}).to_list(length=None)
            for document in profile_documents:
                await restore_runtime_record(
                    f"profile grant {document.get('_id')}", sync_profile_grant,
                    document.get("userId", "0"), document.get("guildId", "0"), document.get("grantedBy", "0"),
                )
            ban_documents = await database.db.global_bans.find({}).to_list(length=None)
            for document in ban_documents:
                await restore_runtime_record(
                    f"global ban {document.get('_id')}", sync_global_ban, bot,
                    document.get("userId", "0"), document.get("reason", "Dashboard ban"),
                    document.get("bannedBy", "0"),
                )
        telemetry_task = asyncio.create_task(broadcast_status(), name="dashboard-status-broadcast")
        if database.available and config.discord_client_id and config.discord_client_secret:
            print("Dashboard v2.1.0 MongoDB, OAuth, and telemetry ready.")
        else:
            required = []
            if not config.mongo_uri:
                required.append("MONGODB_URI")
            elif not database.available:
                required.append("a reachable MongoDB service")
            if not config.discord_client_id:
                required.append("DISCORD_CLIENT_ID")
            if not config.discord_client_secret:
                required.append("DISCORD_CLIENT_SECRET")
            print("Dashboard v2.1.0 public site and telemetry ready.")
            print(f"Dashboard management is disabled until configured: {', '.join(required)}")
        try:
            yield
        finally:
            telemetry_task.cancel()
            with suppress(asyncio.CancelledError):
                await telemetry_task
            await database.close()

    app = FastAPI(title="xiel dashboard API", version="2.1.0", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.bot = bot
    app.state.config = config
    app.state.database = database
    app.state.sio = sio
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(DuplicateKeyError, duplicate_key_handler)
    app.add_exception_handler(HTTPException, http_error_handler)

    @app.exception_handler(Exception)
    async def unexpected_error(_request: Request, error: Exception):
        LOGGER.exception("Unhandled dashboard request error", exc_info=error)
        return JSONResponse(
            {"error": {"code": "INTERNAL_ERROR", "message": "The dashboard could not complete this request."}},
            status_code=500,
        )

    app.add_middleware(
        MongoSessionMiddleware,
        database=database,
        secure=config.secure_cookies,
        secret=config.session_secret,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list({config.client_url, config.public_url}),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    limiter = RateLimiter()
    allowed_origins = {
        origin for value in (config.client_url, config.public_url)
        if (origin := normalized_origin(value))
    }

    @app.middleware("http")
    async def security_and_rate_limit(request: Request, call_next):
        if request.url.path.startswith("/api/"):
            client_ip = client_address(request)
            if not await limiter.allow(client_ip):
                return JSONResponse(
                    {"error": {"code": "RATE_LIMITED", "message": "Too many requests. Try again shortly."}},
                    status_code=429,
                )
            if request.method in {"POST", "PATCH", "PUT", "DELETE"} and COOKIE_NAME in request.cookies:
                supplied_origin = normalized_origin(request.headers.get("origin", ""))
                if supplied_origin is None:
                    supplied_origin = normalized_origin(request.headers.get("referer", ""))
                if supplied_origin not in allowed_origins:
                    return JSONResponse(
                        {"error": {"code": "CSRF_REJECTED", "message": "Request origin is not allowed."}},
                        status_code=403,
                    )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https://cdn.discordapp.com; "
            "connect-src 'self' wss: https:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
        )
        session = getattr(request.state, "session", {})
        if session.get("user") or request.url.path.startswith("/api/auth/"):
            response.headers["Cache-Control"] = "no-store, private"
            response.headers["Pragma"] = "no-cache"
        if request.url.path.startswith("/api/"):
            vary = {value.strip() for value in response.headers.get("Vary", "").split(",") if value.strip()}
            vary.add("Cookie")
            response.headers["Vary"] = ", ".join(sorted(vary))
        return response

    app.include_router(auth_router)
    app.include_router(public_router)
    app.include_router(servers_router)
    app.include_router(settings_router)
    app.include_router(economy_router)
    app.include_router(owner_router)
    app.include_router(coowner_router)

    assets = client_dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    media = client_dist / "media"
    if media.is_dir():
        app.mount("/media", StaticFiles(directory=media), name="media")

    @app.get("/og.png", include_in_schema=False)
    async def open_graph_image():
        image = client_dist / "og.png"
        if not image.is_file():
            return JSONResponse({"error": {"code": "NOT_FOUND", "message": "Asset not found."}}, status_code=404)
        return FileResponse(image, media_type="image/png")

    @app.get("/favicon.png", include_in_schema=False)
    async def favicon():
        image = client_dist / "favicon.png"
        if not image.is_file():
            return JSONResponse({"error": {"code": "NOT_FOUND", "message": "Asset not found."}}, status_code=404)
        return FileResponse(image, media_type="image/png")

    @app.get("/{page_path:path}", include_in_schema=False)
    async def react_app(page_path: str):
        if page_path.startswith(("api/", "socket.io/")):
            return JSONResponse({"error": {"code": "NOT_FOUND", "message": "Route not found."}}, status_code=404)
        if Path(page_path).suffix:
            return JSONResponse({"error": {"code": "NOT_FOUND", "message": "Asset not found."}}, status_code=404)
        return FileResponse(index_file, headers={"Cache-Control": "no-cache"})

    @sio.event
    async def connect(sid, _environ, _auth):
        await sio.emit("status:update", status_payload(bot), to=sid)

    return socketio.ASGIApp(sio, other_asgi_app=app), app
