from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from itsdangerous import BadSignature, URLSafeTimedSerializer
from starlette.middleware.base import BaseHTTPMiddleware


COOKIE_NAME = "xiel.sid"


class MongoSessionMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, database, *, secure: bool, secret: str):
        super().__init__(app)
        self.database = database
        self.secure = secure
        self.serializer = URLSafeTimedSerializer(secret, salt="xiel-dashboard-session")

    async def dispatch(self, request, call_next):
        database_available = bool(
            self.database
            and getattr(self.database, "available", False)
            and getattr(self.database, "db", None) is not None
        )
        signed_sid = request.cookies.get(COOKIE_NAME, "")
        try:
            sid = self.serializer.loads(signed_sid, max_age=60 * 60 * 24 * 7) if signed_sid else ""
        except BadSignature:
            sid = ""
        record = None
        if (
            database_available
            and len(sid) == 64
            and all(character in "0123456789abcdef" for character in sid)
        ):
            record = await self.database.db.web_sessions.find_one({"sid": sid, "expiresAt": {"$gt": datetime.now(UTC)}})
        request.state.session_id = sid if record else None
        request.state.session_family_id = (record or {}).get("familyId") or (sid if record else None)
        request.state.session_presented = bool(sid)
        request.state.session = dict(record.get("data", {})) if record else {}
        request.state.session_touched = False
        request.state.session_destroyed = False
        request.state.session_rotate = False
        request.state.session_allow_create = False
        response = await call_next(request)

        if request.state.session_destroyed:
            family_id = request.state.session_family_id
            session_id = request.state.session_id
            if database_available and (family_id or session_id):
                clauses = []
                if family_id:
                    clauses.append({"familyId": family_id})
                if session_id:
                    clauses.append({"sid": session_id})
                await self.database.db.web_sessions.delete_many({"$or": clauses})
            response.delete_cookie(COOKIE_NAME, path="/")
        elif request.state.session_touched:
            if not database_available:
                response.delete_cookie(COOKIE_NAME, path="/")
                return response
            expires_at = datetime.now(UTC) + timedelta(days=7)
            stored = False
            if request.state.session_id:
                old_sid = request.state.session_id
                new_sid = secrets.token_hex(32) if request.state.session_rotate else old_sid
                family_id = request.state.session_family_id or old_sid
                result = await self.database.db.web_sessions.update_one(
                    {"sid": old_sid},
                    {"$set": {
                        "sid": new_sid,
                        "familyId": family_id,
                        "data": request.state.session,
                        "expiresAt": expires_at,
                    }},
                    upsert=False,
                )
                stored = result.matched_count == 1
                request.state.session_id = new_sid if stored else None
            elif not request.state.session_presented or request.state.session_allow_create:
                new_sid = secrets.token_hex(32)
                await self.database.db.web_sessions.insert_one({
                    "sid": new_sid,
                    "familyId": new_sid,
                    "data": request.state.session,
                    "expiresAt": expires_at,
                })
                request.state.session_id = new_sid
                request.state.session_family_id = new_sid
                stored = True
            if not stored:
                response.delete_cookie(COOKIE_NAME, path="/")
                return response
            response.set_cookie(
                COOKIE_NAME,
                self.serializer.dumps(request.state.session_id),
                max_age=60 * 60 * 24 * 7,
                httponly=True,
                secure=self.secure,
                samesite="lax",
                path="/",
            )
        return response


def touch_session(request):
    request.state.session_touched = True


def rotate_session(request):
    request.state.session_rotate = True
    request.state.session_touched = True


def allow_session_creation(request):
    """Explicitly permit replacing an expired/missing issued session."""
    request.state.session_allow_create = True


def destroy_session(request):
    request.state.session.clear()
    request.state.session_destroyed = True
