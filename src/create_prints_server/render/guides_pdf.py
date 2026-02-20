from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from create_prints_server.domain.guides import (
    compute_order_total,
    filter_orders_requiring_guide,
    normalize_guide_items,
    split_order_date_components,
)
from create_prints_server.domain.money import money_clp


def draw_guide_block(
    c: canvas.Canvas,
    x: float,
    y: float,
    w: float,
    h: float,
    out: Any,
    order_header: Dict[str, Any],
    items: pd.DataFrame,
):
    """Dibuja una guía de despacho en (x,y) con ancho w y alto h.

    Cambios vs versión anterior:
        - Se elimina texto de empresa/subtítulo.
        - Se dibuja el logo arriba a la derecha (como guía física).
        - Se mantiene footer reservado para Total + Firma + Contacto.

    Args:
        c (canvas.Canvas): Canvas reportlab.
        x (float): Coordenada X (izquierda).
        y (float): Coordenada Y (arriba).
        w (float): Ancho del bloque.
        h (float): Alto del bloque.
        out (Any): Config (debe exponer: contact, logo_path, max_items).
        order_header (Dict[str, Any]): Header de la orden.
        items (pd.DataFrame): Ítems de la orden.
    """
    pad = 5
    line = 11

    contact = getattr(out, "contact", "")
    logo_path = getattr(out, "logo_path", None)
    max_items = int(getattr(out, "max_items", 8))

    dd, mm_, yyyy = split_order_date_components(order_header)
    cliente = (
        order_header.get("cliente_nombre", "")
        or order_header.get("cliente", "")
        or ""
    )
    direccion = order_header.get("direccion", "") or ""

    total = compute_order_total(order_header, items)

    bottom = y - h

    # Footer reservado (fijo): evita pisarse con tabla
    sig_y = bottom + 5 * mm
    total_y = bottom + 11 * mm
    footer_top = bottom + 16 * mm

    # Marco exterior
    c.setStrokeColor(colors.black)
    c.rect(x, y - h, w, h, stroke=1, fill=0)

    # Header superior: título a la izquierda + logo a la derecha
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x + pad, y - 16, "GUIA DE DESPACHO")

    # ✅ Logo en vez de title/subtitle
    if logo_path:
        # Similar a guía física: más grande que antes y más arriba
        _draw_logo_safe(
            c=c,
            logo_path=str(logo_path),
            x=x + w - 25 * mm,
            y=y - 5,          # y es top del bloque, -10 lo deja dentro del header
            max_w=40 * mm,
            max_h=10 * mm,
        )

    # Línea separadora del header
    c.line(x, y - 34, x + w, y - 34)

    label_x = x + pad
    row_y = y - 48

    # Fecha / RUT
    c.setFont("Helvetica-Bold", 8)
    c.drawString(label_x, row_y, "DIA")
    c.setFont("Helvetica", 8)
    c.drawString(label_x + 18, row_y, dd)

    c.setFont("Helvetica-Bold", 8)
    c.drawString(label_x + 45, row_y, "MES")
    c.setFont("Helvetica", 8)
    c.drawString(label_x + 70, row_y, mm_)

    c.setFont("Helvetica-Bold", 8)
    c.drawString(label_x + 95, row_y, "AÑO")
    c.setFont("Helvetica", 8)
    c.drawString(label_x + 120, row_y, yyyy[-4:] if yyyy else "")

    # Cliente / Dirección
    row_y -= line
    c.setFont("Helvetica-Bold", 8)
    c.drawString(label_x, row_y, "CLIENTE")
    c.setFont("Helvetica", 8)
    c.drawString(label_x + 55, row_y, str(cliente)[:55])

    row_y -= line
    c.setFont("Helvetica-Bold", 8)
    c.drawString(label_x, row_y, "DIRECCION")
    c.setFont("Helvetica", 7)
    c.drawString(label_x + 55, row_y, str(direccion)[:75])

    # Texto de conformidad
    row_y -= 14
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(
        x + pad,
        row_y,
        "SIRVANSE RECIBIR LO SIGUIENTE EN BUENAS CONDICIONES, QUEDANDO CONFORME",
    )

    # Tabla (top dinámico, bottom reservado por footer)
    row_y -= 6
    table_top = row_y
    table_bottom = max(footer_top, bottom + pad)

    table_h = table_top - table_bottom
    if table_h < 20 * mm:
        table_h = max(16 * mm, table_h)
        table_bottom = table_top - table_h

    # Ajuste filas si queda apretado
    header_inner_h = 14
    min_row_h_pt = 8.5
    n_rows = max_items
    if table_h > header_inner_h:
        row_h_try = (table_h - header_inner_h) / max(1, max_items)
        if row_h_try < min_row_h_pt:
            n_rows = max(1, int((table_h - header_inner_h) / min_row_h_pt))

    items_n = normalize_guide_items(items, max_items=n_rows)

    col1 = x + pad
    col2 = x + w * 0.65
    col3 = x + w * 0.80
    col4 = x + w - pad

    c.setStrokeColor(colors.black)
    c.rect(x + pad, table_bottom, w - 2 * pad, table_h, stroke=1, fill=0)
    c.line(col2, table_bottom, col2, table_top)
    c.line(col3, table_bottom, col3, table_top)

    c.setFont("Helvetica-Bold", 8)
    c.drawString(col1 + 2, table_top - 12, "Producto")
    c.drawRightString(col3 - 4, table_top - 12, "Kilos")
    c.drawRightString(col4 - 2, table_top - 12, "Precio Unitario")

    c.line(x + pad, table_top - 16, x + w - pad, table_top - 16)

    row_h = (table_h - 16) / max(1, n_rows)
    start_y = table_top - 16

    c.setFont("Helvetica", 8)
    for i in range(n_rows):
        y_i = start_y - (i + 1) * row_h
        c.setStrokeColor(colors.black)
        c.line(x + pad, y_i, x + w - pad, y_i)
        c.setStrokeColor(colors.black)

        if i < len(items_n):
            r = items_n.iloc[i]
            prod = str(r.get("producto", "") or "")
            kg = r.get("kg", None)
            pu = r.get("precio_unit", None)

            kg_s = ""
            if kg is not None and not pd.isna(kg):
                try:
                    kg_s = f"{float(kg):.0f}"
                except Exception:
                    kg_s = str(kg)

            c.drawString(col1 + 2, y_i + row_h * 0.28, prod[:48])
            c.drawRightString(col3 - 4, y_i + row_h * 0.28, kg_s)
            c.drawRightString(col4 - 2, y_i + row_h * 0.28, money_clp(pu))

    # Total (siempre arriba del footer)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(x + pad, total_y, "Total")
    c.drawRightString(x + w - pad, total_y, money_clp(total))

    # Firma + Contacto al mismo nivel (texto debajo de la línea)
    c.setFont("Helvetica", 7.5)

    # Línea de firma
    line_y = sig_y
    c.line(x + pad, line_y, x + 70 * mm, line_y)

    # Texto bajo la línea
    text_y = line_y - 9  # ajuste fino visual
    c.drawString(x + pad, text_y, "FIRMA DEL DESPACHADOR")

    # Contacto al mismo nivel que el texto (derecha)
    c.drawRightString(x + w - pad, text_y, str(contact))



def render_guides_pdf(guides: List[Dict[str, Any]], out: Any, pdf_path: str):
    """Renderiza un PDF con guías de despacho (3 por página).

    Args:
        guides (List[Dict[str, Any]]): Estructura tipo `build_orders_structure`.
        out (Any): Config (ver `draw_guide_block`).
        pdf_path (str): Ruta del PDF de salida.
    """
    guides = filter_orders_requiring_guide(guides)

    page_w, page_h = A4
    c = canvas.Canvas(pdf_path, pagesize=A4)

    margin = 12 * mm
    v_gap = 10 * mm

    block_w = page_w - 2 * margin
    block_h = (page_h - 2 * margin - 2 * v_gap) / 3

    x = margin
    y_top = page_h - margin
    cursor_y = y_top

    for idx, od in enumerate(guides):
        draw_guide_block(
            c=c,
            x=x,
            y=cursor_y,
            w=block_w,
            h=block_h,
            out=out,
            order_header=od.get("header", {}) or {},
            items=od.get("items", pd.DataFrame()),
        )

        cursor_y -= block_h + v_gap

        if (idx + 1) % 3 == 0 and (idx + 1) < len(guides):
            c.showPage()
            cursor_y = y_top

    c.save()


def render_pdf_guides(guides: List[Dict[str, Any]], out: Any, pdf_path: str):
    """Alias por compatibilidad para el nombre esperado en `main.py`.

    Args:
        guides (List[Dict[str, Any]]): Guías.
        out (Any): Config.
        pdf_path (str): Ruta PDF.
    """
    render_guides_pdf(guides, out, pdf_path)


def _draw_logo_safe(
    c: canvas.Canvas,
    logo_path: str,
    x: float,
    y: float,
    max_w: float,
    max_h: float,
):
    """Dibuja el logo si existe, sin romper el render si falla.

    Args:
        c (canvas.Canvas): Canvas.
        logo_path (str): Ruta al archivo de imagen.
        x (float): X superior-izq aproximado.
        y (float): Y superior-izq aproximado.
        max_w (float): Ancho máximo.
        max_h (float): Alto máximo.
    """
    try:
        img = ImageReader(logo_path)
        iw, ih = img.getSize()
        if iw <= 0 or ih <= 0:
            return

        scale = min(max_w / float(iw), max_h / float(ih))
        w = float(iw) * scale
        h = float(ih) * scale

        c.drawImage(
            img,
            x,
            y - h,
            width=w,
            height=h,
            preserveAspectRatio=True,
            mask="auto",
        )
    except Exception:
        return
