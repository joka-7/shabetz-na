"""Capability discovery.

The frontend reads this to hide what the deployment cannot do, rather than
offering a button that returns an error.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DbSession

from ...auth.service import setup_is_complete
from ...config import Settings
from ...exporters.renderers import available_formats, pdf_engine_available
from ..deps import get_db, settings_dep
from ..schemas import CapabilitiesOut

router = APIRouter(prefix="/api/meta", tags=["meta"])


@router.get("/capabilities", response_model=CapabilitiesOut)
def capabilities(
    db: DbSession = Depends(get_db), settings: Settings = Depends(settings_dep)
) -> CapabilitiesOut:
    return CapabilitiesOut(
        google_enabled=settings.google_enabled,
        export_formats=[f.value for f in available_formats()],
        pdf_available=pdf_engine_available(),
        setup_complete=setup_is_complete(db),
    )


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}
