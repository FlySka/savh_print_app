from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd
import pytest

import create_prints_server.app.api as create_api
from create_prints_server.infra.documents_provider import DocumentQuery


def _build_egreso_frame() -> pd.DataFrame:
    """Construye una tabla mínima para listar egresos.

    Returns:
        pd.DataFrame: Frame de detalle con dos líneas para la misma venta.
    """

    return pd.DataFrame(
        [
            {
                "venta_id": "101",
                "nombre": "Cliente Uno",
                "destinatario": "Destinatario Uno",
                "precio_total": 100000,
            },
            {
                "venta_id": "101",
                "nombre": "Cliente Uno",
                "destinatario": "Destinatario Uno",
                "precio_total": 50000,
            },
        ]
    )


@dataclass
class _StubProvider:
    """Provider doble para tests de API.

    Args:
        frame: DataFrame que se devolverá en cada consulta.
        queries: Historial de queries recibidas.
    """

    frame: pd.DataFrame
    queries: list[DocumentQuery] = field(default_factory=list)

    def load_orders_frame(self, query: DocumentQuery) -> pd.DataFrame:
        """Registra la query y devuelve una copia del frame de prueba.

        Args:
            query: Query solicitada por la API.

        Returns:
            pd.DataFrame: Frame de prueba.
        """

        self.queries.append(query)
        return self.frame.copy(deep=True)


def test_list_egresos_uses_provider_and_builds_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifica que `/api/egresos` use el provider abstracto.

    Args:
        monkeypatch: Fixture de pytest para stubs de dependencias.
    """

    provider = _StubProvider(_build_egreso_frame())
    monkeypatch.setattr(create_api, "build_documents_provider", lambda: provider)

    result = create_api.list_egresos(day=date(2026, 2, 18))

    assert len(result) == 1
    assert result[0].venta_id == "101"
    assert result[0].cliente == "Cliente Uno"
    assert result[0].destinatario == "Destinatario Uno"
    assert result[0].total == 150000
    assert result[0].total_fmt
    assert provider.queries[0].allowed_types == ["EGRESO"]


def test_list_egresos_returns_empty_list_when_no_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifica que `/api/egresos` mantenga el caso vacío.

    Args:
        monkeypatch: Fixture de pytest para stubs de dependencias.
    """

    provider = _StubProvider(pd.DataFrame())
    monkeypatch.setattr(create_api, "build_documents_provider", lambda: provider)

    result = create_api.list_egresos(day=date(2026, 2, 18))

    assert result == []