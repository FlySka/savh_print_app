from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Literal
from create_prints_server.infra.logging import get_logger

from dotenv import load_dotenv

from create_prints_server.config.settings import OutputConfig
from create_prints_server.domain.orders import build_orders_structure
from create_prints_server.infra.documents_provider import (
    DocumentQuery,
    build_documents_provider,
)
from create_prints_server.render.guides_pdf import render_guides_pdf
from create_prints_server.render.shipping_pdf import render_orders_pdf


DocKind = Literal["shipping_list", "guides", "both", "egreso"]
load_dotenv()
logger = get_logger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_LOGO_PATH = REPO_ROOT / "static" / "images" / "logo_sinfondo.png"


@dataclass(frozen=True)
class GeneratedArtifacts:
    """Resultado de generación de PDFs.

    Attributes:
        shipping_list_path: Ruta del PDF de lista de despacho (si se generó).
        guides_path: Ruta del PDF de guías (si se generó).
        orders_count: Cantidad de pedidos/órdenes del día.
    """

    shipping_list_path: str | None
    guides_path: str | None
    orders_count: int


class NoOrdersForDateError(RuntimeError):
    """Error cuando no hay pedidos para la fecha solicitada."""


def _resolve_logo_path() -> str | None:
    """Resuelve la ruta al logo para PDFs.

    Returns:
        str | None: Ruta configurada o el logo por defecto del repositorio.
    """
    configured = os.getenv("LOGO_PATH") or None
    if configured:
        return configured
    if DEFAULT_LOGO_PATH.exists():
        return str(DEFAULT_LOGO_PATH)
    return None


def _dated_path(original_path: str, day: date) -> str:
    """Crea un path con sufijo de fecha para evitar sobreescritura.

    Ej:
      shipping_list.pdf -> shipping_list_20260213.pdf

    Args:
        original_path: Path original (puede incluir carpeta).
        day: Fecha objetivo.

    Returns:
        str: Path con sufijo de fecha.
    """
    p = Path(original_path)
    stamp = day.strftime("%Y%m%d")
    if p.suffix.lower() != ".pdf":
        return str(p.with_name(f"{p.name}_{stamp}.pdf"))
    return str(p.with_name(f"{p.stem}_{stamp}{p.suffix}"))


def generate_pdfs(
    *,
    what: DocKind,
    day: date,
    venta_id: str | None = None,
) -> GeneratedArtifacts:
    """Genera PDFs (shipping list / guías) para una fecha.

    Args:
        what: Qué generar ("shipping_list", "guides" o "both").
        day: Fecha objetivo.
        venta_id: Si `what == "egreso"`, id de la venta a imprimir.

    Returns:
        GeneratedArtifacts: Paths generados y cantidad de órdenes.

    Raises:
        KeyError: Si faltan variables requeridas del proveedor activo.
        RuntimeError: Si hay error al leer la fuente o renderizar PDFs.
        NoOrdersForDateError: Si no hay ventas para la fecha.
    """
    logger.info(f"Generación solicitada: what={what} day={day.isoformat()}")
    out_cfg = OutputConfig(
        pdf_orders_path=os.getenv("PDF_ORDERS_PATH", "shipping_list.pdf"),
        pdf_guides_path=os.getenv("PDF_GUIDES_PATH", "guides_list.pdf"),
        title=os.getenv("TITLE", "EMPRESA SAVH INVERSIONES SPA"),
        subtitle=os.getenv("SUBTITLE", "Bodega Los Pinos"),
        max_items=int(os.getenv("MAX_ITEMS", "5")),
        contact=os.getenv("CONTACT", "Contacto: +56 9 1234 5678"),
        logo_path=_resolve_logo_path(),
    )

    # Ajusta nombres de archivo por fecha y, si es egreso, cambia nombre base de guías.
    guides_base = out_cfg.pdf_guides_path
    if what == "egreso":
        p = Path(out_cfg.pdf_guides_path)
        guides_base = str(p.with_name("guides_egreso.pdf"))

    out_cfg = OutputConfig(
        pdf_orders_path=_dated_path(out_cfg.pdf_orders_path, day),
        pdf_guides_path=_dated_path(guides_base, day),
        title=out_cfg.title,
        subtitle=out_cfg.subtitle,
        max_items=out_cfg.max_items,
        contact=out_cfg.contact,
        logo_path=out_cfg.logo_path,
    )

    allowed_types: list[str] | None = ["DESPACHO"]
    if what == "egreso":
        if not venta_id:
            raise ValueError("venta_id es requerido cuando what == 'egreso'")
        allowed_types = ["EGRESO"]

    provider = build_documents_provider()
    det_dia = provider.load_orders_frame(
        DocumentQuery(
            day=day,
            allowed_types=allowed_types,
            venta_id=venta_id,
        )
    )
    logger.info(f"Ventas filtradas para {day.isoformat()}: {len(det_dia)} registros")

    if det_dia.empty:
        raise NoOrdersForDateError(f"No hay ventas para {day.isoformat()}")

    orders = build_orders_structure(det_dia.copy(deep=True))
    guides = build_orders_structure(det_dia.copy(deep=True))

    shipping_path: str | None = None
    guides_path: str | None = None

    if what in ("shipping_list", "both"):
        render_orders_pdf(orders, out_cfg, out_cfg.pdf_orders_path)
        shipping_path = out_cfg.pdf_orders_path
        logger.info(f"Lista de despacho generada en {shipping_path}")

    if what in ("guides", "both", "egreso"):
        guide_title = "GUIA DE EGRESO" if what == "egreso" else "GUIA DE DESPACHO"
        render_guides_pdf(guides, out_cfg, out_cfg.pdf_guides_path, guide_title=guide_title)
        guides_path = out_cfg.pdf_guides_path
        logger.info(f"Guías generadas en {guides_path}")

    result = GeneratedArtifacts(
        shipping_list_path=shipping_path,
        guides_path=guides_path,
        orders_count=len(orders),
    )
    logger.info(
        f"Generación completada: orders_count={result.orders_count} shipping={bool(result.shipping_list_path)} guides={bool(result.guides_path)}"
    )
    return result
