from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd


@dataclass(frozen=True)
class GuidesOutputConfig:
    """Configuración de salida para el PDF de guías de despacho.

    Args:
        pdf_path (str): Ruta del PDF de salida.
        title (str): Título superior (ej. nombre de la empresa).
        subtitle (str): Subtítulo (ej. bodega/sucursal).
        contact (str): Texto de contacto (ej. "Contacto: +56 9 ...").
        logo_path (Optional[str]): Ruta local al logo (png/jpg). Si es None, no se dibuja.
        max_items (int): Cantidad máxima de filas de ítems en la guía.

    """
    pdf_path: str
    title: str
    subtitle: str
    contact: str
    logo_path: Optional[str] = None
    max_items: int = 8


def should_generate_guide(factura_despacho: Any) -> bool:
    """Determina si corresponde generar guía según el campo `factura_despacho`.

    Regla:
        - Si `factura_despacho` es TRUE => NO se genera guía.
        - Si es FALSE (o vacío/desconocido) => SÍ se genera guía.

    Args:
        factura_despacho (Any): Valor crudo (bool/str/número) desde la tabla CLIENTES.

    Returns:
        bool: True si hay que generar guía; False en caso contrario.

    """
    parsed = _parse_bool(factura_despacho)
    return parsed is not True


def filter_orders_requiring_guide(
    orders: Iterable[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Filtra órdenes dejando solo las que requieren guía.

    Args:
        orders (Iterable[Dict[str, Any]]): Órdenes con 'header' e 'items'.

    Returns:
        List[Dict[str, Any]]: Órdenes que sí requieren guía.
    """
    out: List[Dict[str, Any]] = []

    for od in orders:
        header = od.get("header", {}) or {}

        flag = (
            header.get("factura_despacho")
            if "factura_despacho" in header
            else header.get("cliente_factura_despacho", header.get("FACTURA_DESPACHO"))
        )

        if should_generate_guide(flag):
            out.append(od)

    return out


def split_order_date_components(order_header: Dict[str, Any]) -> Tuple[str, str, str]:
    """Extrae (día, mes, año) como strings desde el header de la orden.

    Intenta usar:
        - order_header["fecha"] (date/datetime/pandas)
        - order_header["fecha_str"] (string parseable)

    Args:
        order_header (Dict[str, Any]): Header de la orden.

    Returns:
        Tuple[str, str, str]: (DD, MM, YYYY) como strings; vacíos si no se puede parsear.

    """
    d = _parse_date(order_header.get("fecha", None))
    if d is None:
        d = _parse_date(order_header.get("fecha_str", None))

    if d is None:
        return "", "", ""

    return f"{d.day:02d}", f"{d.month:02d}", f"{d.year:04d}"


def compute_order_total(order_header: Dict[str, Any], items: pd.DataFrame) -> float:
    """Calcula el total de la guía desde header o desde ítems.

    Prioridad:
        1) header["total_venta"]
        2) sum(items["precio_total"])
        3) sum(items["kg"] * items["precio_unit"])

    Args:
        order_header (Dict[str, Any]): Header de la orden.
        items (pd.DataFrame): DataFrame de ítems.

    Returns:
        float: Total calculado (0.0 si no hay datos).

    """
    total_hdr = order_header.get("total_venta", None)
    if total_hdr is not None and _is_number(total_hdr):
        return float(total_hdr)

    if isinstance(items, pd.DataFrame) and not items.empty:
        if "precio_total" in items.columns:
            s = pd.to_numeric(items["precio_total"], errors="coerce").fillna(0).sum()
            return float(s)

        if "kg" in items.columns and "precio_unit" in items.columns:
            kg = pd.to_numeric(items["kg"], errors="coerce").fillna(0)
            pu = pd.to_numeric(items["precio_unit"], errors="coerce").fillna(0)
            return float((kg * pu).sum())

    return 0.0


def normalize_guide_items(items: pd.DataFrame, max_items: int) -> pd.DataFrame:
    """Normaliza el DF de ítems para guías: Producto | Kilos | Precio Unitario.

    Args:
        items (pd.DataFrame): Ítems originales (posiblemente con más columnas).
        max_items (int): Máximo de filas a mantener.

    Returns:
        pd.DataFrame: Ítems recortados y con columnas esperadas (si existen).

    """
    if not isinstance(items, pd.DataFrame) or items.empty:
        return pd.DataFrame(columns=["producto", "kg", "precio_unit"])

    cols = []
    for c in ["producto", "kg", "precio_unit"]:
        if c in items.columns:
            cols.append(c)

    base = items[cols].copy() if cols else items.copy()
    if "producto" not in base.columns:
        base["producto"] = ""
    if "kg" not in base.columns:
        base["kg"] = None
    if "precio_unit" not in base.columns:
        base["precio_unit"] = None

    return base[["producto", "kg", "precio_unit"]].head(int(max_items))


def _parse_bool(value: Any) -> Optional[bool]:
    """Parsea valores comunes a booleano.

    Args:
        value (Any): Entrada cruda.

    Returns:
        Optional[bool]: True/False si se reconoce; None si es desconocido.

    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not pd.isna(value):
        if float(value) == 1.0:
            return True
        if float(value) == 0.0:
            return False
        return None
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"true", "t", "1", "si", "sí", "yes", "y", "verdadero"}:
            return True
        if v in {"false", "f", "0", "no", "n", "falso", ""}:
            return False
    return None


def _parse_date(value: Any) -> Optional[date]:
    """Parsea un valor a date.

    Args:
        value (Any): date/datetime/Timestamp o string parseable.

    Returns:
        Optional[date]: Fecha si se puede; None si no.

    """
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, pd.Timestamp):
        return value
    try:
        ts = pd.to_datetime(value, errors="coerce", dayfirst=True)
    except Exception:
        return None
    if pd.isna(ts):
        return None
    return ts.date()


def _is_number(value: Any) -> bool:
    """Indica si un valor es numérico (incluye strings numéricos).

    Args:
        value (Any): Valor.

    Returns:
        bool: True si es numérico; False si no.

    """
    try:
        float(value)
        return True
    except Exception:
        return False
