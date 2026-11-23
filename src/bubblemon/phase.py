"""阶段判断：把破裂信号归成四层，只用“价格破没破、需求破没破”回答现在是哪一种局面。

数信号个数没有意义：价格类信号总是一起亮，需求类信号一个就够；而且财报数据比股价晚一到两个季度。
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import triggers
from .registry import LAYERS, Config

# 只有“触发”才算破。警戒线是按这一轮的高增速定的，放到 2023 年以前属于常态，不能用来定阶段。
PHASES = {
    1: ("扩张", "价格没有跌破触发线，财报里的需求也没有转负。"),
    2: ("价格回调，需求未证实转弱", "价格已经跌破触发线，但已公布的财报里云厂商投入和英伟达收入都还在增长。"
        "接下来看财报：需求跟着掉就是破裂，没掉就只是一次回调。"),
    3: ("需求数据偏弱，价格未破", "财报里的需求已经转负，但股价不在低位。财报比股价晚一到两个季度，"
        "这种组合过去多数出现在下跌之后的恢复期，也可能是价格还没有反映。"),
    4: ("破裂确认", "价格跌破触发线，财报也证实需求转负。"),
}
SHORT = {1: "扩张", 2: "价格回调", 3: "需求偏弱", 4: "破裂确认"}
PHASE_COLOR = {1: "#23b26d", 2: "#f5a524", 3: "#8b94a7", 4: "#ff5459"}


def layer_states(statuses: dict[str, str], cfg: Config) -> dict[str, str]:
    """每一层取层内最差的状态；整层都没数据才算无数据。"""
    out = {}
    for layer in LAYERS:
        seen = [statuses[t.id] for t in cfg.triggers if t.layer == layer and statuses.get(t.id, "nodata") != "nodata"]
        out[layer] = min(seen, key=triggers.SEVERITY.get) if seen else "nodata"
    return out


def phase_of(layers: dict[str, str]) -> int:
    demand, price = layers.get("demand") == "triggered", layers.get("price") == "triggered"
    return 4 if demand and price else 3 if demand else 2 if price else 1


def history(status_hist: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """status_hist 来自 triggers.history。返回每个日期的各层状态和阶段。"""
    rows = {d: layer_states(row.to_dict(), cfg) for d, row in status_hist.iterrows()}
    out = pd.DataFrame(rows).T
    out["phase"] = [phase_of(r) for r in rows.values()]
    return out


def _after(price: pd.Series, day: pd.Timestamp, days: int) -> pd.Series | None:
    """day 之后 days 天的价格（除以 day 当天的价格）；还没走完返回 None。"""
    end = day + pd.Timedelta(days=days)
    past = price[price.index <= day]
    if past.empty or end > price.index[-1]:
        return None
    return price[(price.index >= day) & (price.index <= end)] / past.iloc[-1] - 1


def track_record(phases: pd.Series, price: pd.Series, days: int = 182) -> dict[int, dict]:
    """每个阶段在回测期占多少周、出现在哪几段，以及之后半年的涨跌中位数和期间最深跌幅的中位数。

    同一段行情里相邻的周高度相关，所以这些数只说明方向，不是概率。
    """
    px = price.dropna().sort_index()
    runs = (phases != phases.shift()).cumsum()
    out = {}
    for p in PHASES:
        mask = phases == p
        spans = [(g.index[0], g.index[-1]) for _, g in phases[mask].groupby(runs[mask])]
        paths = [x for x in (_after(px, d, days) for d in phases.index[mask]) if x is not None]
        out[p] = {
            "share": float(mask.mean()), "weeks": int(mask.sum()), "spans": spans,
            "median_return": float(np.median([x.iloc[-1] for x in paths])) if paths else float("nan"),
            "median_worst": float(np.median([x.min() for x in paths])) if paths else float("nan"),
        }
    return out


@dataclass
class Episode:
    start: pd.Timestamp          # 第一次跌破触发线
    trough: pd.Timestamp
    max_drawdown: float          # 距 52 周高点最深跌了多少
    further: float               # 从第一次跌破那天算，之后 12 个月内最多又跌了多少
    after_12m: float             # 第一次跌破后 12 个月的涨跌；没走完是 nan
    demand_quarter: pd.Timestamp | None   # 证实需求转差的财季（收入环比跌破触发线），没有就是 None
    demand_qoq: float
    confirm_date: pd.Timestamp | None     # 这份财报可见的日子
    drop_at_confirm: float       # 财报可见那天，股价比跌破前的 52 周高点低多少
    after_confirm: float         # 财报可见之后 12 个月内最多又跌了多少
    ongoing: bool

    @property
    def confirmed(self) -> bool:
        return self.demand_quarter is not None


def _qoq(revenue_q: pd.Series) -> pd.Series:
    out = {}
    for d, v in revenue_q.items():
        base = triggers.value_near(revenue_q, d - pd.Timedelta(days=91), 25)
        if base and not np.isnan(base):
            out[d] = v / base - 1
    return pd.Series(out, dtype=float)


def drawdown_episodes(price: pd.Series, revenue_q: pd.Series, cfg: Config, since: str = "2010-01-01",
                      merge_days: int = 90) -> list[Episode]:
    """NVDA 每一段跌破回撤触发线的经历，以及前后三个季度内收入有没有跟着掉。

    相隔不到 merge_days 的两次跌破算同一段。
    """
    dd_t = next(t for t in cfg.triggers if t.id == "nvda_drawdown")
    rev_t = next(t for t in cfg.triggers if t.id == "nvda_rev_qoq")
    lag = pd.Timedelta(days=cfg.indicator(rev_t.series).publication_lag_days)
    px = price.dropna().sort_index()
    high = px.rolling(f"{dd_t.days}D").max()
    dd = px / high - 1
    below = dd[(dd <= dd_t.trigger) & (dd.index >= pd.Timestamp(since))]
    spans: list[list[pd.Timestamp]] = []
    for d in below.index:
        if spans and (d - spans[-1][1]).days <= merge_days:
            spans[-1][1] = d
        else:
            spans.append([d, d])
    qoq = _qoq(revenue_q.dropna().sort_index())
    year = pd.Timedelta(days=365)
    out = []
    for start, end in spans:
        window = dd[(dd.index >= start) & (dd.index <= end)]
        after = px[(px.index >= start) & (px.index <= start + year)]
        near = qoq[(qoq.index >= start - pd.Timedelta(days=100)) & (qoq.index <= start + pd.Timedelta(days=270))]
        hit = near[near <= rev_t.trigger]
        quarter = hit.index[0] if len(hit) else None
        confirm = drop = more = None
        if quarter is not None and quarter + lag <= px.index[-1]:
            confirm = quarter + lag
            seen = px[px.index <= confirm]
            p = seen.iloc[-1]
            drop = float(p / high[start] - 1)
            more = float(px[(px.index >= seen.index[-1]) & (px.index <= confirm + year)].min() / p - 1)
        out.append(Episode(
            start=start, trough=window.idxmin(), max_drawdown=float(window.min()),
            further=float(after.min() / px[start] - 1),
            after_12m=float(after.iloc[-1] / px[start] - 1) if start + year <= px.index[-1] else float("nan"),
            demand_quarter=quarter, demand_qoq=float(hit.iloc[0]) if len(hit) else float("nan"),
            confirm_date=confirm, drop_at_confirm=float("nan") if drop is None else drop,
            after_confirm=float("nan") if more is None else more,
            ongoing=(px.index[-1] - end).days <= merge_days,
        ))
    return out
