from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any
from print_server.infra.logging import get_logger

from sqlalchemy import select
from sqlalchemy.orm import Session

from printing_queue.db import SessionLocal
from printing_queue.infra.observability import capture_exception, init_sentry
from printing_queue.models import PrintJob, PrintJobStatus
from print_server.infra.printer import print_pdf_windows_sumatra
from print_server.config.settings import settings


logger = get_logger(__name__)


def _files_from_payload(payload: dict[str, Any]) -> list[str]:
    """Extrae y valida la lista de PDFs a imprimir desde payload.

    Formato esperado:
      payload["files"] = ["path1.pdf", "path2.pdf", ...]

    Args:
        payload (dict[str, Any]): Payload del job.

    Returns:
        list[str]: Lista de rutas válidas (no vacías).
    """
    files = payload.get("files", [])
    if not isinstance(files, list):
        return []
    return [str(p).strip() for p in files if str(p).strip()]


def _claim_next_job(db: Session) -> PrintJob | None:
    """Reclama el siguiente job READY usando bloqueo para evitar colisiones.

    Args:
        db (Session): Sesión de BD.

    Returns:
        PrintJob | None: Job reclamado o None si no hay.
    """
    stmt = (
        select(PrintJob)
        .where(PrintJob.status == PrintJobStatus.READY)
        .order_by(PrintJob.created_at.asc())
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    job = db.execute(stmt).scalars().first()
    if not job:
        return None

    logger.info(f"Job READY reclamado id={job.id}")
    job.status = PrintJobStatus.PRINTING
    job.updated_at = datetime.now()
    db.commit()
    db.refresh(job)
    return job


def _mark_done(db: Session, job: PrintJob, payload_extra: dict[str, Any]) -> None:
    """Marca el job como exitoso.

    Args:
        db (Session): Sesión de BD.
        job (PrintJob): Job a actualizar.
        payload_extra (dict[str, Any]): Datos a mezclar en payload.
    """
    job.status = PrintJobStatus.DONE
    job.updated_at = datetime.now()
    job.printed_at = datetime.now()
    job.error_msg = None
    job.payload = {**(job.payload or {}), **payload_extra}
    db.commit()
    logger.info(f"Job impreso OK id={job.id} archivos={payload_extra.get('printed_files')}")


def _mark_error(db: Session, job: PrintJob, err: Exception) -> None:
    """Marca el job como fallido.

    Args:
        db (Session): Sesión de BD.
        job (PrintJob): Job a actualizar.
        err (Exception): Error ocurrido.
    """
    job.status = PrintJobStatus.ERROR
    job.updated_at = datetime.now()
    job.error_msg = str(err)
    db.commit()
    capture_exception(err)
    logger.exception(f"Job fallido id={job.id}")


def _print_files(files: list[str]) -> list[str]:
    """Imprime una lista de PDFs y retorna los que se imprimieron.

    Args:
        files (list[str]): Rutas a PDFs.

    Returns:
        list[str]: Rutas impresas.

    Raises:
        RuntimeError: Si algún archivo no existe o falla la impresión.
    """
    printed: list[str] = []
    for p in files:
        pdf = Path(p)
        if not pdf.exists():
            raise RuntimeError(f"PDF no existe: {pdf}")
        logger.info(f"Imprimiendo PDF {pdf}")
        print_pdf_windows_sumatra(str(pdf))
        printed.append(str(pdf))
    return printed


def run_worker() -> None:
    """Loop principal: toma jobs READY y los imprime."""
    init_sentry("print_worker")
    logger.info(f"Worker iniciado, buscando jobs para imprimir...")
    while True:
        db = SessionLocal()
        try:
            job = _claim_next_job(db)
            if not job:
                # logger.info(f"Sin jobs READY; sleep {settings.POLL_SECONDS}s")
                time.sleep(settings.POLL_SECONDS)
                continue

            try:
                payload = job.payload or {}
                files = _files_from_payload(payload)

                if not files:
                    raise RuntimeError("Job READY sin payload.files para imprimir.")

                logger.info(f"Job id={job.id} iniciando impresión de {len(files)} archivos")
                printed = _print_files(files)

                _mark_done(
                    db,
                    job,
                    {
                        "printed_files": printed,
                        "printed_at": datetime.now().isoformat(),
                    },
                )

            except Exception as e:
                _mark_error(db, job, e)

        finally:
            db.close()


if __name__ == "__main__":
    run_worker()
