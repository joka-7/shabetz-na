"""The database session must be committed before the reply is sent.

With FastAPI's default, a dependency's exit code runs after the response has
gone out. The browser asks for the next thing the instant sign-up or sign-in
replies, so on a database that takes a moment to commit (a remote one, as on
the hosted site) that request raced the commit and met "session expired" or an
empty project list. ``scope="function"`` runs the commit before the reply.

Every place that asks for the session must say so: FastAPI keeps one session
per scope, so a single place that forgot would also open a second session.
"""

from __future__ import annotations

import importlib
import pkgutil

from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from shabetz.api import routes
from shabetz.api.deps import get_db


def _uses(dependant: Dependant, found: list[Dependant]) -> None:
    for dependency in dependant.dependencies:
        if dependency.call is get_db:
            found.append(dependency)
        _uses(dependency, found)


def test_every_use_of_the_session_commits_before_the_reply() -> None:
    uses: list[Dependant] = []
    # Each routes module, so one added later is checked too.
    for info in pkgutil.iter_modules(routes.__path__):
        router = getattr(importlib.import_module(f"{routes.__name__}.{info.name}"), "router", None)
        for route in getattr(router, "routes", []):
            if isinstance(route, APIRoute):
                _uses(route.dependant, uses)

    assert uses, "no route asks for the database session; the check is not looking at anything"
    assert [u for u in uses if u.scope != "function"] == []
