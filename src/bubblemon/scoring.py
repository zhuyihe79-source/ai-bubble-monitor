from dataclasses import dataclass

import numpy as np
import pandas as pd

from .registry import Config, Indicator

WINDOW_WEEKS = 15 * 52   # 滚动分位数窗口
MIN_WEEKS = 3 * 52       # 历史不足 3 年不打分


def last_friday(asof: pd.Timestamp) -> pd.Timestamp:
    asof = pd.Timestamp(asof).normalize()
    return asof - pd.Timedelta(days=(asof.weekday() - 4) % 7)


def to_weekly(series: pd.Series, max_stale_days: int, asof: pd.Timestamp, lag_days: int = 0) -> pd.Series:
    """对齐到周五；按公布滞后平移，用前值填充，但超过 max_stale_days 的空档置为缺失。"""
    s = series.sort_index()
    s.index = s.index + pd.Timedelta(days=lag_days)
    end = last_friday(asof)
    s = s[s.index <= end]
    if s.empty:
        return s
    grid = pd.date_range(s.index[0].to_period("W-FRI").end_time.normalize(), end, freq="W-FRI")
    weekly = s.resample("W-FRI").last().reindex(grid).ffill()
    last_obs = pd.Series(s.index, index=s.index).resample("W-FRI").last().reindex(grid).ffill()
    age = (weekly.index.to_series() - last_obs).dt.days
    return weekly.where(age <= max_stale_days)


def rolling_percentile(weekly: pd.Series) -> pd.Series:
    """每个时点的值在过去窗口（含当前）里的分位，0-1。"""
    def rank_last(x: np.ndarray) -> float:
        x = x[~np.isnan(x)]
        if len(x) == 0:
            return np.nan
        return (x < x[-1]).sum() / max(len(x) - 1, 1) if len(x) > 1 else np.nan

    return weekly.rolling(WINDOW_WEEKS, min_periods=MIN_WEEKS).apply(rank_last, raw=True)


def indicator_score(series: pd.Series, ind: Indicator, asof: pd.Timestamp) -> pd.Series:
    """0-1 的风险分，越高越接近泡沫。"""
    weekly = to_weekly(series, ind.max_stale_days, asof, ind.publication_lag_days)
    if weekly.dropna().empty:
        return pd.Series(dtype=float)
    pct = rolling_percentile(weekly)
    return pct if ind.direction == "high" else 1 - pct


@dataclass
class ScoreResult:
    indicators: pd.DataFrame   # 周 × 指标，0-1
    dimensions: pd.DataFrame   # 周 × 维度，0-100
    total: pd.Series           # 周，0-100
    coverage: pd.Series        # 周，有多少比例的指标有分数


def compute(series_by_id: dict[str, pd.Series], cfg: Config, asof: pd.Timestamp | None = None) -> ScoreResult:
    asof = asof or pd.Timestamp.today().normalize()
    cols = {}
    for ind in cfg.scored:
        s = series_by_id.get(ind.id)
        if s is None or s.empty:
            continue
        sc = indicator_score(s, ind, asof)
        if not sc.empty:
            cols[ind.id] = sc
    if not cols:
        empty = pd.Series(dtype=float)
        return ScoreResult(pd.DataFrame(), pd.DataFrame(), empty, empty)

    ind_df = pd.DataFrame(cols)
    dim_cols = {}
    for dim in cfg.dimensions:
        members = [i.id for i in cfg.scored if i.dimension == dim and i.id in ind_df]
        if members:
            dim_cols[dim] = ind_df[members].mean(axis=1, skipna=True) * 100
    dim_df = pd.DataFrame(dim_cols)

    weights = pd.Series({d: cfg.dimensions[d]["weight"] for d in dim_df.columns})
    w = dim_df.notna().mul(weights, axis=1)
    total = dim_df.fillna(0).mul(weights, axis=1).sum(axis=1) / w.sum(axis=1)
    total = total.where(dim_df.notna().sum(axis=1) >= cfg.scoring.get("min_dimensions", 1))
    coverage = ind_df.notna().sum(axis=1) / len(cfg.scored)
    return ScoreResult(ind_df, dim_df.dropna(how="all"), total.dropna(), coverage)


def band(score: float, alerts: dict) -> str:
    if score >= alerts["score_red"]:
        return "red"
    if score >= alerts["score_yellow"]:
        return "yellow"
    return "green"
