from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

import pandas as pd
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from create_prints_server.domain.money import money_clp
from create_prints_server.domain.orders import build_daily_orders
from create_prints_server.infra.google_sheets import sheet_to_df
from printing_queue.db import get_db
from printing_queue.infra.job_status_events import try_record_print_job_status_event
from printing_queue.models import PrintJob, PrintJobStatus, PrintJobType

DocKind = Literal["shipping_list", "guides", "both", "egreso"]

router = APIRouter(tags=["create_prints"])


class EnqueueGenerateRequest(BaseModel):
    """Request para encolar generación/impresión."""

    what: DocKind = Field(
        ..., description="Qué generar: shipping_list, guides, both o egreso."
    )
    day: date | None = Field(None, description="Fecha objetivo. Si es None, usa hoy.")
    venta_id: str | None = Field(
        None, description="Id de la venta (requerido si what == 'egreso')."
    )

    @model_validator(mode="after")
    def _validate_venta_id(self) -> "EnqueueGenerateRequest":
        if self.what == "egreso" and not self.venta_id:
            raise ValueError("venta_id es requerido cuando what == 'egreso'")
        return self


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


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or value == "":
        raise KeyError(f"Falta variable de entorno requerida: {name}")
    return value


def _load_sheets_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Carga dataframes desde Google Sheets usando la config de entorno."""
    sheets_cfg = {
        "SHEETS_ID": _required_env("SHEETS_ID"),
        "CLIENTES_SHEET": _required_env("CLIENTES_SHEET"),
        "DESTINATARIOS_SHEET": _required_env("DESTINATARIOS_SHEET"),
        "VENTAS_SHEET": _required_env("VENTAS_SHEET"),
        "DETALLE_SHEET": _required_env("DETALLE_SHEET"),
        "CLIENTES_RANGE": _required_env("CLIENTES_RANGE"),
        "DESTINATARIOS_RANGE": _required_env("DESTINATARIOS_RANGE"),
        "VENTAS_RANGE": _required_env("VENTAS_RANGE"),
        "DETALLE_RANGE": _required_env("DETALLE_RANGE"),
    }

    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    creds = Credentials.from_service_account_file(
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"],
        scopes=scopes,
    )
    service = build("sheets", "v4", credentials=creds)

    df_clientes = sheet_to_df(
        service,
        sheets_cfg["SHEETS_ID"],
        sheets_cfg["CLIENTES_SHEET"],
        sheets_cfg["CLIENTES_RANGE"],
    )
    df_destinatarios = sheet_to_df(
        service,
        sheets_cfg["SHEETS_ID"],
        sheets_cfg["DESTINATARIOS_SHEET"],
        sheets_cfg["DESTINATARIOS_RANGE"],
    )
    df_ventas = sheet_to_df(
        service,
        sheets_cfg["SHEETS_ID"],
        sheets_cfg["VENTAS_SHEET"],
        sheets_cfg["VENTAS_RANGE"],
    )
    df_det = sheet_to_df(
        service,
        sheets_cfg["SHEETS_ID"],
        sheets_cfg["DETALLE_SHEET"],
        sheets_cfg["DETALLE_RANGE"],
    )
    return df_clientes, df_destinatarios, df_ventas, df_det


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

    payload: dict[str, Any] = {"what": req.what, "date": target_day.isoformat()}
    if req.venta_id:
        payload["venta_id"] = req.venta_id

    job = PrintJob(
        job_type=PrintJobType.SHIPPING_DOCS,
        status=PrintJobStatus.PENDING,
        payload=payload,
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


class EgresoOption(BaseModel):
    """Opción de venta tipo EGRESO disponible para impresión."""

    venta_id: str
    label: str
    cliente: str
    total: int
    total_fmt: str
    destinatario: str | None = None


@router.get("/api/egresos", response_model=list[EgresoOption])
def list_egresos(day: date | None = None) -> list[EgresoOption]:
    """Retorna ventas de tipo EGRESO para la fecha indicada."""
    target_day = day or _today_in_config_timezone()
    dt_day = datetime(target_day.year, target_day.month, target_day.day)

    df_clientes, df_destinatarios, df_ventas, df_det = _load_sheets_data()
    det_dia = build_daily_orders(
        df_clientes,
        df_destinatarios,
        df_ventas,
        df_det,
        pd.to_datetime(dt_day),
        allowed_types=["EGRESO"],
    )

    if det_dia.empty:
        return []

    options: list[EgresoOption] = []
    for venta_id, g in det_dia.groupby("venta_id", sort=False):
        r0 = g.iloc[0]
        cliente = str(r0.get("nombre", "") or r0.get("cliente", "") or "")
        destinatario = str(r0.get("destinatario", "") or "")
        total_venta = (
            int(g["precio_total"].sum(skipna=True)) if "precio_total" in g.columns else 0
        )

        label_cliente = destinatario or cliente or ""
        label_total = money_clp(total_venta)
        label = f"{label_cliente} | {label_total}".strip(" |")

        options.append(
            EgresoOption(
                venta_id=str(venta_id),
                label=label,
                cliente=cliente,
                total=total_venta,
                total_fmt=label_total,
                destinatario=destinatario or None,
            )
        )

    return options
