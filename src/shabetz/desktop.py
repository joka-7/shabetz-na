"""The Windows desktop application.

Double-clicking the executable lands here. Everything a technical user would do
by hand happens automatically: the database is created or upgraded in the
user's own folder, a signing key is generated once and kept, the server starts
on this machine only, and the app opens in its own window. Closing the window
stops it.

Nothing listens beyond this machine, so the first-run screen needs no setup
code: there is nobody else who could race to it.
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import os
import secrets
import signal
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

APP_NAME = "Shabetz"
DEFAULT_PORT = 8765
HOST = "127.0.0.1"
STARTUP_TIMEOUT_SECONDS = 30

log = logging.getLogger("shabetz.desktop")


def data_dir() -> Path:
    """Per-user application data, e.g. %LOCALAPPDATA%\\Shabetz on Windows."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
    root = Path(base) if base else Path.home() / ".local" / "share"
    path = root / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_or_create_secret(directory: Path) -> str:
    """A signing key generated on first launch and kept thereafter.

    Regenerating it on every start would sign everyone out each time the app
    was reopened.
    """
    key_file = directory / "secret.key"
    if key_file.exists():
        existing = key_file.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    secret = secrets.token_urlsafe(48)
    key_file.write_text(secret, encoding="utf-8")
    # Windows ignores POSIX modes; LOCALAPPDATA already carries a per-user ACL.
    with contextlib.suppress(OSError):
        key_file.chmod(0o600)
    return secret


def configure_environment(directory: Path) -> str:
    """Point the application at this machine's own database and key."""
    database_url = f"sqlite:///{(directory / 'shabetz.db').as_posix()}"
    os.environ["SHABETZ_DEPLOYMENT"] = "desktop"
    os.environ["SHABETZ_ENVIRONMENT"] = "prod"
    os.environ["SHABETZ_DATABASE_URL"] = database_url
    os.environ["SHABETZ_SECRET_KEY"] = load_or_create_secret(directory)
    os.environ["SHABETZ_DATA_DIR"] = str(directory)
    # Plain http on the loopback interface, so the cookie cannot be Secure.
    os.environ["SHABETZ_COOKIE_SECURE"] = "false"

    from .config import get_settings

    get_settings.cache_clear()
    return database_url


def is_our_app_running(port: int) -> bool:
    """Whether a copy of this app already answers on ``port``.

    A second launch should bring up the running copy rather than fight it for
    the same database file.
    """
    try:
        with urllib.request.urlopen(f"http://{HOST}:{port}/api/meta/health", timeout=1) as r:
            return b'"app":"shabetz"' in r.read().replace(b" ", b"")
    except OSError:
        return False


def port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        # Probe the way the server will actually bind. Without this, a port
        # left in TIME_WAIT by a copy that was just force-closed looks taken
        # even though the server could use it.
        if os.name != "nt":
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((HOST, port))
        except OSError:
            return False
    return True


PORT_FILE = "server.port"


def recorded_port(directory: Path) -> int | None:
    """The port a running copy last announced, if any."""
    try:
        return int((directory / PORT_FILE).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def find_running_copy(directory: Path, default_port: int) -> int | None:
    """Where an already-running copy answers, checking its recorded port first.

    If the default port was busy the app runs elsewhere, so looking only at the
    default would miss it and start a second server on the same database.
    """
    for port in dict.fromkeys(p for p in (recorded_port(directory), default_port) if p):
        if is_our_app_running(port):
            return port
    return None


def pick_port(preferred: int) -> int:
    if port_is_free(preferred):
        return preferred
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((HOST, 0))
        return int(probe.getsockname()[1])


def open_window(url: str) -> bool:
    """Show the app in its own window. False when no native window is possible.

    Uses the WebView2 runtime that ships with current Windows; on a machine
    without it the caller falls back to the default browser.
    """
    try:
        import webview
    except Exception:
        log.warning("Native window unavailable; opening the browser instead")
        return False

    try:
        webview.create_window(APP_NAME, url, width=1360, height=900, min_size=(900, 600))
        webview.start()  # Blocks until the window is closed.
    except Exception:
        log.exception("Native window failed; opening the browser instead")
        return False
    return True


def window_support_self_test() -> int:
    """Exit 0 when the native window can be created on this machine.

    The build's smoke test runs without a window, so without this a bundle
    missing the window libraries would pass the build and then open in the
    browser on every user's machine.
    """
    try:
        import webview  # noqa: F401

        if sys.platform == "win32":
            # WebView2 is driven through the .NET bridge; this is what a bundle
            # most often loses.
            import clr  # type: ignore[import-not-found]  # noqa: F401
    except Exception:
        log.exception("Window libraries are not available")
        return 1
    return 0


def _wait_for(thread: threading.Thread) -> None:
    """Block until ``thread`` ends, still responsive to an interrupt.

    A bare join() never returns control to the interpreter, so Ctrl+C or a
    termination signal could not stop the app; waiting in short slices lets it.
    """
    while thread.is_alive():
        thread.join(timeout=0.5)


def _stop_cleanly_on_terminate() -> None:
    """Treat a termination request like closing the window.

    Windows sends one at logoff and shutdown. By default Python would die on the
    spot, skipping the shutdown that flushes the database and removes the port
    record.
    """

    def _handle(_signum: int, _frame: object) -> None:
        raise KeyboardInterrupt

    with contextlib.suppress(ValueError, OSError):
        signal.signal(signal.SIGTERM, _handle)


def _configure_logging(directory: Path) -> None:
    # The windowed executable has no console, so the log file is the only
    # record of what happened if someone reports a problem.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(directory / "shabetz.log", encoding="utf-8")],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=APP_NAME)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--no-window",
        action="store_true",
        help="Run the server without opening a window (for testing).",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Check the native window libraries are bundled, then exit.",
    )
    args = parser.parse_args(argv)

    directory = data_dir()
    _configure_logging(directory)

    if args.self_test:
        # After logging is set up, so a failure's reason reaches the log file
        # the build prints.
        return window_support_self_test()
    _stop_cleanly_on_terminate()
    log.info("Starting %s; data in %s", APP_NAME, directory)

    running_port = find_running_copy(directory, args.port)
    if running_port is not None:
        url = f"http://{HOST}:{running_port}/"
        log.info("Already running at %s; showing it", url)
        if not open_window(url):
            webbrowser.open(url)
        return 0

    database_url = configure_environment(directory)

    # Imported only now, after the environment points at this machine's
    # database, because settings are read once on import.
    import uvicorn

    from .api.main import create_app
    from .db.migrate import upgrade_to_head

    upgrade_to_head(database_url)

    port = pick_port(args.port)
    server = uvicorn.Server(
        uvicorn.Config(create_app(), host=HOST, port=port, log_config=None, access_log=False)
    )
    thread = threading.Thread(target=server.run, name="shabetz-server", daemon=True)
    thread.start()

    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while not server.started:
        if not thread.is_alive() or time.monotonic() > deadline:
            log.error("Server did not start")
            return 1
        time.sleep(0.05)

    url = f"http://{HOST}:{port}/"
    (directory / PORT_FILE).write_text(str(port), encoding="utf-8")
    log.info("Serving at %s", url)

    try:
        if args.no_window:
            print(f"Serving at {url}", flush=True)
            _wait_for(thread)
        elif not open_window(url):
            webbrowser.open(url)
            # Without a window to close, keep serving until the process ends.
            _wait_for(thread)
    except KeyboardInterrupt:
        pass
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        (directory / PORT_FILE).unlink(missing_ok=True)
        log.info("Stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
