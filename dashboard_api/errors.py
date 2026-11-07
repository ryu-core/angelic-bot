from __future__ import annotations

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pymongo.errors import DuplicateKeyError
from starlette.exceptions import HTTPException


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details=None):
        self.status = status
        self.code = code
        self.message = message
        self.details = details


async def api_error_handler(_request: Request, error: ApiError):
    payload = {"code": error.code, "message": error.message}
    if error.details is not None:
        payload["details"] = error.details
    return JSONResponse({"error": payload}, status_code=error.status)


async def validation_error_handler(_request: Request, error: RequestValidationError):
    return JSONResponse(
        {"error": {
            "code": "VALIDATION_ERROR",
            "message": "The request contains invalid data.",
            "details": jsonable_encoder(error.errors()),
        }},
        status_code=422,
    )


async def duplicate_key_handler(_request: Request, _error: DuplicateKeyError):
    return JSONResponse(
        {"error": {"code": "CONFLICT", "message": "A record with those values already exists."}},
        status_code=409,
    )


async def http_error_handler(_request: Request, error: HTTPException):
    code = "NOT_FOUND" if error.status_code == 404 else "METHOD_NOT_ALLOWED" if error.status_code == 405 else "HTTP_ERROR"
    message = str(error.detail) if error.detail else "The request could not be completed."
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=error.status_code)
