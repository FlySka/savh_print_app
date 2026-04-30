from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

import create_prints_server.render.guides_pdf as guides_pdf


def _build_guide(index: int) -> dict:
    """Construye una guía mínima para pruebas de layout.

    Args:
        index: Índice para distinguir el cliente de prueba.

    Returns:
        dict: Estructura compatible con `render_guides_pdf`.
    """

    return {
        "header": {
            "cliente_nombre": f"Cliente {index}",
            "fecha_str": "22-04-26",
            "direccion": "Direccion de prueba 123",
            "total_venta": 10000,
        },
        "items": pd.DataFrame(
            [
                {
                    "producto": "Palta",
                    "kg": 10,
                    "precio_unit": 1000,
                }
            ]
        ),
    }


def test_render_guides_pdf_leaves_print_safe_bottom_margin(
    tmp_path: Path,
) -> None:
    """Verifica que la tercera guía deje margen inferior seguro para impresión.

    Args:
        tmp_path: Carpeta temporal para el PDF de prueba.
    """

    captured_blocks: list[dict] = []
    original_draw = guides_pdf.draw_guide_block

    def fake_draw_guide_block(**kwargs) -> None:
        captured_blocks.append(kwargs)

    guides_pdf.draw_guide_block = fake_draw_guide_block
    try:
        guides_pdf.render_guides_pdf(
            guides=[_build_guide(1), _build_guide(2), _build_guide(3)],
            out=SimpleNamespace(contact="", logo_path=None, max_items=5),
            pdf_path=str(tmp_path / "guides.pdf"),
        )
    finally:
        guides_pdf.draw_guide_block = original_draw

    assert len(captured_blocks) == 3

    _page_w, _page_h = A4
    bottom_margin_mm = (captured_blocks[-1]["y"] - captured_blocks[-1]["h"]) / mm
    assert bottom_margin_mm == pytest.approx(40.0)


def test_receipt_stub_keeps_amount_between_checkboxes_and_signature() -> None:
    """Verifica que el talón no vuelva a solapar monto con los checkboxes.

    El layout nuevo compacta el talón, pero debe mantener una banda clara para
    `MONTO` entre el grupo de checkboxes y la firma de recepción.
    """

    buffer = BytesIO()
    pdf_canvas = canvas.Canvas(buffer, pagesize=A4)

    text_positions: list[tuple[str, float, float]] = []
    rects: list[tuple[float, float, float, float]] = []

    original_draw_string = pdf_canvas.drawString
    original_draw_right_string = pdf_canvas.drawRightString
    original_rect = pdf_canvas.rect

    def capture_draw_string(x: float, y: float, text: str, *args, **kwargs) -> None:
        text_positions.append((str(text), x, y))
        original_draw_string(x, y, text, *args, **kwargs)

    def capture_draw_right_string(
        x: float,
        y: float,
        text: str,
        *args,
        **kwargs,
    ) -> None:
        text_positions.append((str(text), x, y))
        original_draw_right_string(x, y, text, *args, **kwargs)

    def capture_rect(
        x: float,
        y: float,
        w: float,
        h: float,
        *args,
        **kwargs,
    ) -> None:
        rects.append((x, y, w, h))
        original_rect(x, y, w, h, *args, **kwargs)

    pdf_canvas.drawString = capture_draw_string  # type: ignore[method-assign]
    pdf_canvas.drawRightString = capture_draw_right_string  # type: ignore[method-assign]
    pdf_canvas.rect = capture_rect  # type: ignore[method-assign]

    block_h = (A4[1] - 12 * mm - 40 * mm - 2 * (10 * mm)) / 3
    guides_pdf._draw_receipt_stub(
        c=pdf_canvas,
        x=150 * mm,
        y=A4[1] - 12 * mm,
        w=58 * mm,
        h=block_h,
        order_header={"cliente_nombre": "la maestria", "fecha_str": "24-04-26"},
        items=pd.DataFrame([{"producto": "palta", "kg": 15, "precio_unit": 3300}]),
        total=49500,
    )

    monto_y = next(y for text, _x, y in text_positions if text == "MONTO")
    signature_y = next(y for text, _x, y in text_positions if text == "RECIBE CONFORME")
    labels = {text for text, _x, _y in text_positions}
    checkbox_bottoms = [
        y for _x, y, w, h in rects if w == pytest.approx(5.3) and h == pytest.approx(5.3)
    ]

    assert {"PAGO", "ABONO", "DEBE"}.issubset(labels)
    assert checkbox_bottoms
    gap_to_checkboxes = min(checkbox_bottoms) - monto_y
    gap_to_signature = monto_y - signature_y

    assert gap_to_checkboxes >= 12
    assert monto_y >= signature_y + 14
    assert gap_to_checkboxes < gap_to_signature
