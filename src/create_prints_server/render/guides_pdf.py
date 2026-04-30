from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from create_prints_server.domain.guides import (
    compute_order_total,
    normalize_guide_items,
    split_order_date_components,
)
from create_prints_server.domain.money import money_clp


def _fit_text(
    c: canvas.Canvas,
    text: str,
    max_width: float,
    font_name: str,
    font_size: float,
) -> str:
    """Ajusta un texto al ancho disponible usando truncado.

    Args:
        c (canvas.Canvas): Canvas activo.
        text (str): Texto original.
        max_width (float): Ancho máximo disponible.
        font_name (str): Fuente a medir.
        font_size (float): Tamaño de fuente a medir.

    Returns:
        str: Texto original o truncado con sufijo `...`.
    """
    raw = str(text or "")
    if not raw or max_width <= 0:
        return ""

    if c.stringWidth(raw, font_name, font_size) <= max_width:
        return raw

    suffix = "..."
    suffix_w = c.stringWidth(suffix, font_name, font_size)
    if suffix_w >= max_width:
        return suffix

    trimmed = raw
    while trimmed and c.stringWidth(trimmed, font_name, font_size) + suffix_w > max_width:
        trimmed = trimmed[:-1]

    return f"{trimmed.rstrip()}{suffix}"


def _format_total_kilos(items: pd.DataFrame) -> str:
    """Calcula el total de kilos para el resumen visible del talón.

    Args:
        items (pd.DataFrame): Ítems de la guía.

    Returns:
        str: Total de kilos formateado o cadena vacía si no aplica.
    """
    if items.empty or "kg" not in items:
        return ""

    kilos = pd.to_numeric(items["kg"], errors="coerce")
    if not kilos.notna().any():
        return ""

    total_kilos = float(kilos.fillna(0).sum())
    if total_kilos.is_integer():
        return f"{int(total_kilos)}"
    return f"{total_kilos:.1f}"


def _draw_checkbox(
    c: canvas.Canvas,
    x: float,
    y: float,
    label: str,
    size: float = 7,
) -> float:
    """Dibuja un checkbox con label y retorna la siguiente X sugerida.

    Args:
        c (canvas.Canvas): Canvas activo.
        x (float): Coordenada X inicial.
        y (float): Línea base visual del rótulo.
        label (str): Texto del checkbox.
        size (float): Tamaño del cuadrado en puntos.

    Returns:
        float: Posición X sugerida para el siguiente elemento.
    """
    font_name = getattr(c, "_fontname", "Helvetica")
    font_size = float(getattr(c, "_fontsize", 7) or 7)
    box_bottom = y - size + 1

    c.rect(x, box_bottom, size, size, stroke=1, fill=0)
    c.drawString(x + size + 3, box_bottom + 0.2, label)
    return x + size + 3 + c.stringWidth(label, font_name, font_size) + 14


def _draw_receipt_stub(
    c: canvas.Canvas,
    x: float,
    y: float,
    w: float,
    h: float,
    order_header: Dict[str, Any],
    items: pd.DataFrame,
    total: float,
) -> None:
    """Dibuja el talón recortable lateral de recepción y pago.

    Args:
        c (canvas.Canvas): Canvas activo.
        x (float): Coordenada X izquierda del talón.
        y (float): Coordenada Y superior del bloque completo.
        w (float): Ancho reservado para el talón.
        h (float): Alto reservado para el talón.
        order_header (Dict[str, Any]): Cabecera resumida del documento.
        items (pd.DataFrame): Ítems asociados a la guía.
        total (float): Total monetario del documento.
    """
    pad = 6
    left = x + pad
    right = x + w - pad
    top = y - pad
    bottom = y - h + pad

    dd, mm_, yyyy = split_order_date_components(order_header)
    cliente = (
        order_header.get("cliente_nombre", "")
        or order_header.get("cliente", "")
        or ""
    )
    fecha = "/".join(
        part
        for part in [dd, mm_, yyyy[-4:] if yyyy else ""]
        if part
    )
    kilos = _format_total_kilos(items)

    c.saveState()
    c.setDash(5, 3)
    c.line(x, bottom, x, top)
    c.restoreState()

    cursor_y = y - 10
    c.setFont("Helvetica-Bold", 6.9)
    c.drawString(left, cursor_y, "TALON DE RECEPCION")
    cursor_y -= 7
    c.line(left, cursor_y, right, cursor_y)

    cursor_y -= 11
    c.setFont("Helvetica-Bold", 5.9)
    c.drawString(left, cursor_y, "CLIENTE")
    cursor_y -= 7
    c.setFont("Helvetica", 6.2)
    c.drawString(
        left,
        cursor_y,
        _fit_text(c, cliente, right - left, "Helvetica", 6.2),
    )

    cursor_y -= 11
    c.setFont("Helvetica-Bold", 5.9)
    c.drawString(left, cursor_y, "FECHA")
    c.setFont("Helvetica", 6.2)
    c.drawRightString(right, cursor_y, fecha)

    cursor_y -= 11
    c.setFont("Helvetica-Bold", 5.9)
    c.drawString(left, cursor_y, "KILOS")
    c.setFont("Helvetica", 6.2)
    c.drawRightString(right, cursor_y, kilos)

    cursor_y -= 11
    c.setFont("Helvetica-Bold", 5.9)
    c.drawString(left, cursor_y, "TOTAL")
    c.setFont("Helvetica-Bold", 6.9)
    c.drawRightString(right, cursor_y, money_clp(total))

    cursor_y -= 8
    c.line(left, cursor_y, right, cursor_y)

    row_y = cursor_y - 12
    c.setFont("Helvetica-Bold", 6.1)
    c.drawString(left, row_y, "CONDICION")
    c.setFont("Helvetica", 6.5)
    checkbox_y = row_y - 10
    next_x = _draw_checkbox(c, left + 1, checkbox_y, "PAGO", size=5.3)
    _draw_checkbox(c, next_x, checkbox_y, "ABONO", size=5.3)

    row_y = checkbox_y - 17
    c.setFont("Helvetica-Bold", 6.1)
    c.drawString(left, row_y, "METODO DE PAGO")
    c.setFont("Helvetica", 6.3)
    checkbox_y = row_y - 10
    next_x = _draw_checkbox(c, left + 1, checkbox_y, "EFECTIVO", size=5.3)
    next_x = _draw_checkbox(c, next_x, checkbox_y, "CHEQUE", size=5.3)
    _draw_checkbox(c, next_x, checkbox_y, "OTRO", size=5.3)

    signature_line_y = bottom + 15
    signature_label_y = signature_line_y + 12
    # El monto vive entre los checkboxes y la firma, pero ligeramente sesgado
    # hacia arriba para quedar visualmente mas cerca del bloque de pago.
    monto_y = max(signature_label_y + 14, min(signature_label_y + 30, checkbox_y - 12))
    monto_line_x = left + 16 * mm
    c.setFont("Helvetica-Bold", 7)
    c.drawString(left, monto_y, "MONTO")
    c.line(monto_line_x, monto_y - 1, right, monto_y - 1)

    c.setFont("Helvetica-Bold", 7)
    c.drawString(left, signature_label_y, "RECIBE CONFORME")
    c.line(left, signature_line_y, right, signature_line_y)
    c.setFont("Helvetica", 6.1)
    c.drawString(left, bottom + 6, "Firma y nombre")


def _load_logo_image(logo_path: str) -> Image.Image:
    """Carga el logo y recorta el margen transparente del PNG.

    Args:
        logo_path (str): Ruta al archivo del logo.

    Returns:
        Image.Image: Imagen lista para ser escalada.
    """
    pil_image = Image.open(logo_path).convert("RGBA")
    alpha = pil_image.getchannel("A")
    alpha_mask = alpha.point(lambda value: 255 if value >= 8 else 0)
    bbox = alpha_mask.getbbox()
    if bbox:
        return pil_image.crop(bbox)
    return pil_image


def draw_guide_block(
    c: canvas.Canvas,
    x: float,
    y: float,
    w: float,
    h: float,
    out: Any,
    order_header: Dict[str, Any],
    items: pd.DataFrame,
    guide_title: str = "GUIA DE DESPACHO",
):
    """Dibuja una guía de despacho en (x,y) con ancho w y alto h.

    Cambios vs versión anterior:
        - Se elimina texto de empresa/subtítulo.
        - Se dibuja el logo arriba a la derecha (como guía física).
        - El talón recortable pasa al lateral derecho para no quitar alto útil.

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
    pad = 4
    line = 9.5

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
    stub_w = min(max(56 * mm, w * 0.32), w * 0.36)
    main_w = w - stub_w
    main_right = x + main_w
    sig_y = bottom + 16
    total_y = bottom + 28
    footer_top = bottom + 34

    # Marco exterior
    c.setStrokeColor(colors.black)
    c.rect(x, y - h, w, h, stroke=1, fill=0)

    # Header superior: título a la izquierda + logo a la derecha
    c.setFont("Helvetica-Bold", 9.5)
    c.drawString(x + pad, y - 14, guide_title)

    if logo_path:
        title_right = x + pad + c.stringWidth(guide_title, "Helvetica-Bold", 9.5)
        logo_right = main_right - pad - 2
        logo_left = title_right + 10
        logo_max_w = max(0, min(46 * mm, logo_right - logo_left))
        _draw_logo_safe(
            c=c,
            logo_path=str(logo_path),
            x=logo_right,
            y=y - 3,
            max_w=logo_max_w,
            max_h=9 * mm,
            align_right=True,
        )

    # Línea separadora del header
    c.line(x, y - 30, main_right - 6, y - 30)

    label_x = x + pad
    row_y = y - 42
    text_value_x = label_x + 55
    text_max_w = main_right - text_value_x - pad

    c.setFont("Helvetica-Bold", 7.4)
    c.drawString(label_x, row_y, "DIA")
    c.setFont("Helvetica", 7.4)
    c.drawString(label_x + 18, row_y, dd)

    c.setFont("Helvetica-Bold", 7.4)
    c.drawString(label_x + 45, row_y, "MES")
    c.setFont("Helvetica", 7.4)
    c.drawString(label_x + 70, row_y, mm_)

    c.setFont("Helvetica-Bold", 7.4)
    c.drawString(label_x + 95, row_y, "AÑO")
    c.setFont("Helvetica", 7.4)
    c.drawString(label_x + 120, row_y, yyyy[-4:] if yyyy else "")

    row_y -= line
    c.setFont("Helvetica-Bold", 7.4)
    c.drawString(label_x, row_y, "CLIENTE")
    c.setFont("Helvetica", 7.4)
    c.drawString(
        text_value_x,
        row_y,
        _fit_text(c, cliente, text_max_w, "Helvetica", 7.4),
    )

    row_y -= line
    c.setFont("Helvetica-Bold", 7.4)
    c.drawString(label_x, row_y, "DIRECCION")
    c.setFont("Helvetica", 6.6)
    c.drawString(
        text_value_x,
        row_y,
        _fit_text(c, direccion, text_max_w, "Helvetica", 6.6),
    )

    row_y -= 11
    c.setFont("Helvetica-Bold", 7)
    c.drawString(
        x + pad,
        row_y,
        _fit_text(
            c,
            "SIRVANSE RECIBIR LO SIGUIENTE EN BUENAS CONDICIONES, QUEDANDO CONFORME",
            main_w - 2 * pad,
            "Helvetica-Bold",
            7,
        ),
    )

    row_y -= 5
    table_top = row_y
    table_footer_gap = 10
    table_bottom = footer_top + table_footer_gap

    table_h = table_top - table_bottom
    if table_h < 17 * mm:
        table_h = max(14 * mm, table_h)
        table_bottom = table_top - table_h

    header_inner_h = 13
    min_row_h_pt = 8.5
    n_rows = max_items
    if table_h > header_inner_h:
        row_h_try = (table_h - header_inner_h) / max(1, max_items)
        if row_h_try < min_row_h_pt:
            n_rows = max(1, int((table_h - header_inner_h) / min_row_h_pt))

    items_n = normalize_guide_items(items, max_items=n_rows)

    col1 = x + pad
    inner_table_w = main_w - 2 * pad
    col2 = col1 + inner_table_w * 0.63
    col3 = col1 + inner_table_w * 0.80
    col4 = main_right - pad

    c.setStrokeColor(colors.black)
    c.rect(x + pad, table_bottom, inner_table_w, table_h, stroke=1, fill=0)
    c.line(col2, table_bottom, col2, table_top)
    c.line(col3, table_bottom, col3, table_top)

    c.setFont("Helvetica-Bold", 7.2)
    c.drawString(col1 + 2, table_top - 10, "Producto")
    c.drawRightString(col3 - 4, table_top - 10, "Kilos")
    c.drawRightString(col4 - 2, table_top - 10, "Precio Unitario")

    c.line(x + pad, table_top - 14, main_right - pad, table_top - 14)

    row_h = (table_h - 14) / max(1, n_rows)
    start_y = table_top - 14

    c.setFont("Helvetica", 7)
    for i in range(n_rows):
        y_i = start_y - (i + 1) * row_h
        c.setStrokeColor(colors.black)
        c.line(x + pad, y_i, main_right - pad, y_i)
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

            row_text_y = y_i + row_h * 0.24
            c.drawString(
                col1 + 2,
                row_text_y,
                _fit_text(c, prod, col2 - col1 - 6, "Helvetica", 7),
            )
            c.drawRightString(col3 - 4, row_text_y, kg_s)
            c.drawRightString(col4 - 2, row_text_y, money_clp(pu))

    c.setFont("Helvetica-Bold", 8.2)
    c.drawString(x + pad, total_y, "Total")
    c.drawRightString(main_right - pad, total_y, money_clp(total))

    c.setFont("Helvetica", 6.8)
    line_y = sig_y
    c.line(x + pad, line_y, x + pad + (main_w - 2 * pad) * 0.55, line_y)
    text_y = line_y - 7
    c.drawString(x + pad, text_y, "FIRMA DEL DESPACHADOR")
    c.drawRightString(main_right - pad, text_y, str(contact))

    _draw_receipt_stub(
        c,
        main_right,
        y,
        stub_w,
        h,
        order_header=order_header,
        items=items,
        total=total,
    )



def render_guides_pdf(
    guides: List[Dict[str, Any]],
    out: Any,
    pdf_path: str,
    guide_title: str = "GUIA DE DESPACHO",
):
    """Renderiza un PDF con guías de despacho (3 por página).

    Args:
        guides (List[Dict[str, Any]]): Estructura tipo `build_orders_structure`.
        out (Any): Config (ver `draw_guide_block`).
        pdf_path (str): Ruta del PDF de salida.
    """
    page_w, page_h = A4
    c = canvas.Canvas(pdf_path, pagesize=A4)

    top_margin = 12 * mm
    bottom_margin = 40 * mm
    v_gap = 10 * mm

    # Las guias impresas quedaban demasiado cerca del borde inferior fisico.
    # Dejamos una franja de seguridad abajo, similar al aire que ya tiene la
    # lista de despacho, para evitar que la tercera guia se corte al imprimir.
    block_w = page_w - 2 * top_margin
    block_h = (page_h - top_margin - bottom_margin - 2 * v_gap) / 3

    x = top_margin
    y_top = page_h - top_margin
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
            guide_title=guide_title,
        )

        cursor_y -= block_h + v_gap

        if (idx + 1) % 3 == 0 and (idx + 1) < len(guides):
            c.showPage()
            cursor_y = y_top

    c.save()


def render_pdf_guides(
    guides: List[Dict[str, Any]],
    out: Any,
    pdf_path: str,
    guide_title: str = "GUIA DE DESPACHO",
):
    """Alias por compatibilidad para el nombre esperado en `main.py`.

    Args:
        guides (List[Dict[str, Any]]): Guías.
        out (Any): Config.
        pdf_path (str): Ruta PDF.
    """
    render_guides_pdf(guides, out, pdf_path, guide_title=guide_title)


def _draw_logo_safe(
    c: canvas.Canvas,
    logo_path: str,
    x: float,
    y: float,
    max_w: float,
    max_h: float,
    align_right: bool = False,
):
    """Dibuja el logo si existe, sin romper el render si falla.

    Args:
        c (canvas.Canvas): Canvas.
        logo_path (str): Ruta al archivo de imagen.
        x (float): X superior-izq aproximado.
        y (float): Y superior-izq aproximado.
        max_w (float): Ancho máximo.
        max_h (float): Alto máximo.
        align_right (bool): Si es `True`, `x` se interpreta como borde derecho.
    """
    try:
        pil_image = _load_logo_image(logo_path)
        img = ImageReader(pil_image)
        iw, ih = pil_image.size
        if iw <= 0 or ih <= 0:
            return

        scale = min(max_w / float(iw), max_h / float(ih))
        w = float(iw) * scale
        h = float(ih) * scale
        draw_x = x - w if align_right else x

        c.drawImage(
            img,
            draw_x,
            y - h,
            width=w,
            height=h,
            preserveAspectRatio=True,
            mask="auto",
        )
    except Exception:
        return
