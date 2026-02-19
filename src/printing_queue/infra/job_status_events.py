from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from printing_queue.models import PrintJobStatus, PrintJobStatusEvent


def try_record_print_job_status_event(
    db: Session,
    *,
    job_id: int,
    from_status: PrintJobStatus | None,
    to_status: PrintJobStatus,
    occurred_at: datetime,
    source: str,
) -> None:
    """Registra (best-effort) un evento de cambio de estado para un job.

    La escritura es opcional y no debe romper el flujo principal (generación/
    impresión). Si falla, hace rollback de *este* intento y retorna.

    Args:
        db: Sesión de DB.
        job_id: ID del job.
        from_status: Estado anterior (puede ser None si es el evento inicial).
        to_status: Estado nuevo.
        occurred_at: Timestamp del cambio.
        source: Fuente del cambio (por ejemplo: api, generate_worker, print_worker).
    """
    try:
        db.add(
            PrintJobStatusEvent(
                job_id=job_id,
                from_status=from_status,
                to_status=to_status,
                occurred_at=occurred_at,
                source=source,
            )
        )
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
