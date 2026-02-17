import pandas as pd
import numpy as np

def money_clp(x) -> str:
    if pd.isna(x):
        return ""
    try:
        x = float(x)
    except Exception:
        return ""
    # CLP sin decimales
    s = f"{x:,.0f}"
    return "$" + s.replace(",", ".")


def parse_cl_number(series: pd.Series) -> pd.Series:
    """
    Convierte valores típicos CL/Latam:
      '3,0'        -> 3.0
      '$2.000'     -> 2000.0
      '$14.500'    -> 14500.0
      '2.000,50'   -> 2000.5
      '20.00'      -> 20.0   (decimal punto)
      20.0 (float) -> 20.0
    """
    s = series.copy()

    # Si viene numérico puro, no lo toques
    if pd.api.types.is_numeric_dtype(s):
        return s.astype(float)

    s = s.astype(str).str.strip()

    # deja solo dígitos, separadores y signo
    s = s.str.replace(r"[^\d,\.\-]", "", regex=True)

    def _norm(x: str):
        if x is None:
            return np.nan
        x = x.strip()
        if x == "" or x.lower() == "nan":
            return np.nan

        # Caso con ambos: normalmente '.' miles y ',' decimal
        if "," in x and "." in x:
            x = x.replace(".", "").replace(",", ".")
        elif "," in x:
            # Solo coma => decimal coma
            x = x.replace(",", ".")
        else:
            # Solo punto o nada.
            # Si hay más de un punto => seguramente miles, quítalos.
            if x.count(".") > 1:
                x = x.replace(".", "")
            elif x.count(".") == 1:
                # Decide si ese punto es miles o decimal:
                # Si hay exactamente 3 dígitos después del punto y pocos antes => miles
                left, right = x.split(".")
                if len(right) == 3 and 1 <= len(left) <= 3:
                    x = left + right  # quita el punto (miles)
                # si no, lo dejamos como decimal (ej: 20.00)

        try:
            return float(x)
        except ValueError:
            return np.nan

    return s.map(_norm).astype(float)