"""Serving the built frontend from the API process."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shabetz.api.static import find_static_dir, mount_frontend


@pytest.fixture
def build(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>")
    (dist / "assets" / "app.js").write_text("console.log('app')")
    (dist / "favicon.svg").write_text("<svg/>")
    (tmp_path / "secret.txt").write_text("do not serve")
    return dist


@pytest.fixture
def client(build: Path) -> TestClient:
    app = FastAPI()

    @app.get("/api/ping")
    def ping() -> dict:
        return {"ok": True}

    mount_frontend(app, build)
    return TestClient(app)


def test_root_serves_the_app(client: TestClient) -> None:
    assert client.get("/").text == "<html>app</html>"


def test_client_side_routes_serve_the_app_so_reloads_work(client: TestClient) -> None:
    response = client.get("/schedule/2026-10-01")
    assert response.status_code == 200
    assert response.text == "<html>app</html>"


def test_assets_and_real_files_are_served(client: TestClient) -> None:
    assert client.get("/assets/app.js").text == "console.log('app')"
    assert client.get("/favicon.svg").text == "<svg/>"


def test_api_routes_win_over_the_catch_all(client: TestClient) -> None:
    assert client.get("/api/ping").json() == {"ok": True}
    assert client.get("/api/missing").status_code == 404


def test_paths_cannot_escape_the_build_directory(client: TestClient) -> None:
    for attempt in ("../secret.txt", "..%2Fsecret.txt", "assets/../../secret.txt"):
        response = client.get(f"/{attempt}")
        assert "do not serve" not in response.text


def test_finds_a_configured_directory(build: Path) -> None:
    assert find_static_dir(str(build)) == build


def test_ignores_a_directory_without_an_index(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    assert find_static_dir(str(empty)) != empty
