import pandas as pd

from ..registry import ROOT


def fetch(params: dict) -> pd.Series:
    """读 data/manual/<file>，两列：date,value。适合没有免费 API 的指标（如 GPU 租赁价）。"""
    path = ROOT / "data" / "manual" / params["file"]
    df = pd.read_csv(path)
    if df.empty:
        raise RuntimeError(f"{path.name} 还没有数据，请手工录入")
    s = pd.Series(df["value"].astype(float).values, index=pd.to_datetime(df["date"]))
    return s.sort_index()
