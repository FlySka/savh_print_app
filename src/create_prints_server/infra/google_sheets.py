import pandas as pd


def sheet_to_df(
    service, spreadsheet_id: str, sheet_name: str, a1_range: str
) -> pd.DataFrame:
    """transforma un sheet en un DF de pandas

    Args:
        service (_type_): _description_
        spreadsheet_id (str): _description_
        sheet_name (str): _description_
        a1_range (str): _description_

    Returns:
        pd.DataFrame: _description_
    """
    result = (
        service.spreadsheets()
        .values()
        .get(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_name}!{a1_range}",
        )
        .execute()
    )

    rows = result.get("values", [])
    if not rows:
        return pd.DataFrame()

    header = rows[0]
    data = rows[1:]

    # normaliza largo de filas (Google a veces trae filas más cortas)
    fixed = []
    for r in data:
        if len(r) < len(header):
            r = r + [""] * (len(header) - len(r))
        fixed.append(r[: len(header)])

    df = pd.DataFrame(fixed, columns=header)
    return df
