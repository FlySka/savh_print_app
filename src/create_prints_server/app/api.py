from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from printing_queue.db import get_db
from printing_queue.infra.job_status_events import try_record_print_job_status_event
from printing_queue.models import PrintJob, PrintJobStatus, PrintJobType

DocKind = Literal["shipping_list", "guides", "both"]

router = APIRouter(tags=["create_prints"])


class EnqueueGenerateRequest(BaseModel):
    """Request para encolar generación/impresión."""

    what: DocKind = Field(..., description="Qué generar: shipping_list, guides o both.")
    day: date | None = Field(None, description="Fecha objetivo. Si es None, usa hoy.")


class EnqueueGenerateResponse(BaseModel):
    """Response al encolar un job."""

    id: int
    status: str
    job_type: str


def _today_in_config_timezone() -> date:
    """Obtiene la fecha 'hoy' según TIMEZONE, con fallback a date.today()."""
    timezone = os.getenv("TIMEZONE", "America/Santiago")
    try:
        return datetime.now(ZoneInfo(timezone)).date()
    except Exception:
        return date.today()


@router.get("/health")
def health() -> dict[str, str]:
    """Healthcheck simple."""
    return {"status": "ok"}


@router.post("/api/jobs/generate", response_model=EnqueueGenerateResponse)
def enqueue_generate(
    req: EnqueueGenerateRequest,
    db: Session = Depends(get_db),
) -> Any:
    """Crea un job para generar PDFs.

    Nota:
        La generación de PDFs es un proceso potencialmente largo. Por diseño no se
        ejecuta en el proceso HTTP. Un worker reclamará el job y lo dejará en
        READY con `payload.files` para que el worker de impresión lo procese.

    Args:
        req: Parámetros del job.
        db: Sesión de BD.

    Returns:
        EnqueueGenerateResponse: Job creado.
    """
    target_day = req.day or _today_in_config_timezone()

    job = PrintJob(
        job_type=PrintJobType.SHIPPING_DOCS,
        status=PrintJobStatus.PENDING,
        payload={"what": req.what, "date": target_day.isoformat()},
        file_path=None,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    try_record_print_job_status_event(
        db,
        job_id=job.id,
        from_status=None,
        to_status=job.status,
        occurred_at=job.created_at,
        source="api",
    )

    return EnqueueGenerateResponse(
        id=job.id,
        status=job.status.value,
        job_type=job.job_type.value,
    )
