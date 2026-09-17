"""Problem responses."""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, code: str, detail: str, status_code: int) -> None:
        self.code = code
        self.detail = detail
        self.status_code = status_code
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
        super().__init__("INVALID_CONFIGURATION", detail, status.HTTP_422_UNPROCESSABLE_ENTITY)


class FeatureUnavailable(ApiError):
    def __init__(self, detail: str) -> None:
        super().__init__("FEATURE_UNAVAILABLE", detail, status.HTTP_503_SERVICE_UNAVAILABLE)


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _handle(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code, content={"code": exc.code, "detail": exc.detail}
        )
