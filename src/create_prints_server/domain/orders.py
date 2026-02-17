import pandas as pd

from create_prints_server.domain.money import parse_cl_number


def build_daily_orders(
    df_clientes: pd.DataFrame,
    df_destinatarios: pd.DataFrame,
    df_ventas: pd.DataFrame,
    df_det: pd.DataFrame,
    day: pd.Timestamp,
) -> pd.DataFrame:
    """
    Retorna una tabla por ítem (detalle) ya unida con cabecera de venta y cliente.

    Args:
        df_clientes: tabla CLIENTES
        df_destinatarios: tabla DESTINATARIOS
        df_ventas: tabla VENTAS
        df_det: tabla DETALLE_VENTAS
        day: día a filtrar (pd.Timestamp normalizado)

    Returns:
        pd.DataFrame con detalle de ventas del día, unido con clientes y ventas.
    """
    # --- normalizaciones mínimas ---
    # fechas
    if "fecha" not in df_ventas.columns:
        raise KeyError("VENTAS debe tener columna 'fecha'")
    # Datos de Sheets vienen en formato dd/mm/YYYY; declaramos dayfirst explícito para
    # evitar que pandas asuma mes/día y emita FutureWarning.
    df_ventas["fecha"] = pd.to_datetime(
        df_ventas["fecha"], errors="coerce", dayfirst=True
    ).dt.normalize()

    # ids (para join estable)
    for col in ["id"]:
        if col in df_clientes.columns:
            df_clientes[col] = df_clientes[col].astype(str)
    for col in ["id", "cliente"]:
        if col in df_ventas.columns:
            df_ventas[col] = df_ventas[col].astype(str)
    for col in ["id", "cliente_id"]:
        if col in df_destinatarios.columns:
            df_destinatarios[col] = df_destinatarios[col].astype(str)
    for col in ["venta_id"]:
        if col in df_det.columns:
            df_det[col] = df_det[col].astype(str)

    # --- filtrar ventas del día ---
    ventas_dia = df_ventas[df_ventas["fecha"] == day].copy()

    if ventas_dia.empty:
        return pd.DataFrame()

    # --- join ventas + clientes ---
    # VENTAS.cliente -> CLIENTES.nombre
    if "cliente" not in ventas_dia.columns:
        raise KeyError("VENTAS debe tener columna 'cliente' (id del cliente)")

    ventas_cli = ventas_dia.merge(
        df_clientes,
        left_on="cliente",
        right_on="nombre",
        how="left",
        suffixes=("", "_cliente"),
    )

    # --- join con destinatarios ---
    # VENTAS.destinatario -> DESTINATARIOS.nombre
    if "destinatario" not in ventas_cli.columns:
        raise KeyError("VENTAS debe tener columna 'destinatario'")

    ventas_cli_des = ventas_cli.merge(
        df_destinatarios,
        left_on="destinatario",
        right_on="nombre",
        how="left",
        suffixes=("", "_destinatario"),
    )

    # --- join con detalle ---
    if "venta_id" not in df_det.columns:
        raise KeyError("DETALLE_VENTAS debe tener columna 'venta_id'")

    det_dia = df_det.merge(
        ventas_cli_des,
        left_on="venta_id",
        right_on="id",
        how="inner",
        suffixes=("", "_venta"),
    )

    # tipos numéricos
    for c in ["kg", "precio_unit", "precio_total"]:
        if c in det_dia.columns:
            det_dia[c] = parse_cl_number(det_dia[c])
    det_dia = det_dia.assign(
        kg=det_dia["kg"].astype(float),
        precio_unit=det_dia["precio_unit"].astype(int),
        precio_total=det_dia["precio_total"].astype(int),
    )

    # orden: por vendedor/cliente si quieres (ajusta)
    if "nombre" in det_dia.columns:
        det_dia = det_dia.sort_values(["nombre", "destinatario", "venta_id"])

    return det_dia


def build_orders_structure(det_dia: pd.DataFrame) -> list[dict]:
    """
    Construye la estructura de pedidos para el PDF.
    Retorna lista de dicts con 'header' y 'items' por pedido.
    """
    orders = []
    for venta_id, g in det_dia.groupby("venta_id", sort=False):
        # header de la venta (sale del primer registro)
        r0 = g.iloc[0]
        fecha_str = (
            pd.to_datetime(r0.get("fecha")).strftime("%d-%m-%y")
            if pd.notna(r0.get("fecha"))
            else ""
        )

        # nombre cliente: CLIENTES.nombre
        cliente_nombre = str(r0.get("nombre", "") or "")
        # destinatario: VENTAS.destinatario
        destinatario = str(r0.get("destinatario", "") or "")
        if destinatario:
            cliente_nombre = f"{destinatario} ({cliente_nombre})"

        # dirección: prioriza VENTAS.destinatario
        direccion = str(r0.get("direccion", "") or "")
        direccion_des = str(r0.get("direccion_destinatario", "") or "")
        if direccion_des != "nan" and direccion_des:
            direccion = direccion_des

        total_venta = (
            g["precio_total"].sum(skipna=True) if "precio_total" in g.columns else 0
        )

        factura_despacho = r0.get("factura_despacho", None)
        rut = str(r0.get("rut", "") or r0.get("rut_cliente", "") or "")

        header = {
            "venta_id": venta_id,
            "fecha_str": fecha_str,
            "cliente_nombre": cliente_nombre,
            "direccion": direccion,
            "total_venta": total_venta,
            "factura_despacho": factura_despacho,
        }

        # items: aseguramos columnas esperadas
        cols = ["producto", "calibre", "kg", "precio_unit", "precio_total"]
        for col in cols:
            if col not in g.columns:
                g[col] = ""

        items = g[cols].copy()

        orders.append({"header": header, "items": items})

    return orders
