from __future__ import annotations

import os
import time
from datetime import date, datetime
from typing import Any
from create_prints_server.infra.logging import get_logger

from sqlalchemy import select
from sqlalchemy.orm import Session

from create_prints_server.app.generator import NoOrdersForDateError, generate_pdfs
from printing_queue.db import SessionLocal, engine
from printing_queue.infra.job_status_events import try_record_print_job_status_event
from printing_queue.infra.observability import capture_exception, init_sentry
from printing_queue.models import Base, PrintJob, PrintJobStatus, PrintJobType
from printing_queue.settings import settings


DocKind = str
logger = get_logger(__name__)


def _claim_next_job(db: Session) -> PrintJob | None:
    """Reclama el siguiente job PENDING de generación usando bloqueo.
    
    Args:
        db: Sesión de DB.
        
    Returns:
        El job reclamado, o None si no hay jobs PENDING.
    """
    stmt = (
        select(PrintJob)
        .where(PrintJob.status == PrintJobStatus.PENDING)
        .where(PrintJob.job_type == PrintJobType.SHIPPING_DOCS)
        .order_by(PrintJob.created_at.asc())
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    job = db.execute(stmt).scalars().first()
    if not job:
        return None

    logger.info(f"Job reclamado para generación id={job.id}")
    prev_status = job.status
    changed_at = datetime.now()
    job.status = PrintJobStatus.GENERATING
    job.updated_at = changed_at
    db.commit()
    db.refresh(job)
    try_record_print_job_status_event(
        db,
        job_id=job.id,
        from_status=prev_status,
        to_status=job.status,
        occurred_at=changed_at,
        source="generate_worker",
    )
    return job


def _payload_get(payload: dict[str, Any], key: str) -> Any:
    """Helper para obtener un valor del payload con chequeo de existencia.
    
    Args:
        payload: El dict payload del job.
        key: La clave a obtener.
        
    Returns:
        El valor asociado a la clave.
        
    Raises:
        KeyError: Si la clave no existe en el payload.
    """
    value = payload.get(key)
    if value is None:
        raise KeyError(f"payload.{key} es requerido")
    return value


def _process_job(db: Session, job: PrintJob) -> None:
    """Procesa un job de generación: genera los PDFs y actualiza el job a READY o ERROR.
    
    Args:
        db: Sesión de DB.
        job: El job a procesar, que debe estar en estado GENERATING.
        
    Side effects:
        Actualiza el job en la base de datos con el resultado de la generación.
    """
    payload = job.payload or {}
    what: DocKind = str(_payload_get(payload, "what"))
    day = date.fromisoformat(str(_payload_get(payload, "date")))

    try:
        venta_id = payload.get("venta_id")
        logger.info(f"Generando PDFs job_id={job.id} what={what} day={day} venta_id={venta_id}")
        artifacts = generate_pdfs(what=what, day=day, venta_id=venta_id)
        files: list[str] = []
        if artifacts.shipping_list_path:
            files.append(artifacts.shipping_list_path)
        if artifacts.guides_path:
            files.append(artifacts.guides_path)

        job.payload = {
            **payload,
            "orders_count": artifacts.orders_count,
            "files": files,
        }
        prev_status = job.status
        changed_at = datetime.now()
        job.status = PrintJobStatus.READY
        job.updated_at = changed_at
        job.error_msg = None
        db.commit()
        try_record_print_job_status_event(
            db,
            job_id=job.id,
            from_status=prev_status,
            to_status=job.status,
            occurred_at=changed_at,
            source="generate_worker",
        )
        logger.info(f"Job listo id={job.id} orders={artifacts.orders_count} files={files}")

    except NoOrdersForDateError as e:
        job.payload = {**payload, "orders_count": 0, "files": [], "note": str(e)}
        prev_status = job.status
        changed_at = datetime.now()
        job.status = PrintJobStatus.DONE
        job.updated_at = changed_at
        job.error_msg = None
        db.commit()
        try_record_print_job_status_event(
            db,
            job_id=job.id,
            from_status=prev_status,
            to_status=job.status,
            occurred_at=changed_at,
            source="generate_worker",
        )
        logger.info(f"Job sin ventas id={job.id}: {e}")

    except Exception as e:
        prev_status = job.status
        changed_at = datetime.now()
        job.status = PrintJobStatus.ERROR
        job.error_msg = str(e)
        job.updated_at = changed_at
        db.commit()
        try_record_print_job_status_event(
            db,
            job_id=job.id,
            from_status=prev_status,
            to_status=job.status,
            occurred_at=changed_at,
            source="generate_worker",
        )
        capture_exception(e)
        logger.exception(f"Error generando job_id={job.id}")


def run_worker() -> None:
    """Loop principal: toma jobs PENDING (generación) y los deja READY."""
    init_sentry("generate_worker")
    Base.metadata.create_all(bind=engine)
    logger.info(f"Worker iniciado, buscando jobs para generar...")
    heartbeat_seconds = int(os.getenv("WORKER_HEARTBEAT_SECONDS", "60"))
    last_heartbeat = time.monotonic()
    while True:
        db = SessionLocal()
        try:
            job = _claim_next_job(db)
            if not job:
                now = time.monotonic()
                if heartbeat_seconds > 0 and (now - last_heartbeat) >= heartbeat_seconds:
                    logger.info(f"Sin jobs PENDING; sleep {settings.POLL_SECONDS}s")
                    last_heartbeat = now
                time.sleep(settings.POLL_SECONDS)
                continue
            _process_job(db, job)
        finally:
            db.close()


if __name__ == "__main__":
    run_worker()
