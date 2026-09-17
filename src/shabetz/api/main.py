"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..config import get_settings
from .errors import install_handlers
from .routes import auth_routes, config_routes, meta_routes, schedule_routes, timeoff_routes


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
    ):
        app.include_router(module.router)

    return app


app = create_app()
