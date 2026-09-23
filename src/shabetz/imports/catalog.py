"""Adding many named things at once without creating duplicates.

Names are matched ignoring case and surrounding or repeated spaces, so pasting
the same list twice, or a list that overlaps what exists, adds only what is
missing. A row removed earlier (removal is a soft delete) is brought back
rather than duplicated, which the unique name columns would refuse anyway.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import models as orm


def name_key(name: str) -> str:
    return " ".join(name.split()).casefold()


def clean_names(names: list[str]) -> list[str]:
    """Trimmed, blank-free, first-occurrence-wins list of names."""
    seen: set[str] = set()
    result: list[str] = []
    for raw in names:
        name = " ".join(raw.split())
        key = name.casefold()
        if name and key not in seen:
            seen.add(key)
            result.append(name)
    return result


T = TypeVar("T")


@dataclass
class EnsureResult(Generic[T]):
    rows: dict[str, T] = field(default_factory=dict)  # by name_key
    created: list[str] = field(default_factory=list)
    existing: list[str] = field(default_factory=list)


def ensure_divisions(db: Session, names: list[str]) -> EnsureResult[orm.Division]:
    result: EnsureResult[orm.Division] = EnsureResult()
    all_rows = {name_key(row.name): row for row in db.scalars(select(orm.Division))}
    next_order = (db.scalar(select(func.max(orm.Division.display_order))) or 0) + 1
    for name in clean_names(names):
        key = name_key(name)
        row = all_rows.get(key)
        if row is not None and row.is_active:
            result.existing.append(row.name)
        elif row is not None:
            # Brought back at the end of the rotation, as a new one would be.
            row.is_active = True
            row.display_order = next_order
            next_order += 1
            result.created.append(row.name)
        else:
            row = orm.Division(name=name, display_order=next_order)
            next_order += 1
            db.add(row)
            all_rows[key] = row
            result.created.append(name)
        result.rows[key] = row
    db.flush()
    return result


def ensure_skills(db: Session, names: list[str]) -> EnsureResult[orm.Skill]:
    result: EnsureResult[orm.Skill] = EnsureResult()
    all_rows = {name_key(row.name): row for row in db.scalars(select(orm.Skill))}
    for name in clean_names(names):
        key = name_key(name)
        row = all_rows.get(key)
        if row is not None and row.is_active:
            result.existing.append(row.name)
        elif row is not None:
            row.is_active = True
            result.created.append(row.name)
        else:
            row = orm.Skill(name=name)
            db.add(row)
            all_rows[key] = row
            result.created.append(name)
        result.rows[key] = row
    db.flush()
    return result


def ensure_levels(db: Session, names: list[str]) -> EnsureResult[orm.ProficiencyLevel]:
    """Append levels to the top of the ladder, weakest of the new ones first.

    Ranks are unique across removed levels too, so the next rank is counted
    from every row rather than only the visible ones.
    """
    result: EnsureResult[orm.ProficiencyLevel] = EnsureResult()
    rows = list(db.scalars(select(orm.ProficiencyLevel)))
    active = {name_key(row.name): row for row in rows if row.is_active}
    removed = {name_key(row.name): row for row in rows if not row.is_active}
    next_rank = max((row.rank for row in rows), default=-1) + 1
    for name in clean_names(names):
        key = name_key(name)
        if key in active:
            result.existing.append(active[key].name)
            result.rows[key] = active[key]
            continue
        row = removed.pop(key, None)
        if row is None:
            row = orm.ProficiencyLevel(name=name, rank=next_rank)
            db.add(row)
        else:
            row.is_active = True
            row.rank = next_rank
        next_rank += 1
        active[key] = row
        result.created.append(row.name)
        result.rows[key] = row
    db.flush()
    return result
