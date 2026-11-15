import io

import pandas as pd
import requests

URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"


def fetch(params: dict) -> pd.Series:
    """FRED 公开 CSV 接口，不需要 API key。"""
    series_id = params["series"]
    resp = requests.get(URL, params={"id": series_id, "cosd": "1990-01-01"}, timeout=30)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    date_col, val_col = df.columns[0], series_id
    s = pd.to_numeric(df[val_col], errors="coerce")  # FRED 用 "." 表示缺失
    s.index = pd.to_datetime(df[date_col])
    return s.dropna()
