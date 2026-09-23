"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..config import get_settings
from .errors import install_handlers
from .routes import (
    auth_routes,
    config_routes,
    meta_routes,
    schedule_routes,
    timeoff_routes,
    user_routes,
)
from .static import find_static_dir, mount_frontend


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Shabetz scheduling",
        version="0.1.0",
        description=(
            "Personnel scheduling driven entirely by administrator configuration: "
            "divisions, shift windows, skills and the proficiency ladder are all data."
        ),
    )

    # Only enabled for a split-origin deployment; in development the frontend
    # proxies /api so requests are same-origin and cookies simply work.
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    install_handlers(app)
    for module in (
        meta_routes,
        auth_routes,
        config_routes,
        schedule_routes,
        timeoff_routes,
        user_routes,
    ):
        app.include_router(module.router)

    # Registered last so API routes always win over the frontend's catch-all.
    static_dir = find_static_dir(settings.static_dir)
    if static_dir is not None:
        mount_frontend(app, static_dir)

    return app


app = create_app()
