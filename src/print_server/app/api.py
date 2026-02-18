from __future__ import annotations

import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session

from printing_queue.db import get_db
from printing_queue.models import PrintJob, PrintJobStatus, PrintJobType
from print_server.config.settings import settings

router = APIRouter(tags=["print_server"])

_jinja = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape(["html", "xml"]),
)


def _render_template(name: str, context: dict[str, Any] | None = None) -> str:
    tpl = _jinja.get_template(name)
    return tpl.render(**(context or {}))


def _ensure_upload_dir() -> Path:
    p = Path(settings.UPLOAD_DIR)
    p.mkdir(parents=True, exist_ok=True)
    return p


@router.get("/", response_class=HTMLResponse)
def index() -> str:
    return _render_template("index.html")


@router.post("/api/print-guides")
def enqueue_guides(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Encola un job para generar e imprimir guías.

    Nota:
        La generación se realiza en un worker. Este endpoint solo encola el job.
    """
    job = PrintJob(
        job_type=PrintJobType.SHIPPING_DOCS,
        status=PrintJobStatus.PENDING,
        payload={"what": "guides", "date": date.today().isoformat()},
        file_path=None,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return {"id": job.id, "status": job.status.value, "job_type": job.job_type.value}


@router.post("/api/print-upload")
async def enqueue_upload(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    filename = (file.filename or "").lower()
    if not (filename.endswith(".pdf") or file.content_type == "application/pdf"):
        raise HTTPException(status_code=400, detail="Solo se permiten archivos PDF.")

    upload_dir = _ensure_upload_dir()
    safe_name = f"{uuid.uuid4().hex}.pdf"
    out_path = upload_dir / safe_name

    content = await file.read()
    out_path.write_bytes(content)

    job = PrintJob(
        job_type=PrintJobType.UPLOAD,
        status=PrintJobStatus.READY,
        payload={
            "original_name": file.filename or "",
            "content_type": file.content_type or "",
            "files": [str(out_path)],
        },
        file_path=str(out_path),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return {"id": job.id, "status": job.status.value, "job_type": job.job_type.value}


@router.get("/api/jobs/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    job = db.get(PrintJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado.")

    return {
        "id": job.id,
        "job_type": job.job_type.value,
        "status": job.status.value,
        "file_path": job.file_path,
        "payload": job.payload,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "printed_at": job.printed_at.isoformat() if job.printed_at else None,
        "error_msg": job.error_msg,
    }
