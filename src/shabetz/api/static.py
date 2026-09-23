"""Serving the built frontend from the API process.

One process on one origin: that is what lets the session cookie, CSRF header and
file downloads work without CORS, whether the app is the desktop executable or a
hosted server.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Paths the frontend must never shadow. An unknown API route should be a JSON
# 404, not the app's index page with a 200.
RESERVED_PREFIXES = ("api/", "docs", "redoc", "openapi.json")


def candidate_dirs(configured: str) -> list[Path]:
    """Where a built frontend may be, most specific first."""
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured))
    # Inside a frozen executable, bundled data sits under the unpack directory.
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        candidates.append(Path(frozen_root) / "shabetz" / "web")
    package_dir = Path(__file__).resolve().parent.parent
    candidates.append(package_dir / "web")
    # A source checkout during development.
    candidates.append(package_dir.parent.parent / "frontend" / "dist")
    return candidates


def find_static_dir(configured: str) -> Path | None:
    for candidate in candidate_dirs(configured):
        if (candidate / "index.html").is_file():
            return candidate
    return None


def mount_frontend(app: FastAPI, static_dir: Path) -> None:
    index = static_dir / "index.html"
    assets = static_dir / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    root = static_dir.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith(RESERVED_PREFIXES):
            raise HTTPException(status_code=404)

        # Serve a real file when one exists, but never one outside the build
        # directory: a path like "../../secrets" must not escape it.
        if path:
            candidate = (root / path).resolve()
            if candidate.is_relative_to(root) and candidate.is_file():
                return FileResponse(candidate)

        # Everything else is a client-side route, so the app decides.
        return FileResponse(index)
