from __future__ import annotations

import pandas as pd


def parse_gtfs_date(series: pd.Series) -> pd.Series:
    if series.empty:
        return series
    return pd.to_datetime(series, format="%Y%m%d", errors="coerce").dt.date
