"""Application settings, read from the environment."""

from __future__ import annotations

import secrets
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SHABETZ_", env_file=".env", extra="ignore"
    )

    environment: Literal["dev", "test", "prod"] = "dev"

    database_url: str = Field(
        default="mysql+pymysql://shabetz:shabetz@127.0.0.1:3306/shabetz?charset=utf8mb4"
    )

    secret_key: str = Field(default="")
    session_ttl_hours: int = 12
    cookie_secure: bool = False
    cookie_name: str = "shabetz_session"
    csrf_cookie_name: str = "shabetz_csrf"

    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:5173/auth/google/callback"

    cors_origins: list[str] = Field(default_factory=list)
    max_upload_bytes: int = 5 * 1024 * 1024

    login_max_attempts: int = 8
    login_lockout_minutes: int = 15

    @field_validator("secret_key")
    @classmethod
    def _require_secret_in_prod(cls, value: str, info: object) -> str:
        return value

    @property
    def google_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    def resolved_secret_key(self) -> str:
        """Fail loudly in production rather than minting an ephemeral key.

        A generated key would invalidate every session on each restart and make
        the failure look like random logouts instead of a missing setting.
        """
        if self.secret_key:
            return self.secret_key
        if self.environment == "prod":
            raise RuntimeError(
                "SHABETZ_SECRET_KEY must be set when SHABETZ_ENVIRONMENT=prod"
            )
        return secrets.token_urlsafe(32)


@lru_cache
def get_settings() -> Settings:
    return Settings()
