from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base declarativa para modelos ORM."""


class PrintJobStatus(str, enum.Enum):
    """Estados posibles de un job de impresión."""

    PENDING = "pending"
    GENERATING = "generating"
    READY = "ready"
    PRINTING = "printing"
    DONE = "done"
    ERROR = "error"


class PrintJobType(str, enum.Enum):
    """Tipos de job soportados."""

    SHIPPING_DOCS = "shipping_docs"
    UPLOAD = "upload"


class PrintJob(Base):
    """Modelo de cola de impresión."""

    __tablename__ = "print_jobs"
    __table_args__ = {"schema": "printing"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_type: Mapped[PrintJobType] = mapped_column(
        PGEnum(
            PrintJobType,
            name="print_job_type",
            schema="printing",
            create_type=False,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
            validate_strings=True,
        ),
        nullable=False,
    )

    status: Mapped[PrintJobStatus] = mapped_column(
        PGEnum(
            PrintJobStatus,
            name="print_job_status",
            schema="printing",
            create_type=False,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
            validate_strings=True,
        ),
        nullable=False,
        default=PrintJobStatus.PENDING,
    )

    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, default=datetime.now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, default=datetime.now
    )
    printed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)

    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)


class PrintJobStatusEvent(Base):
    """Evento de cambio de estado de un job.

    Se usa para auditoría y para poder calcular tiempos entre estados en
    dashboards (Grafana/SQL).

    Nota:
        Este modelo no requiere migración sobre `printing.print_jobs` porque es
        una tabla nueva. `Base.metadata.create_all(...)` la crea si no existe.
    """

    __tablename__ = "print_job_status_events"
    __table_args__ = {"schema": "printing"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("printing.print_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    from_status: Mapped[PrintJobStatus | None] = mapped_column(
        PGEnum(
            PrintJobStatus,
            name="print_job_status",
            schema="printing",
            create_type=False,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
            validate_strings=True,
        ),
        nullable=True,
    )

    to_status: Mapped[PrintJobStatus] = mapped_column(
        PGEnum(
            PrintJobStatus,
            name="print_job_status",
            schema="printing",
            create_type=False,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
            validate_strings=True,
        ),
        nullable=False,
    )

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        default=datetime.now,
        index=True,
    )

    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
