from typing import List

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from create_prints_server.config.settings import OutputConfig
from create_prints_server.domain.money import money_clp


def draw_order_block(
    c: canvas.Canvas,
    x: float,
    y: float,
    w: float,
    h: float,
    out: OutputConfig,
    order_header: dict,
    items: pd.DataFrame,
):
    """
    Dibuja un bloque estilo "pedido" en (x,y) con ancho w y alto h.
    y es la esquina superior (top).
    """

    pad = 6
    line = 12

    # marco
    c.setStrokeColor(colors.black)
    c.rect(x, y - h, w, h, stroke=1, fill=0)

    # header superior: "PEDIDOS" a la izquierda, empresa a la derecha
    c.setFont("Helvetica-Bold", 9)
    c.drawString(x + pad, y - 14, "PEDIDOS")
    c.drawRightString(x + w - pad, y - 14, out.title)

    # subtítulo (bodega)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(x + pad, y - 28, out.subtitle)

    # línea separadora
    c.line(x, y - 34, x + w, y - 34)

    # filas: FECHA, Nombre Cliente, Dirección
    label_x = x + pad
    value_x = x + 70  # ajusta según ancho; esto emula tu planilla
    row_y = y - 50

    c.setFont("Helvetica-Bold", 8)
    c.drawString(label_x, row_y, "FECHA")
    c.setFont("Helvetica", 8)
    c.drawString(value_x, row_y, order_header.get("fecha_str", ""))

    row_y -= line
    c.setFont("Helvetica-Bold", 8)
    c.drawString(label_x, row_y, "Nombre Cliente")
    c.setFont("Helvetica", 8)
    c.drawString(value_x, row_y, order_header.get("cliente_nombre", ""))

    # Kilos de Palta (tabla items)
    row_y -= line + 6
    c.setFont("Helvetica-Bold", 8)
    c.drawString(label_x, row_y, "Kilos de Palta")
    row_y -= 8

    # encabezados ítems: Producto/Calibre/Kg/P.Unit/Total (compacto)
    # columnas internas
    ix = x + pad
    col_prod = ix + 0
    col_cal = ix + 50
    col_kg = ix + 135
    col_pu = ix + 175
    col_pt = ix + 215

    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(col_prod, row_y, "Producto")
    c.drawString(col_cal, row_y, "Calibre")
    c.drawRightString(col_kg, row_y, "Kg")
    c.drawRightString(col_pu, row_y, "P.Unit")
    c.drawRightString(col_pt, row_y, "Total")

    # línea bajo header items
    c.line(x + pad, row_y - 3, x + w - pad, row_y - 3)
    row_y -= 12

    # 5 líneas fijas
    c.setFont("Helvetica", 7.5)
    max_items = out.max_items

    # asegura máximo 5 filas
    items = items.head(max_items).copy()

    # dibuja filas
    for i in range(max_items):
        if i < len(items):
            r = items.iloc[i]
            prod = str(r.get("producto", "") or "")
            cal = str(r.get("calibre", "") or "")
            kg = r.get("kg", "")
            pu = r.get("precio_unit", "")
            pt = r.get("precio_total", "")
            kg_s = "" if pd.isna(kg) else f"{float(kg):.0f}".rstrip(".")
            c.drawString(col_prod, row_y, prod[:24])
            c.drawString(col_cal, row_y, cal[:12])
            c.drawRightString(col_kg, row_y, kg_s)
            c.drawRightString(col_pu, row_y, money_clp(pu))
            c.drawRightString(col_pt, row_y, money_clp(pt))
        # línea guía suave (opcional)
        c.setStrokeColor(colors.lightgrey)
        c.line(x + pad, row_y - 3, x + w - pad, row_y - 3)
        c.setStrokeColor(colors.black)
        row_y -= 12

    # Dirección
    row_y -= 6
    c.setFont("Helvetica-Bold", 8)
    c.drawString(label_x, row_y, "Direccion")
    c.setFont("Helvetica", 5)
    c.drawString(value_x, row_y, order_header.get("direccion", "")[:40])

    # Total destacado al final (banda gris)
    band_h = 18
    c.setFillColor(colors.lightgrey)
    c.rect(x, (y - h) + 0, w, band_h, stroke=0, fill=1)
    c.setFillColor(colors.black)

    c.setFont("Helvetica-Bold", 8)
    c.drawString(x + pad, (y - h) + 5, "Total")
    c.drawRightString(
        x + w - pad, (y - h) + 5, money_clp(order_header.get("total_venta", 0))
    )


def render_orders_pdf(orders: List[dict], out: OutputConfig, pdf_path: str):
    page_w, page_h = A4
    c = canvas.Canvas(pdf_path, pagesize=A4)

    # layout: 2 columnas
    margin = 10 * mm
    gap = 8 * mm
    col_w = (page_w - 2 * margin - gap) / 2
    block_h = 78 * mm  # altura estándar por pedido (ajusta a gusto)
    v_gap = 6 * mm

    x_left = margin
    x_right = margin + col_w + gap
    y_top = page_h - margin

    cursor_y = y_top
    col = 0  # 0: left, 1: right
    blocks_in_row = 0

    for od in orders:
        x = x_left if col == 0 else x_right
        y = cursor_y

        draw_order_block(
            c=c,
            x=x,
            y=y,
            w=col_w,
            h=block_h,
            out=out,
            order_header=od["header"],
            items=od["items"],
        )

        # alternar columna
        if col == 0:
            col = 1
        else:
            col = 0
            # bajamos a la siguiente fila de bloques
            cursor_y -= block_h + v_gap

        # si no cabe otra fila, nueva página
        if cursor_y - block_h < margin:
            c.showPage()
            cursor_y = y_top
            col = 0

    c.save()
