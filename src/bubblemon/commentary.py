from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import alerts, triggers
from .registry import Config
from .scoring import ScoreResult, band, last_friday

BAND_CN = {"green": "低", "yellow": "升温", "red": "过热"}


def _get(series: dict, iid: str) -> pd.Series:
    s = series.get(iid)
    return s if s is not None and len(s) else pd.Series(dtype=float, index=pd.DatetimeIndex([]))


def _visible(series: dict, cfg: Config, iid: str, when: pd.Timestamp) -> pd.Series:
    lag = next((i.publication_lag_days for i in cfg.indicators if i.id == iid), 0)
    return triggers.visible(_get(series, iid), lag, when)


@dataclass
class Note:
    week: pd.Timestamp
    headline: str
    sections: list = field(default_factory=list)  # [(标题, [要点, ...])]


def _at(s: pd.Series, when: pd.Timestamp) -> float:
    s = s[s.index <= when]
    return float(s.iloc[-1]) if len(s) else np.nan


def _pct(s: pd.Series, end: pd.Timestamp, days: int) -> float:
    s = s[s.index <= end]
    if s.empty:
        return np.nan
    base = _at(s, s.index[-1] - pd.Timedelta(days=days))
    return float(s.iloc[-1]) / base - 1 if base else np.nan


def _signed(x: float) -> str:
    return "—" if np.isnan(x) else f"{round(x):+d}"


def _quarter(d: pd.Timestamp) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def _drivers(result: ScoreResult, cfg: Config, week: pd.Timestamp, prev: pd.Timestamp, top: int = 3) -> list[str]:
    """把总分变化拆到单个指标：指标分变化 × 它在总分里的权重。"""
    ind = result.indicators
    if week not in ind.index or prev not in ind.index:
        return []
    now, before = ind.loc[week], ind.loc[prev]
    dims_now = result.dimensions.loc[week].dropna()
    wsum = sum(cfg.dimensions[d]["weight"] for d in dims_now.index)
    rows = []
    for i in cfg.scored:
        if i.dimension not in dims_now.index or pd.isna(now.get(i.id)) or pd.isna(before.get(i.id)):
            continue
        n_in_dim = now[[j.id for j in cfg.scored if j.dimension == i.dimension and j.id in now]].notna().sum()
        contrib = (now[i.id] - before[i.id]) * cfg.dimensions[i.dimension]["weight"] / wsum / n_in_dim * 100
        rows.append((contrib, i.name, before[i.id], now[i.id]))
    rows.sort(key=lambda r: -abs(r[0]))
    return [f"{name}：风险分位 {b:.0%} → {a:.0%}，拉动总分 {c:+.1f}" for c, name, b, a in rows[:top] if abs(c) >= 0.05]


def weekly_note(series: dict[str, pd.Series], cfg: Config, result: ScoreResult, asof: pd.Timestamp) -> Note:
    week = last_friday(asof)
    prev, month = week - pd.Timedelta(days=7), week - pd.Timedelta(days=28)
    total = result.total
    now, d1, d4 = _at(total, week), _at(total, week) - _at(total, prev), _at(total, week) - _at(total, month)
    states = triggers.evaluate(series, cfg, week)
    before = {s.trigger.id: s for s in triggers.evaluate(series, cfg, prev)}
    n_trig = sum(s.status == "triggered" for s in states)
    n_alert = sum(s.status == "alert" for s in states)

    if np.isnan(now):
        headline = f"本周没有足够数据计算泡沫温度。{n_trig} 项信号触发、{n_alert} 项警戒。"
    else:
        headline = (f"泡沫温度 {now:.0f}（{BAND_CN[band(now, cfg.alerts)]}），较上周 {_signed(d1)}，较 4 周前 {_signed(d4)}；"
                    f"{len(states)} 个破裂信号中 {n_trig} 项触发、{n_alert} 项警戒。")
    note = Note(week, headline)

    changes = []
    for s in states:
        b = before.get(s.trigger.id)
        if b and b.status != s.status and "nodata" not in (b.status, s.status):
            worse = triggers.SEVERITY[s.status] < triggers.SEVERITY[b.status]
            changes.append(f"{'⚠ 恶化' if worse else '缓和'}｜{s.trigger.name}：{b.label} → {s.label}"
                           f"（当前 {triggers.fmt(s.value, s.trigger.unit)}）")
    note.sections.append(("信号状态变化", changes or ["本周没有信号改变状态。"]))

    drivers = _drivers(result, cfg, week, prev)
    note.sections.append(("总分变化来自哪里", drivers or ["各指标风险分位基本没有变化。"]))

    market = []
    nv, smh, spy = (_get(series, k) for k in ("nvda_price", "smh_price", "spy_price"))
    r_nv, r_smh, r_spy = _pct(nv, week, 7), _pct(smh, week, 7), _pct(spy, week, 7)
    if not np.isnan(r_nv):
        market.append(f"本周 NVDA {r_nv:+.1%}，SMH {r_smh:+.1%}，SPY {r_spy:+.1%}；"
                      f"半导体相对大盘 {'跑赢' if r_smh > r_spy else '跑输'} {abs(r_smh - r_spy) * 100:.1f} 个百分点。")
    hy, vix = _get(series, "hy_spread"), _get(series, "vix")
    if len(hy[hy.index <= week]) and len(vix[vix.index <= week]):
        hy_now = _at(hy, week)
        market.append(f"高收益债利差 {hy_now:.2f}%（周变化 {(hy_now - _at(hy, prev)) * 100:+.0f}bp），"
                      f"VIX {_at(vix, week):.1f}（周变化 {_at(vix, week) - _at(vix, prev):+.1f}）。")
    note.sections.append(("市场", market or ["缺少行情数据。"]))

    fund = []
    by_id = {s.trigger.id: s for s in states}
    capq = _visible(series, cfg, "hyperscaler_capex_q", week)
    if len(capq):
        yoy = _pct(capq, capq.index[-1], 365)
        ocf = by_id.get("capex_vs_ocf")
        fund.append(f"最新可见季度 {_quarter(capq.index[-1])}：五大云厂商单季 capex {capq.iloc[-1] / 1e8:,.0f} 亿美元"
                    f"（同比 {yoy:+.0%}，环比 {triggers.fmt(by_id['capex_qoq'].value if 'capex_qoq' in by_id else np.nan, 'pct')}）"
                    + (f"；滚动四季 capex / 经营现金流 = {ocf.value:.2f}" if ocf and not np.isnan(ocf.value) else "") + "。")
    rev = _visible(series, cfg, "nvda_revenue_q", week)
    if len(rev):
        fund.append(f"NVDA 最新财季（截至 {rev.index[-1].date()}）收入 {rev.iloc[-1] / 1e8:,.0f} 亿美元，"
                    f"同比 {triggers.fmt(by_id['nvda_rev_yoy'].value if 'nvda_rev_yoy' in by_id else np.nan, 'pct')}。")
    debt = _visible(series, cfg, "hyperscaler_debt", week)
    if len(debt):
        fund.append(f"五大云厂商有息负债 {debt.iloc[-1] / 1e8:,.0f} 亿美元，同比 {triggers.fmt(by_id['debt_yoy'].value if 'debt_yoy' in by_id else np.nan, 'pct')}。")
    note.sections.append(("基本面（财报）", fund or ["缺少财报数据。"]))

    watch = [f"【{s.label}】{s.trigger.name} {triggers.fmt(s.value, s.trigger.unit)}"
             f"（警戒 {triggers.fmt_threshold(s.trigger.alert, s.trigger.unit)} / 触发 {triggers.fmt_threshold(s.trigger.trigger, s.trigger.unit)}）："
             f"{s.trigger.why}"
             for s in sorted(states, key=lambda s: triggers.SEVERITY[s.status]) if s.status in ("triggered", "alert")]
    note.sections.append(("需要盯住的信号", watch or ["目前没有信号进入警戒区。"]))

    extremes = [m for m in alerts.evaluate(result, cfg) if "风险分位" in m]
    if extremes:
        note.sections.append(("处于历史极端的评分指标", extremes))
    return note


def history(series, cfg, result, asof, weeks: int = 8) -> list[Note]:
    week = last_friday(asof)
    return [weekly_note(series, cfg, result, week - pd.Timedelta(days=7 * k)) for k in range(weeks)]
