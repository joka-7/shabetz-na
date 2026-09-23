# PyInstaller build for the desktop executable.
#
#   uv run --extra build --extra desktop pyinstaller packaging/shabetz.spec
#
# The frontend must be built and copied to src/shabetz/web first; see
# `make desktop`. Produces dist/Shabetz/ (a folder, which starts faster and trips
# antivirus heuristics far less often than a single self-extracting file); the
# Windows installer wraps that folder.

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parent
PACKAGE = ROOT / "src" / "shabetz"

if not (PACKAGE / "web" / "index.html").is_file():
    raise SystemExit(
        "The frontend has not been built into src/shabetz/web. Run `make desktop`."
    )

datas = [
    # Loaded from disk at runtime rather than imported, so they have to ship as
    # files: the app upgrades its own database on launch.
    (str(PACKAGE / "db" / "migrations"), "shabetz/db/migrations"),
    (str(PACKAGE / "exporters" / "templates"), "shabetz/exporters/templates"),
    (str(PACKAGE / "web"), "shabetz/web"),
]

hiddenimports = [
    # uvicorn chooses its protocol and loop implementations by name at runtime,
    # which static analysis cannot see.
    *collect_submodules("uvicorn"),
    # Alembic loads the migration environment and revisions from the files
    # above rather than importing them, so analysis never sees their imports.
    "logging.config",
    "sqlalchemy.dialects.sqlite",
    "sqlalchemy.dialects.mysql",
]

if sys.platform == "win32":
    hiddenimports += collect_submodules("webview")

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    datas=datas,
    hiddenimports=hiddenimports,
    # The desktop app never uses these; leaving them out keeps the download
    # smaller and avoids bundling native libraries it would never load.
    excludes=["weasyprint", "pymysql", "tkinter", "pytest", "mypy", "ruff"],
    noarchive=False,
)
pyz = PYZ(a.pure)

icon = ROOT / "packaging" / "shabetz.ico"

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Shabetz",
    # A windowed program: no console flashes up behind the app.
    console=False,
    icon=str(icon) if icon.is_file() else None,
)

coll = COLLECT(exe, a.binaries, a.datas, name="Shabetz")
