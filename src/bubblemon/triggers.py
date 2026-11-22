from dataclasses import dataclass

import numpy as np
import pandas as pd

from .registry import Config, Trigger

LABEL = {"ok": "正常", "alert": "警戒", "triggered": "触发", "nodata": "无数据"}
SEVERITY = {"triggered": 0, "alert": 1, "ok": 2, "nodata": 3}


@dataclass
class TriggerState:
    trigger: Trigger
    status: str
    value: float = np.nan
    data_date: pd.Timestamp | None = None

    @property
    def label(self) -> str:
        return LABEL[self.status]


def visible(series: pd.Series, lag_days: int, asof: pd.Timestamp) -> pd.Series:
    """asof 当天实际能看到的数据：观测日期 + 公布滞后 <= asof。"""
    s = series.sort_index()
    return s[s.index + pd.Timedelta(days=lag_days) <= asof]


def value_near(s: pd.Series, target: pd.Timestamp, tolerance_days: int) -> float:
    """取离 target 最近、且在容差范围内的观测；季度数据的日期不一定刚好对齐。"""
    tol = pd.Timedelta(days=tolerance_days)
    window = s[(s.index >= target - tol) & (s.index <= target + tol)]
    if window.empty:
        return np.nan
    pos = np.abs((window.index - target).days).argmin()
    return float(window.iloc[pos])


def compute_value(s: pd.Series, t: Trigger) -> float:
    last_date, v = s.index[-1], float(s.iloc[-1])
    if t.transform == "level":
        return v
    if t.transform == "drawdown":
        window = s[s.index > last_date - pd.Timedelta(days=t.days)]
        return v / float(window.max()) - 1
    base = value_near(s, last_date - pd.Timedelta(days=t.days), t.tolerance_days)
    if np.isnan(base):
        return np.nan
    if t.transform == "pct_change":
        return v / base - 1 if base else np.nan
    return v - base  # diff


def classify(value: float, t: Trigger) -> str:
    if value is None or np.isnan(value):
        return "nodata"
    if t.direction == "above":
        return "triggered" if value >= t.trigger else "alert" if value >= t.alert else "ok"
    return "triggered" if value <= t.trigger else "alert" if value <= t.alert else "ok"


def evaluate(series_by_id: dict[str, pd.Series], cfg: Config, asof: pd.Timestamp) -> list[TriggerState]:
    asof = pd.Timestamp(asof).normalize()
    out = []
    for t in cfg.triggers:
        ind = cfg.indicator(t.series)
        raw = series_by_id.get(t.series)
        if raw is None or raw.empty:
            out.append(TriggerState(t, "nodata"))
            continue
        s = visible(raw.dropna(), ind.publication_lag_days, asof)
        if s.empty:
            out.append(TriggerState(t, "nodata"))
            continue
        published = s.index[-1] + pd.Timedelta(days=ind.publication_lag_days)
        if (asof - published).days > ind.max_stale_days:
            out.append(TriggerState(t, "nodata", data_date=s.index[-1]))
            continue
        value = compute_value(s, t)
        out.append(TriggerState(t, classify(value, t), value, s.index[-1]))
    return out


def history(series_by_id: dict[str, pd.Series], cfg: Config, dates) -> pd.DataFrame:
    """每个日期按当时可见的数据重算全部信号。行 = 日期，列 = 信号 id，值 = 状态。"""
    return pd.DataFrame({d: {s.trigger.id: s.status for s in evaluate(series_by_id, cfg, d)} for d in dates}).T


def base_rates(hist: pd.DataFrame) -> dict[str, tuple[float, int]]:
    """每个信号有数据的那些周里，多大比例处于警戒或触发；以及有数据的周数。

    比例高说明这条线平时就常被越过，单独亮起来不算稀奇。
    """
    out = {}
    for tid in hist:
        col = hist[tid][hist[tid] != "nodata"]
        if len(col):
            out[tid] = (float(col.isin(["alert", "triggered"]).mean()), len(col))
    return out


def fmt(value: float, unit: str) -> str:
    if value is None or np.isnan(value):
        return "—"
    if unit == "pct":
        return f"{value:+.1%}"
    if unit == "pp":
        return f"{value:+.2f} 个百分点"
    return f"{value:.2f}" if abs(value) < 10 else f"{value:.1f}"


def fmt_threshold(value: float, unit: str) -> str:
    if unit == "pct":
        return f"{value:+.0%}"
    if unit == "pp":
        return f"{value:+.2f}pp"
    return f"{value:g}"
