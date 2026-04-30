from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from typing import Literal, Protocol, runtime_checkable

import pandas as pd
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.engine import Engine

from create_prints_server.domain.orders import build_daily_orders
from create_prints_server.infra.google_sheets import sheet_to_df


DocumentSourceType = Literal["sheets", "postgres"]


@dataclass(frozen=True)
class DocumentQuery:
    """Filtro de lectura para documentos comerciales.

    Args:
        day: Fecha objetivo a consultar.
        allowed_types: Tipos de venta permitidos. Si es None, no filtra.
        venta_id: Si se informa, limita la consulta a una venta puntual.
    """

    day: date
    allowed_types: list[str] | None = None
    venta_id: str | None = None


@runtime_checkable
class DocumentsProvider(Protocol):
    """Contrato para fuentes de datos de documentos comerciales.

    Cada implementación debe devolver una tabla normalizada compatible con el
    pipeline actual de construcción de órdenes y render de PDFs.
    """

    def load_orders_frame(self, query: DocumentQuery) -> pd.DataFrame:
        """Obtiene el detalle normalizado de ventas para la consulta dada.

        Args:
            query: Filtros de negocio para la consulta.

        Returns:
            pd.DataFrame: Tabla a nivel de ítem compatible con el render actual.
        """


@dataclass(frozen=True)
class GoogleSheetsConfig:
    """Configuración de Google Sheets necesaria para documentos.

    Args:
        spreadsheet_id: ID del spreadsheet.
        clientes_sheet: Nombre de la hoja de clientes.
        destinatarios_sheet: Nombre de la hoja de destinatarios.
        ventas_sheet: Nombre de la hoja de ventas.
        detalle_sheet: Nombre de la hoja de detalle de ventas.
        clientes_range: Rango A1 de clientes.
        destinatarios_range: Rango A1 de destinatarios.
        ventas_range: Rango A1 de ventas.
        detalle_range: Rango A1 de detalle.
        credentials_path: Ruta al JSON del service account.
    """

    spreadsheet_id: str
    clientes_sheet: str
    destinatarios_sheet: str
    ventas_sheet: str
    detalle_sheet: str
    clientes_range: str
    destinatarios_range: str
    ventas_range: str
    detalle_range: str
    credentials_path: str


@dataclass(frozen=True)
class BusinessDatabaseConfig:
    """Configuración de la base de negocio para documentos.

    Args:
        database_url: URL SQLAlchemy de la base comercial.
        schema: Schema donde viven las tablas comerciales.
        dispatch_sale_type: Etiqueta del tipo de venta para despachos.
        egreso_sale_type: Etiqueta del tipo de venta para egresos.
    """

    database_url: str
    schema: str = "core"
    dispatch_sale_type: str = "DESPACHO"
    egreso_sale_type: str = "EGRESO"


class SheetsDocumentsProvider:
    """Proveedor de documentos comerciales basado en Google Sheets."""

    def __init__(self, config: GoogleSheetsConfig) -> None:
        """Inicializa el proveedor de Google Sheets.

        Args:
            config: Configuración de acceso a Sheets.
        """

        self._config = config

    def load_orders_frame(self, query: DocumentQuery) -> pd.DataFrame:
        """Carga el detalle de ventas desde Google Sheets.

        Args:
            query: Filtros de lectura para la consulta.

        Returns:
            pd.DataFrame: Tabla detallada compatible con el flujo actual.
        """

        service = self._build_service()
        df_clientes = sheet_to_df(
            service,
            self._config.spreadsheet_id,
            self._config.clientes_sheet,
            self._config.clientes_range,
        )
        df_destinatarios = sheet_to_df(
            service,
            self._config.spreadsheet_id,
            self._config.destinatarios_sheet,
            self._config.destinatarios_range,
        )
        df_ventas = sheet_to_df(
            service,
            self._config.spreadsheet_id,
            self._config.ventas_sheet,
            self._config.ventas_range,
        )
        df_det = sheet_to_df(
            service,
            self._config.spreadsheet_id,
            self._config.detalle_sheet,
            self._config.detalle_range,
        )

        if df_clientes.empty or df_ventas.empty or df_det.empty:
            raise RuntimeError(
                "Alguna tabla esta vacia o el rango no trae datos "
                "(CLIENTES/VENTAS/DETALLE_VENTAS)."
            )

        target_day = datetime(query.day.year, query.day.month, query.day.day)
        return build_daily_orders(
            df_clientes,
            df_destinatarios,
            df_ventas,
            df_det,
            target_day,
            allowed_types=query.allowed_types,
            venta_id=query.venta_id,
        )

    def _build_service(self):
        """Construye el cliente readonly de Google Sheets.

        Returns:
            Resource: Cliente de la API de Sheets.
        """

        scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
        creds = Credentials.from_service_account_file(
            self._config.credentials_path,
            scopes=scopes,
        )
        return build("sheets", "v4", credentials=creds)


class PostgresDocumentsProvider:
    """Proveedor de documentos comerciales basado en PostgreSQL."""

    def __init__(
        self,
        config: BusinessDatabaseConfig,
        engine: Engine | None = None,
    ) -> None:
        """Inicializa el proveedor PostgreSQL.

        Args:
            config: Configuración de acceso a la base comercial.
            engine: Engine opcional para testing o inyección manual.
        """

        self._config = config
        self._schema = _validate_identifier(config.schema, env_name="BUSINESS_DB_SCHEMA")
        self._engine = engine or _get_business_engine(config.database_url)

    def load_orders_frame(self, query: DocumentQuery) -> pd.DataFrame:
        """Carga el detalle de ventas desde PostgreSQL.

        Args:
            query: Filtros de lectura para la consulta.

        Returns:
            pd.DataFrame: Tabla detallada compatible con el flujo actual.
        """

        statement, params = build_postgres_orders_query(self._schema, self._config, query)
        with self._engine.connect() as connection:
            frame = pd.read_sql_query(statement, connection, params=params)
        return _normalize_postgres_orders_frame(frame)


def get_document_source_type() -> DocumentSourceType:
    """Retorna el tipo de fuente configurado globalmente.

    Returns:
        DocumentSourceType: Fuente configurada en entorno.

    Raises:
        ValueError: Si la fuente no pertenece al conjunto soportado.
    """

    source = os.getenv("DOCUMENTS_DATA_SOURCE", "sheets").strip().lower()
    if source not in {"sheets", "postgres"}:
        raise ValueError(
            "DOCUMENTS_DATA_SOURCE debe ser 'sheets' o 'postgres'."
        )
    return source  # type: ignore[return-value]


def build_documents_provider() -> DocumentsProvider:
    """Construye el proveedor de documentos configurado por entorno.

    Returns:
        DocumentsProvider: Implementación de lectura de documentos.

    Raises:
        KeyError: Si faltan variables requeridas para el proveedor activo.
        NotImplementedError: Si la fuente configurada aún no tiene implementación.
    """

    source = get_document_source_type()
    if source == "sheets":
        return SheetsDocumentsProvider(_load_google_sheets_config())
    return PostgresDocumentsProvider(_load_business_database_config())


def _load_google_sheets_config() -> GoogleSheetsConfig:
    """Carga la configuración de Google Sheets desde variables de entorno.

    Returns:
        GoogleSheetsConfig: Configuración validada para el proveedor.
    """

    return GoogleSheetsConfig(
        spreadsheet_id=_required_env("SHEETS_ID"),
        clientes_sheet=_required_env("CLIENTES_SHEET"),
        destinatarios_sheet=_required_env("DESTINATARIOS_SHEET"),
        ventas_sheet=_required_env("VENTAS_SHEET"),
        detalle_sheet=_required_env("DETALLE_SHEET"),
        clientes_range=_required_env("CLIENTES_RANGE"),
        destinatarios_range=_required_env("DESTINATARIOS_RANGE"),
        ventas_range=_required_env("VENTAS_RANGE"),
        detalle_range=_required_env("DETALLE_RANGE"),
        credentials_path=_required_env("GOOGLE_APPLICATION_CREDENTIALS"),
    )


def _load_business_database_config() -> BusinessDatabaseConfig:
    """Carga la configuración de la base de negocio desde entorno.

    Returns:
        BusinessDatabaseConfig: Configuración validada del proveedor PostgreSQL.
    """

    return BusinessDatabaseConfig(
        database_url=_required_env("BUSINESS_DATABASE_URL"),
        schema=os.getenv("BUSINESS_DB_SCHEMA", "core"),
        dispatch_sale_type=os.getenv("DOCUMENTS_DISPATCH_SALE_TYPE", "DESPACHO"),
        egreso_sale_type=os.getenv("DOCUMENTS_EGRESO_SALE_TYPE", "EGRESO"),
    )


def build_postgres_orders_query(
    schema: str,
    config: BusinessDatabaseConfig,
    query: DocumentQuery,
):
    """Construye el SQL y parámetros para leer ventas desde PostgreSQL.

    Args:
        schema: Schema validado con las tablas comerciales.
        config: Configuración del proveedor PostgreSQL.
        query: Filtros de negocio de la consulta.

    Returns:
        tuple: Statement SQLAlchemy y parámetros asociados.
    """

    conditions = [
        "sales.deleted_at IS NULL",
        "sale_items.deleted_at IS NULL",
        "sales.fecha = :day",
    ]
    params: dict[str, object] = {"day": query.day}

    if query.venta_id is not None:
        conditions.append("CAST(sales.id AS TEXT) = :venta_id")
        params["venta_id"] = str(query.venta_id)

    translated_types = _translate_sale_types(query.allowed_types, config)
    if translated_types:
        conditions.append("UPPER(TRIM(COALESCE(sale_types.tipo, ''))) IN :allowed_types")
        params["allowed_types"] = translated_types

    statement = text(
        f"""
        SELECT
            CAST(sales.id AS TEXT) AS venta_id,
            sales.fecha AS fecha,
            sale_types.tipo AS tipo,
            customer_party.nombre AS nombre,
            customer_party.rut AS rut,
            customer_party.direccion AS direccion,
            recipient_party.nombre AS destinatario,
            recipient_party.direccion AS direccion_destinatario,
            customer.factura_despacho AS factura_despacho,
            products.nombre AS producto,
            COALESCE(calibers.calibre, '') AS calibre,
            sale_items.kg AS kg,
            sale_items.precio_unit AS precio_unit,
            sale_items.precio_total AS precio_total
        FROM {schema}.sales AS sales
        JOIN {schema}.sale_items AS sale_items
            ON sale_items.venta_id = sales.id
        LEFT JOIN {schema}.dim_sale_types AS sale_types
            ON sale_types.id = sales.tipo_id
        LEFT JOIN {schema}.parties_customer AS customer
            ON customer.tercero_id = sales.cliente_id
        LEFT JOIN {schema}.parties AS customer_party
            ON customer_party.id = sales.cliente_id
        LEFT JOIN {schema}.parties_recipient AS recipient
            ON recipient.tercero_id = sales.destinatario_id
        LEFT JOIN {schema}.parties AS recipient_party
            ON recipient_party.id = sales.destinatario_id
        LEFT JOIN {schema}.products AS products
            ON products.id = sale_items.producto_id
        LEFT JOIN {schema}.dim_calibers AS calibers
            ON calibers.id = sale_items.calibre_id
        WHERE {' AND '.join(conditions)}
        ORDER BY customer_party.nombre ASC NULLS LAST,
                 recipient_party.nombre ASC NULLS LAST,
                 sales.id ASC,
                 sale_items.id ASC
        """
    )

    if translated_types:
        statement = statement.bindparams(bindparam("allowed_types", expanding=True))

    return statement, params


def _normalize_postgres_orders_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Normaliza el resultado PostgreSQL al contrato del pipeline actual.

    Args:
        frame: DataFrame leído desde la base comercial.

    Returns:
        pd.DataFrame: DataFrame listo para `build_orders_structure()`.
    """

    if frame.empty:
        return frame

    frame = frame.copy()
    frame["venta_id"] = frame["venta_id"].astype(str)

    for column in ["kg", "precio_unit", "precio_total"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
        if frame[column].isna().any():
            raise RuntimeError(
                f"La columna requerida '{column}' trae valores no numéricos desde PostgreSQL."
            )

    frame["kg"] = frame["kg"].astype(float)
    frame["precio_unit"] = frame["precio_unit"].round().astype(int)
    frame["precio_total"] = frame["precio_total"].round().astype(int)
    return frame


@lru_cache(maxsize=None)
def _get_business_engine(database_url: str) -> Engine:
    """Construye y cachea el engine de la base comercial.

    Args:
        database_url: URL SQLAlchemy de la base de negocio.

    Returns:
        Engine: Engine reutilizable para consultas readonly.
    """

    return create_engine(database_url, pool_pre_ping=True)


def _translate_sale_types(
    allowed_types: list[str] | None,
    config: BusinessDatabaseConfig,
) -> list[str]:
    """Traduce tipos lógicos al etiquetado real de la base comercial.

    Args:
        allowed_types: Tipos solicitados por el flujo de negocio.
        config: Configuración del proveedor PostgreSQL.

    Returns:
        list[str]: Tipos normalizados para comparar contra `dim_sale_types.tipo`.
    """

    if not allowed_types:
        return []

    aliases = {
        "DESPACHO": config.dispatch_sale_type,
        "EGRESO": config.egreso_sale_type,
    }
    translated: list[str] = []
    for sale_type in allowed_types:
        key = str(sale_type).strip().upper()
        translated.append(str(aliases.get(key, sale_type)).strip().upper())
    return translated


def _validate_identifier(value: str, *, env_name: str) -> str:
    """Valida identificadores SQL inyectados por configuración.

    Args:
        value: Valor a validar.
        env_name: Nombre de la variable de entorno asociada.

    Returns:
        str: Identificador validado.

    Raises:
        ValueError: Si el valor no es un identificador SQL simple.
    """

    candidate = value.strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", candidate):
        raise ValueError(
            f"{env_name} debe ser un identificador SQL simple y seguro."
        )
    return candidate


def _required_env(name: str) -> str:
    """Obtiene una variable de entorno obligatoria.

    Args:
        name: Nombre de la variable.

    Returns:
        str: Valor no vacío de la variable.

    Raises:
        KeyError: Si la variable no existe o está vacía.
    """

    value = os.getenv(name)
    if value is None or value == "":
        raise KeyError(f"Falta variable de entorno requerida: {name}")
    return value