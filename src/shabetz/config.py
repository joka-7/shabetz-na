"""Application settings, read from the environment."""

from __future__ import annotations

import secrets
from functools import lru_cache
from typing import Literal

from pydantic import Field, PrivateAttr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SHABETZ_", env_file=".env", extra="ignore")

    environment: Literal["dev", "test", "prod"] = "dev"

    # "desktop" is the packaged Windows app: one machine, bound to localhost.
    # "server" is a hosted deployment reachable by other people.
    deployment: Literal["server", "desktop"] = "server"

    database_url: str = Field(
        default="mysql+pymysql://shabetz:shabetz@127.0.0.1:3306/shabetz?charset=utf8mb4"
    )

    secret_key: str = Field(default="")
    session_ttl_hours: int = 12
    cookie_secure: bool = False
    cookie_name: str = "shabetz_session"
    csrf_cookie_name: str = "shabetz_csrf"

    # Required to create the first administrator on a server. Without it, a
    # freshly deployed site belongs to whoever happens to load it first.
    setup_token: str = ""

    # Where the built frontend lives. Empty means "look in the usual places".
    static_dir: str = ""

    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:5173/auth/google/callback"

    cors_origins: list[str] = Field(default_factory=list)
    max_upload_bytes: int = 5 * 1024 * 1024

    # The per-address limit must stay below the per-account one. Then guessing
    # from one machine gets that machine throttled long before the targeted
    # account locks, and locking an account out needs many addresses. With
    # these reversed, one attacker could lock the real owner out.
    login_ip_max_failures: int = 20
    login_ip_window_minutes: int = 15
    login_max_attempts: int = 50
    login_lockout_minutes: int = 15

    _ephemeral_secret: str | None = PrivateAttr(default=None)

    @property
    def google_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def setup_token_required(self) -> bool:
        return bool(self.setup_token) or (
            self.deployment == "server" and self.environment == "prod"
        )

    def resolved_secret_key(self) -> str:
        """The signing key, failing loudly in production.

        A generated key would invalidate every session on each restart and make
        the failure look like random logouts instead of a missing setting. In
        development the generated key is kept for the life of this settings
        object: minting a fresh one per call meant a value signed in one request
        could never be verified in the next.
        """
        if self.secret_key:
            return self.secret_key
        if self.environment == "prod":
            raise RuntimeError("SHABETZ_SECRET_KEY must be set when SHABETZ_ENVIRONMENT=prod")
        if self._ephemeral_secret is None:
            self._ephemeral_secret = secrets.token_urlsafe(32)
        return self._ephemeral_secret


@lru_cache
def get_settings() -> Settings:
    return Settings()
