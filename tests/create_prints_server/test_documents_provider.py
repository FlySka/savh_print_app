from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

import create_prints_server.infra.documents_provider as documents_provider


def _set_sheets_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Carga variables mínimas para el provider de Google Sheets.

    Args:
        monkeypatch: Fixture de pytest para modificar entorno.
    """

    monkeypatch.delenv("DOCUMENTS_DATA_SOURCE", raising=False)
    monkeypatch.setenv("SHEETS_ID", "sheet-id")
    monkeypatch.setenv("CLIENTES_SHEET", "CLIENTES")
    monkeypatch.setenv("DESTINATARIOS_SHEET", "DESTINATARIOS")
    monkeypatch.setenv("VENTAS_SHEET", "VENTAS")
    monkeypatch.setenv("DETALLE_SHEET", "DETALLE_VENTAS")
    monkeypatch.setenv("CLIENTES_RANGE", "A1:K")
    monkeypatch.setenv("DESTINATARIOS_RANGE", "A1:H")
    monkeypatch.setenv("VENTAS_RANGE", "A1:H")
    monkeypatch.setenv("DETALLE_RANGE", "A1:J")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/tmp/fake-google.json")


def _set_postgres_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Carga variables mínimas para el provider PostgreSQL.

    Args:
        monkeypatch: Fixture de pytest para modificar entorno.
    """

    monkeypatch.setenv("DOCUMENTS_DATA_SOURCE", "postgres")
    monkeypatch.setenv(
        "BUSINESS_DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@localhost:5432/savh_business",
    )
    monkeypatch.setenv("BUSINESS_DB_SCHEMA", "core")
    monkeypatch.setenv("DOCUMENTS_DISPATCH_SALE_TYPE", "DESPACHO")
    monkeypatch.setenv("DOCUMENTS_EGRESO_SALE_TYPE", "EGRESO")


def _build_sheet_frames() -> list[pd.DataFrame]:
    """Construye un set mínimo de dataframes con shape de Sheets.

    Returns:
        list[pd.DataFrame]: DataFrames de clientes, destinatarios, ventas y detalle.
    """

    clientes = pd.DataFrame(
        [
            {
                "nombre": "Cliente Uno",
                "rut": "11.111.111-1",
                "direccion": "Direccion Cliente 123",
                "factura_despacho": False,
            }
        ]
    )
    destinatarios = pd.DataFrame(
        [{"nombre": "Destinatario Uno", "direccion": "Direccion Destinatario 456"}]
    )
    ventas = pd.DataFrame(
        [
            {
                "id": "101",
                "fecha": "18/02/2026",
                "cliente": "Cliente Uno",
                "destinatario": "Destinatario Uno",
                "tipo": "DESPACHO",
            }
        ]
    )
    detalle = pd.DataFrame(
        [
            {
                "venta_id": "101",
                "producto": "Palta Hass",
                "calibre": "18",
                "kg": "100",
                "precio_unit": "1500",
                "precio_total": "150000",
            }
        ]
    )
    return [clientes, destinatarios, ventas, detalle]


def test_build_documents_provider_defaults_to_sheets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifica que la factory use Sheets cuando no se configura otra fuente.

    Args:
        monkeypatch: Fixture de pytest para modificar entorno.
    """

    _set_sheets_env(monkeypatch)

    provider = documents_provider.build_documents_provider()

    assert isinstance(provider, documents_provider.SheetsDocumentsProvider)


def test_build_documents_provider_uses_postgres_when_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifica que la factory construya el provider PostgreSQL.

    Args:
        monkeypatch: Fixture de pytest para modificar entorno.
    """

    _set_postgres_env(monkeypatch)
    fake_engine = object()
    monkeypatch.setattr(documents_provider, "_get_business_engine", lambda _url: fake_engine)

    provider = documents_provider.build_documents_provider()

    assert isinstance(provider, documents_provider.PostgresDocumentsProvider)
    assert provider._engine is fake_engine


def test_sheets_provider_load_orders_frame_returns_expected_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Valida que el provider de Sheets preserve el contrato del pipeline.

    Args:
        monkeypatch: Fixture de pytest para modificar dependencias.
    """

    frames = iter(_build_sheet_frames())
    config = documents_provider.GoogleSheetsConfig(
        spreadsheet_id="sheet-id",
        clientes_sheet="CLIENTES",
        destinatarios_sheet="DESTINATARIOS",
        ventas_sheet="VENTAS",
        detalle_sheet="DETALLE_VENTAS",
        clientes_range="A1:K",
        destinatarios_range="A1:H",
        ventas_range="A1:H",
        detalle_range="A1:J",
        credentials_path="/tmp/fake-google.json",
    )
    provider = documents_provider.SheetsDocumentsProvider(config)

    monkeypatch.setattr(provider, "_build_service", lambda: object())
    monkeypatch.setattr(
        documents_provider,
        "sheet_to_df",
        lambda *_args, **_kwargs: next(frames),
    )

    result = provider.load_orders_frame(
        documents_provider.DocumentQuery(
            day=date(2026, 2, 18),
            allowed_types=["DESPACHO"],
        )
    )

    assert list(result["venta_id"]) == ["101"]
    assert list(result["producto"]) == ["Palta Hass"]
    assert list(result["destinatario"]) == ["Destinatario Uno"]


def test_build_postgres_orders_query_translates_sale_types() -> None:
    """Verifica el armado del SQL y la traducción de tipos de venta."""

    config = documents_provider.BusinessDatabaseConfig(
        database_url="postgresql+psycopg://postgres:postgres@localhost:5432/savh_business",
        schema="core",
        dispatch_sale_type="SALIDA",
        egreso_sale_type="RETIRO",
    )

    statement, params = documents_provider.build_postgres_orders_query(
        "core",
        config,
        documents_provider.DocumentQuery(
            day=date(2026, 2, 18),
            allowed_types=["DESPACHO"],
            venta_id="900",
        ),
    )

    assert "FROM core.sales AS sales" in statement.text
    assert params["venta_id"] == "900"
    assert params["allowed_types"] == ["SALIDA"]


def test_normalize_postgres_orders_frame_casts_expected_types() -> None:
    """Verifica normalización de tipos para datos leídos desde PostgreSQL."""

    frame = pd.DataFrame(
        [
            {
                "venta_id": 101,
                "kg": "100",
                "precio_unit": "1500",
                "precio_total": "150000",
            }
        ]
    )

    normalized = documents_provider._normalize_postgres_orders_frame(frame)

    assert normalized.loc[0, "venta_id"] == "101"
    assert normalized.loc[0, "kg"] == 100.0
    assert normalized.loc[0, "precio_unit"] == 1500
    assert normalized.loc[0, "precio_total"] == 150000


def test_normalize_postgres_orders_frame_rejects_non_numeric_values() -> None:
    """Verifica que la normalización falle ante datos inválidos."""

    frame = pd.DataFrame(
        [
            {
                "venta_id": 101,
                "kg": "100",
                "precio_unit": "oops",
                "precio_total": "150000",
            }
        ]
    )

    with pytest.raises(RuntimeError, match="precio_unit"):
        documents_provider._normalize_postgres_orders_frame(frame)