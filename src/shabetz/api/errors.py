"""Problem responses."""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError


class ApiError(Exception):
    def __init__(
        self,
        code: str,
        detail: str,
        status_code: int,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.code = code
        self.detail = detail
        self.status_code = status_code
        self.headers = headers
        super().__init__(detail)


class NotFound(ApiError):
    def __init__(self, detail: str = "Not found") -> None:
        super().__init__("NOT_FOUND", detail, status.HTTP_404_NOT_FOUND)


class Forbidden(ApiError):
    def __init__(self, detail: str = "Not permitted") -> None:
        super().__init__("FORBIDDEN", detail, status.HTTP_403_FORBIDDEN)


class Unauthorized(ApiError):
    def __init__(self, detail: str = "Authentication required") -> None:
        super().__init__("UNAUTHORIZED", detail, status.HTTP_401_UNAUTHORIZED)


class Conflict(ApiError):
    def __init__(self, detail: str) -> None:
        super().__init__("CONFLICT", detail, status.HTTP_409_CONFLICT)


class UnprocessableConfig(ApiError):
    def __init__(self, detail: str) -> None:
        super().__init__("INVALID_CONFIGURATION", detail, status.HTTP_422_UNPROCESSABLE_CONTENT)


class FeatureUnavailable(ApiError):
    def __init__(self, detail: str) -> None:
        super().__init__("FEATURE_UNAVAILABLE", detail, status.HTTP_503_SERVICE_UNAVAILABLE)


class TooManyRequests(ApiError):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(
            "TOO_MANY_REQUESTS",
            "Too many failed attempts from this address; try again later",
            status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": str(retry_after_seconds)},
        )


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _handle(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "detail": exc.detail},
            headers=exc.headers,
        )

    @app.exception_handler(IntegrityError)
    async def _handle_integrity(_: Request, exc: IntegrityError) -> JSONResponse:
        # Usually a unique name: two divisions or skills called the same. A 409
        # lets the page say so instead of reporting a server fault. Anything
        # else -- a row still referenced elsewhere, say -- must not be
        # reported as a duplicate name.
        if is_unique_violation(exc):
            content = {"code": "DUPLICATE", "detail": "That name is already in use"}
        else:
            content = {
                "code": "CONFLICT",
                "detail": "That change conflicts with data that depends on it",
            }
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=content)

    @app.exception_handler(StaleDataError)
    async def _handle_stale(_: Request, exc: StaleDataError) -> JSONResponse:
        # Someone else saved the same schedule between our read and our write.
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "code": "STALE",
                "detail": "Someone else changed this schedule a moment ago; reload and try again",
            },
        )


def is_unique_violation(exc: IntegrityError) -> bool:
    """Whether the database refused a duplicate, as opposed to another constraint."""
    orig = exc.orig
    # PostgreSQL's SQLSTATE, MySQL's error number, then SQLite's wording.
    if getattr(orig, "sqlstate", None) == "23505":
        return True
    args = getattr(orig, "args", ())
    if args and args[0] == 1062:
        return True
    text = str(orig).lower()
    return "unique" in text or "duplicate" in text
