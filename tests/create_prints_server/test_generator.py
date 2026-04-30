from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

import create_prints_server.app.generator as generator
from create_prints_server.infra.documents_provider import DocumentQuery


def _build_orders_frame(factura_despacho: bool = False) -> pd.DataFrame:
    """Construye una tabla mínima compatible con `build_orders_structure()`.

    Args:
        factura_despacho: Flag comercial heredado desde clientes.

    Returns:
        pd.DataFrame: DataFrame de detalle de una venta.
    """

    return pd.DataFrame(
        [
            {
                "venta_id": "101",
                "fecha": pd.Timestamp("2026-02-18"),
                "nombre": "Cliente Uno",
                "rut": "11.111.111-1",
                "direccion": "Direccion Cliente 123",
                "destinatario": "Destinatario Uno",
                "direccion_destinatario": "Direccion Destinatario 456",
                "factura_despacho": factura_despacho,
                "producto": "Palta Hass",
                "calibre": "18",
                "kg": 100.0,
                "precio_unit": 1500,
                "precio_total": 150000,
            }
        ]
    )


@dataclass
class _StubProvider:
    """Provider doble para tests de generación.

    Args:
        frame: DataFrame que se devolverá en cada consulta.
        queries: Historial de queries recibidas.
    """

    frame: pd.DataFrame
    queries: list[DocumentQuery] = field(default_factory=list)

    def load_orders_frame(self, query: DocumentQuery) -> pd.DataFrame:
        """Registra la query y devuelve una copia del frame de prueba.

        Args:
            query: Query solicitada por el generador.

        Returns:
            pd.DataFrame: Frame de prueba.
        """

        self.queries.append(query)
        return self.frame.copy(deep=True)


def test_generate_pdfs_shipping_list_uses_provider_and_creates_pdf(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verifica generación de lista de despacho usando el provider abstracto.

    Args:
        monkeypatch: Fixture de pytest para stubs de entorno.
        tmp_path: Carpeta temporal para artefactos.
    """

    provider = _StubProvider(_build_orders_frame())
    monkeypatch.setattr(generator, "build_documents_provider", lambda: provider)
    monkeypatch.setenv("PDF_ORDERS_PATH", str(tmp_path / "shipping_list.pdf"))
    monkeypatch.setenv("PDF_GUIDES_PATH", str(tmp_path / "guides.pdf"))

    artifacts = generator.generate_pdfs(
        what="shipping_list",
        day=date(2026, 2, 18),
    )

    assert artifacts.shipping_list_path is not None
    assert artifacts.guides_path is None
    assert Path(artifacts.shipping_list_path).exists()
    assert provider.queries[0].allowed_types == ["DESPACHO"]


def test_generate_pdfs_egreso_uses_venta_id_and_creates_guide(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verifica generación de guía de egreso usando la nueva frontera.

    Args:
        monkeypatch: Fixture de pytest para stubs de entorno.
        tmp_path: Carpeta temporal para artefactos.
    """

    provider = _StubProvider(_build_orders_frame())
    monkeypatch.setattr(generator, "build_documents_provider", lambda: provider)
    monkeypatch.setenv("PDF_ORDERS_PATH", str(tmp_path / "shipping_list.pdf"))
    monkeypatch.setenv("PDF_GUIDES_PATH", str(tmp_path / "guides.pdf"))

    artifacts = generator.generate_pdfs(
        what="egreso",
        day=date(2026, 2, 18),
        venta_id="101",
    )

    assert artifacts.shipping_list_path is None
    assert artifacts.guides_path is not None
    assert Path(artifacts.guides_path).exists()
    assert Path(artifacts.guides_path).name == "guides_egreso_20260218.pdf"
    assert provider.queries[0].allowed_types == ["EGRESO"]
    assert provider.queries[0].venta_id == "101"


def test_generate_pdfs_guides_keeps_orders_with_factura_despacho_true(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verifica que las guías ya no se filtren por `factura_despacho`.

    Args:
        monkeypatch: Fixture de pytest para stubs de entorno.
        tmp_path: Carpeta temporal para artefactos.
    """

    provider = _StubProvider(_build_orders_frame(factura_despacho=True))
    monkeypatch.setattr(generator, "build_documents_provider", lambda: provider)
    monkeypatch.setenv("PDF_ORDERS_PATH", str(tmp_path / "shipping_list.pdf"))
    monkeypatch.setenv("PDF_GUIDES_PATH", str(tmp_path / "guides.pdf"))

    artifacts = generator.generate_pdfs(
        what="guides",
        day=date(2026, 2, 18),
    )

    assert artifacts.shipping_list_path is None
    assert artifacts.guides_path is not None
    assert Path(artifacts.guides_path).exists()
    assert artifacts.orders_count == 1
    assert provider.queries[0].allowed_types == ["DESPACHO"]
    assert provider.queries[0].venta_id is None


def test_generate_pdfs_raises_when_provider_returns_no_orders(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verifica que se mantenga el contrato de error sin ventas.

    Args:
        monkeypatch: Fixture de pytest para stubs de entorno.
        tmp_path: Carpeta temporal para artefactos.
    """

    provider = _StubProvider(pd.DataFrame())
    monkeypatch.setattr(generator, "build_documents_provider", lambda: provider)
    monkeypatch.setenv("PDF_ORDERS_PATH", str(tmp_path / "shipping_list.pdf"))
    monkeypatch.setenv("PDF_GUIDES_PATH", str(tmp_path / "guides.pdf"))

    with pytest.raises(generator.NoOrdersForDateError):
        generator.generate_pdfs(
            what="shipping_list",
            day=date(2026, 2, 18),
        )