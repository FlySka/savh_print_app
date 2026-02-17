from datetime import datetime

import pandas as pd
import pytz

from create_prints_server.config.settings import FilterConfig


def pick_filter_date(f: FilterConfig) -> pd.Timestamp:
    tz = pytz.timezone(f.timezone)

    if f.use_config_date:
        if not f.config_date:
            raise ValueError(
                "FILTER.USE_CONFIG_DATE=true pero FILTER.CONFIG_DATE está vacío."
            )
        return pd.to_datetime(f.config_date, errors="raise").normalize()

    # "hoy" local Chile (o la TZ que definas)
    now_local = datetime.now(tz)
    return pd.Timestamp(now_local.date())
