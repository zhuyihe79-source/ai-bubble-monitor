import argparse
import html
from pathlib import Path

import markdown
import pandas as pd
import plotly.graph_objects as go

from . import commentary, db, news, scoring, triggers
from .registry import GROUPS, ROOT, load_config

COLORS = {"green": "#1f9d61", "yellow": "#d98a00", "red": "#e5484d"}
LABELS = {"green": "低", "yellow": "升温", "red": "过热"}
HEAT_WEEKS = 12

CSS = """
:root{--bg:#f5f6f8;--card:#fff;--ink:#0f172a;--ink2:#475569;--ink3:#8a94a6;--line:#e6e9ef;--soft:#f1f3f7;
--red:#e5484d;--amber:#f0a020;--green:#1f9d61;--r:14px}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:72px}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.65 Inter,-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans CJK SC",sans-serif;-webkit-font-smoothing:antialiased}
a{color:#2563eb;text-decoration:none}a:hover{text-decoration:underline}
small{color:var(--ink3);font-size:12.5px}b{font-weight:650}
.top{position:sticky;top:0;z-index:10;background:rgba(255,255,255,.86);backdrop-filter:saturate(180%) blur(12px);-webkit-backdrop-filter:saturate(180%) blur(12px);border-bottom:1px solid var(--line)}
.top .in{max-width:1180px;margin:0 auto;padding:0 24px;height:56px;display:flex;align-items:center;gap:28px}
.brand{font-weight:700;font-size:15px;white-space:nowrap;display:flex;align-items:center;gap:10px}
.brand i{width:9px;height:9px;border-radius:50%;background:var(--red);box-shadow:0 0 0 4px #e5484d26}
.top nav{display:flex;gap:2px;overflow-x:auto;scrollbar-width:none}.top nav::-webkit-scrollbar{display:none}
.top nav a{color:var(--ink2);padding:6px 10px;border-radius:8px;font-size:13px;white-space:nowrap}
.top nav a:hover{background:var(--soft);color:var(--ink);text-decoration:none}
main{max-width:1180px;margin:0 auto;padding:30px 24px 56px}
.title{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap;margin-bottom:20px}
.title h1{font-size:28px;line-height:1.2;letter-spacing:-.02em;margin:0}
.title p{margin:6px 0 0;color:var(--ink2)}
.stamp{color:var(--ink3);font-size:12.5px;text-align:right}
.hero{display:grid;grid-template-columns:1.45fr 1fr 1fr 1.25fr;gap:16px;margin-bottom:20px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:20px 22px;display:flex;flex-direction:column;gap:10px;min-width:0}
.kpi.main{background:linear-gradient(160deg,#fff 40%,#fff5f5)}
.eyebrow{font-size:12px;font-weight:600;color:var(--ink3);letter-spacing:.05em}
.num{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
.big{font-size:60px;font-weight:750;line-height:1;letter-spacing:-.04em;font-variant-numeric:tabular-nums}
.mid{font-size:40px;font-weight:700;line-height:1;letter-spacing:-.03em;font-variant-numeric:tabular-nums}
.mid small{font-size:15px;font-weight:600;letter-spacing:0;margin-left:2px}
.pill{display:inline-flex;align-items:center;gap:6px;padding:2px 10px;border-radius:999px;font-size:12.5px;font-weight:600;white-space:nowrap}
.scale{position:relative;height:8px;border-radius:999px;margin-top:6px;background:linear-gradient(90deg,#cdeedb 0 60%,#fbe3a8 60% 80%,#f9c7c8 80%)}
.scale.gray{background:linear-gradient(90deg,#e7ebf1,#cfd6e1)}
.scale b{position:absolute;top:-5px;width:4px;height:18px;border-radius:2px;background:var(--ink);transform:translateX(-50%);box-shadow:0 0 0 2px #fff}
.ticks{display:flex;justify-content:space-between;font-size:11px;color:var(--ink3);font-variant-numeric:tabular-nums}
.deltas{display:flex;gap:14px;flex-wrap:wrap;font-size:12.5px;color:var(--ink2)}.deltas b{font-variant-numeric:tabular-nums}
.up{color:var(--red)}.down{color:var(--green)}.flat{color:var(--ink3)}
.counts{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.counts div{background:var(--soft);border-radius:10px;padding:8px 10px}
.counts b{display:block;font-size:24px;line-height:1.1;font-variant-numeric:tabular-nums}
.counts span{font-size:12px;color:var(--ink2)}
.seg{display:flex;gap:4px;margin-top:4px}.seg i{flex:1;height:8px;border-radius:3px;background:#e7ebf1}
.kpi .note{font-size:12px;color:var(--ink3);line-height:1.55}
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:22px 24px;margin-bottom:20px;min-width:0}
.card>h2{font-size:17px;line-height:1.35;margin:0;letter-spacing:-.01em}
.card>.sub{color:var(--ink3);font-size:12.5px;margin:4px 0 14px}
.card>h2+*:not(.sub){margin-top:14px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px;align-items:start}
.grid-news{display:grid;grid-template-columns:1.7fr 1fr;gap:20px;margin-bottom:20px;align-items:start}
.grid2>.card,.grid-news>.card{margin-bottom:0}
.sticky{position:sticky;top:76px}
.tw{overflow-x:auto;margin:0 -4px;padding:0 4px}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th{font-size:12px;font-weight:600;color:var(--ink3);text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);white-space:nowrap}
td{padding:12px 10px;border-bottom:1px solid #eff1f5;vertical-align:top}
tr:last-child td{border-bottom:0}
.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.why{color:var(--ink2);font-size:12.5px;line-height:1.55;margin-top:2px}
.badge{display:inline-flex;align-items:center;gap:6px;padding:2px 9px;border-radius:999px;font-size:12px;font-weight:600;white-space:nowrap}
.badge::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor}
.s-triggered{background:#fdeced;color:#c4242b}.s-alert{background:#fdf3dc;color:#9a6200}
.s-ok{background:#e4f5eb;color:#17794a}.s-nodata{background:var(--soft);color:var(--ink3)}
.s-news{background:#fdeced;color:#c4242b}
.bar{display:inline-block;width:84px;height:6px;background:#eceff4;border-radius:999px;vertical-align:middle;margin-right:6px;overflow:hidden}
.bar i{display:block;height:100%;border-radius:999px}
.headline{font-size:15.5px;font-weight:600;line-height:1.6;padding:12px 16px;background:#f8fafc;border-left:3px solid var(--red);border-radius:0 10px 10px 0;margin:14px 0 6px}
.sec h3{font-size:13px;font-weight:650;margin:16px 0 4px;color:var(--ink)}
.sec ul{margin:0;padding-left:18px}.sec li{margin:3px 0;font-size:13.5px;line-height:1.6;color:var(--ink2)}
.heat{border-collapse:separate;border-spacing:3px;width:auto}
.heat td{padding:0;border:0;width:30px;height:24px;border-radius:5px}
.heat td.name{width:auto;padding:0 14px 0 0;font-size:12.5px;color:var(--ink2);white-space:nowrap;border-radius:0}
.heat th{font-size:11px;font-weight:500;padding:0 0 4px;border:0;text-align:center;color:var(--ink3)}
.h-triggered{background:#e5484d}.h-alert{background:#f3b23f}.h-ok{background:#c3e9d3}.h-nodata{background:#eef0f4}
.legend{display:flex;gap:14px;flex-wrap:wrap;margin-top:10px;font-size:12px;color:var(--ink2)}
.legend span{display:inline-flex;align-items:center;gap:6px}.legend i{width:12px;height:12px;border-radius:3px;display:inline-block}
.minis{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
.mini{border:1px solid var(--line);border-radius:12px;padding:12px 14px 6px;min-width:0}
.mhead{display:flex;justify-content:space-between;align-items:flex-start;gap:8px;font-size:13px;line-height:1.45}
.mval{font-size:20px;font-weight:700;font-variant-numeric:tabular-nums;margin:2px 0 2px}.mval small{font-size:11.5px;font-weight:500;margin-left:4px}
@media(max-width:1000px){.minis{grid-template-columns:1fr 1fr}}@media(max-width:700px){.minis{grid-template-columns:1fr}}
.past details{border:1px solid var(--line);border-radius:10px;padding:10px 14px;margin-top:10px}
.past details[open]{background:#fbfcfd}
.past summary{cursor:pointer;font-weight:600;font-size:13.5px;line-height:1.55;list-style:none}
.past summary::-webkit-details-marker{display:none}
.past summary::before{content:"›";display:inline-block;margin-right:8px;color:var(--ink3);transition:transform .15s}
.past details[open] summary::before{transform:rotate(90deg)}
.news{padding:14px 0;border-bottom:1px solid #eff1f5}.news:first-of-type{padding-top:4px}.news:last-child{border-bottom:0}
.news .meta{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:6px}
.news a.t{display:block;font-weight:650;color:var(--ink);font-size:14.5px;line-height:1.5}
.news a.t:hover{color:#2563eb;text-decoration:none}
.news .sum{color:var(--ink2);font-size:13.5px;margin-top:4px}
.news .imp{margin-top:6px;font-size:12.5px;color:var(--ink);background:#f8fafc;border-radius:8px;padding:6px 10px}
.stars{color:#f0a020;letter-spacing:1px;font-size:12px}.stars em{color:#dde1e8;font-style:normal}
.tag{background:var(--soft);color:var(--ink2);border-radius:6px;padding:1px 8px;font-size:12px}
.nheat{border-collapse:separate;border-spacing:3px}
.nheat td,.nheat th{text-align:center;border:0;padding:4px 2px;font-size:12px}
.nheat td{border-radius:5px;font-weight:600;font-variant-numeric:tabular-nums}
.nheat td:first-child{text-align:left;white-space:nowrap;padding-right:10px;font-weight:500;color:var(--ink2)}
.prose{max-width:none}
.prose h1{font-size:21px;line-height:1.45;letter-spacing:-.01em;margin:14px 0 12px}
.prose h2{font-size:15.5px;margin:22px 0 8px;padding-top:16px;border-top:1px solid var(--line)}
.prose h3{font-size:14px;margin:14px 0 4px}
.prose p,.prose li{font-size:14.5px;line-height:1.8;color:#1e293b}
.prose ul,.prose ol{padding-left:22px}.prose li{margin:4px 0}
.prose table{margin:10px 0}.prose th,.prose td{border-bottom:1px solid var(--line)}
.nalert{margin-top:8px;font-size:12.5px;display:flex;gap:6px;align-items:center;flex-wrap:wrap}.nalert a{color:#c4242b}
.lead{color:var(--ink2);margin:6px 0 14px}.lead b{color:var(--ink)}
footer{color:var(--ink3);font-size:12px;line-height:1.7;margin-top:8px}
@media(max-width:1000px){.hero{grid-template-columns:1fr 1fr}.grid-news{grid-template-columns:1fr}.sticky{position:static}}
@media(max-width:700px){.hero,.grid2{grid-template-columns:1fr}main{padding:20px 14px 40px}.card{padding:18px 16px}
.big{font-size:52px}.title h1{font-size:23px}.stamp{text-align:left}.top .in{padding:0 14px;gap:14px}.brand span{display:none}}
"""


def _fig_html(fig: go.Figure, first: bool, cdn: bool = False) -> str:
    js = ("cdn" if cdn else True) if first else False
    return fig.to_html(full_html=False, include_plotlyjs=js, config={"displayModeBar": False, "responsive": True})


def _note_html(note: commentary.Note, with_headline: bool = True) -> str:
    parts = [f"<div class=headline>{html.escape(note.headline)}</div>"] if with_headline else []
    for title, items in note.sections:
        lis = "".join(f"<li>{html.escape(x)}</li>" for x in items)
        parts.append(f"<div class=sec><h3>{html.escape(title)}</h3><ul>{lis}</ul></div>")
    return "".join(parts)


DIR_CLASS = {"risk_up": "s-triggered", "risk_down": "s-ok", "neutral": "s-nodata"}


def _news_html(items: list, trigger_names: dict) -> str:
    if not items:
        return "<p><small>最近 7 天还没有新闻数据（等待分析师定时任务运行）。</small></p>"
    rows = []
    for x in sorted(items, key=lambda x: (-x.importance, -x.published.value))[:25]:
        sig = f"<span class=tag>关联：{html.escape(trigger_names.get(x.signal, x.signal))}</span>" if x.signal else ""
        rows.append(
            f"<div class=news><div class=meta><span class=stars title='重要性 {x.importance}/5'>{'★' * x.importance}<em>{'★' * (5 - x.importance)}</em></span>"
            f"<span class='badge {DIR_CLASS[x.direction]}'>{news.DIRECTIONS[x.direction]}</span>"
            f"<span class=tag>{news.TOPICS[x.topic]}</span>{sig}"
            f"<small>{html.escape(x.source)} · {x.published:%m-%d}</small></div>"
            f"<a class=t href='{html.escape(x.url, quote=True)}' target=_blank rel=noopener>{html.escape(x.title)}</a>"
            f"<div class=sum>{html.escape(x.summary)}</div><div class=imp>→ {html.escape(x.implication)}</div></div>")
    return "".join(rows)


def _heat_news_html(df: pd.DataFrame, rate_hist: dict | None = None) -> str:
    if df.empty or df["count"].sum() == 0:
        return "<p><small>暂无数据。</small></p>"
    weeks = sorted(df["week_end"].unique())
    head = "".join(f"<th>{pd.Timestamp(w):%m/%d}</th>" for w in weeks)
    rows = []
    for topic, label in news.TOPICS.items():
        cells = []
        for w in weeks:
            r = df[(df.topic == topic) & (df.week_end == w)].iloc[0]
            style = ("background:#fbd5d6;color:#a3181e" if r.net > 0 else "background:#cdeedb;color:#11653c" if r.net < 0
                     else "background:#f1f3f7;color:#64748b")
            cells.append(f"<td style='{style}' title='净方向 {r.net:+d}'>{r['count'] or ''}</td>")
        rows.append(f"<tr><td>{label}</td>{''.join(cells)}</tr>")
    if rate_hist:
        cells = "".join(
            f"<td style='color:{LEVEL_COLOR.get(rate_hist[w].level, '#c4c8cf')};font-size:13px'>{rate_hist[w].level or '—'}</td>"
            for w in weeks)
        rows.append(f"<tr><td><b>分析师评级</b></td>{cells}</tr>")
    return (f"<div class=tw><table class=nheat><tr><th></th>{head}</tr>{''.join(rows)}</table></div>"
            "<p><small>数字 = 重要性 ≥ 3 的新闻条数。红 = 风险上升的多于下降的，绿相反。每列为截至该日的 7 天。</small></p>")


LEVEL_COLOR = {1: "#1f9d61", 2: "#6cbf8a", 3: "#8a94a6", 4: "#f0a020", 5: "#e5484d"}


def _rating_html(r: news.Rating) -> str:
    if r.level is None:
        return ("<div class=kpi><div class=eyebrow>分析师风险评级</div><div class=mid style='color:#c4c8cf'>—</div>"
                "<div class=note>近 7 天新闻不足</div></div>")
    rule = f"规则值 {r.rule_level}（近 7 天新闻净方向 {r.balance:+.2f}，权重 {r.weight:g}）"
    if r.forced:
        rule += "，因有重要性 5 的风险上升新闻抬到至少 4"
    if r.reason:
        adj = r.level - r.rule_level
        rule += f"；分析师{'维持' if adj == 0 else '上调' if adj > 0 else '下调'}{'' if adj == 0 else f' {abs(adj)} 级'}：{html.escape(r.reason)}"
    seg = "".join(f"<i style='background:{LEVEL_COLOR[r.level] if k <= r.level else '#e7ebf1'}'></i>" for k in range(1, 6))
    return (f"<div class=kpi><div class=eyebrow>分析师风险评级 · 新闻</div>"
            f"<div class=num><div class=mid style='color:{LEVEL_COLOR[r.level]}'>{r.level}<small>/5</small></div>"
            f"<span class=pill style='background:{LEVEL_COLOR[r.level]}1f;color:{LEVEL_COLOR[r.level]}'>{news.LEVELS[r.level]}</span></div>"
            f"<div class=seg>{seg}</div><div class=note>{r.asof.date()}，基于新闻，不计入温度。{rule}</div></div>")


def _level_word(v: float) -> str:
    return "历史高位" if v >= 80 else "偏高" if v >= 60 else "中等" if v >= 40 else "偏低"


def _bar(v: float) -> str:
    """v 是 0–100。"""
    color = "#e5484d" if v >= 80 else "#f0a020" if v >= 60 else "#94a3b8"
    return f"<div class=bar><i style='width:{v:.0f}%;background:{color}'></i></div>"


def _dimension_section(res: scoring.ScoreResult, cfg, group: str = "ai",
                       lookback: pd.Timedelta = pd.Timedelta(weeks=13)) -> str:
    """回答：分数由哪几块构成，过去 3 个月是谁在推高或拉低、具体是哪个指标。"""
    score = res.total if group == "ai" else res.market
    group_dims = cfg.group_dims(group)
    if score.empty:
        return "<p><small>数据不足。</small></p>"
    dims, inds = res.dimensions.reindex(columns=group_dims), res.indicators
    end = score.index[-1]
    then = score.index[score.index <= end - lookback]
    then = then[-1] if len(then) else score.index[0]
    weights = pd.Series({d: cfg.dimensions[d]["weight"] for d in group_dims})

    def contrib(t):  # 每个维度对当周分数贡献了几度（分数 = 有数据维度的加权平均）
        row = dims.loc[t]
        w = weights[row.notna()]
        return (row.dropna() * w / w.sum()).reindex(group_dims)

    c_now, c_then = contrib(end), contrib(then)
    delta_total = score.loc[end] - score.loc[then]
    rows, moves = [], []
    for d in group_dims:
        meta = cfg.dimensions[d]
        label, desc = html.escape(meta["label"]), html.escape(meta.get("desc", ""))
        cur = dims[d].get(end)
        if cur is None or pd.isna(cur):
            rows.append(f"<tr><td><b>{label}</b><div class=why>{desc}</div></td><td colspan=4><small>暂无数据，不参与计算</small></td></tr>")
            continue
        old = dims[d].get(then)
        dc = c_now[d] - (0 if pd.isna(c_then[d]) else c_then[d])
        moves.append((dc, meta["label"]))
        ids = [i.id for i in cfg.scored if i.dimension == d and i.id in inds]
        chg = sorted(((inds[i].get(end) - inds[i].get(then), i) for i in ids
                      if pd.notna(inds[i].get(end)) and pd.notna(inds[i].get(then))), key=lambda x: -abs(x[0]))
        entered = [i for i in ids if pd.notna(inds[i].get(end)) and pd.isna(inds[i].get(then))]
        left = [i for i in ids if pd.isna(inds[i].get(end)) and pd.notna(inds[i].get(then))]
        if entered or left:  # 指标进出会让维度分跳变，这不是市场变化，要单独说明
            driver = "；".join([f"新加入 {html.escape(cfg.indicator(i).name)}（{inds[i][end]:.0%}）" for i in entered]
                              + [f"{html.escape(cfg.indicator(i).name)} 缺数据，暂不计入" for i in left])
        elif chg and abs(chg[0][0]) >= 0.05:
            ind = cfg.indicator(chg[0][1])
            driver = f"{html.escape(ind.name)}：{inds[ind.id][then]:.0%} → {inds[ind.id][end]:.0%}"
        else:
            driver = "各指标变化不大"
        cls = "up" if dc >= 1 else "down" if dc <= -1 else "flat"
        rows.append(
            f"<tr><td><b>{label}</b><div class=why>{desc}</div></td>"
            f"<td style='white-space:nowrap'>{_bar(cur)}<b>{cur:.0f}</b> <small>{_level_word(cur)}</small></td>"
            f"<td class=n>{'—' if pd.isna(old) else f'{old:.0f}'} → {cur:.0f}</td>"
            f"<td class=n><b class={cls}>{dc:+.1f}</b></td><td class=why>{driver}</td></tr>")
    moves.sort(key=lambda x: -abs(x[0]))
    top = "；".join(f"{name} {'推高' if v > 0 else '拉低'} {abs(v):.1f}" for v, name in moves[:3] if abs(v) >= 0.5) or "各维度变化都不大"
    n = int(dims.loc[end].notna().sum())
    head = (f"<p class=lead>{GROUPS[group]} {score.loc[end]:.0f} = {n} 个有数据维度的平均。和 3 个月前（{then.date()}，{score.loc[then]:.0f}）相比 "
            f"<b>{delta_total:+.0f}</b>，主要来自：{top}。</p>")
    return (head + "<div class=tw><table><tr><th>维度（在问什么）</th><th>当前分</th><th class=n>3 个月前 → 现在</th>"
            "<th class=n>对分数变化的贡献（度）</th><th>变化最大的指标（风险分位）</th></tr>" + "".join(rows) + "</table></div>")


def _signal_history(raw: pd.Series, t, ind, dates) -> pd.Series:
    """每周按当时可见的数据重算信号值，和信号表用同一套规则。"""
    s = raw.dropna().sort_index()
    lag = pd.Timedelta(days=ind.publication_lag_days)
    out = {}
    for w in dates:
        vis = s[s.index + lag <= w]
        if vis.empty or (w - (vis.index[-1] + lag)).days > ind.max_stale_days:
            out[w] = float("nan")
            continue
        out[w] = triggers.compute_value(vis, t)
    return pd.Series(out, dtype=float)


TICK = {"pct": ".0%", "pp": "+.2f", "num": ".3~g"}
POINT = {"triggered": "#e5484d", "alert": "#f0a020", "ok": "#1f9d61", "nodata": "#94a3b8"}


def _signal_charts(series, cfg, states: dict, start: pd.Timestamp, end: pd.Timestamp, cdn: bool) -> str:
    dates = pd.date_range(start, end, freq="W-FRI")
    if end not in dates:
        dates = dates.append(pd.DatetimeIndex([end]))
    cards = []
    for s in sorted(states.values(), key=lambda s: (triggers.SEVERITY[s.status], s.trigger.name)):
        t = s.trigger
        raw = series.get(t.series)
        hist = _signal_history(raw, t, cfg.indicator(t.series), dates) if raw is not None and not raw.empty else pd.Series(dtype=float)
        hist = hist.dropna()
        if hist.empty:
            continue
        lo, hi = min(hist.min(), t.alert, t.trigger), max(hist.max(), t.alert, t.trigger)
        pad = (hi - lo) * 0.08 or abs(hi) * 0.1 or 1
        lo, hi = lo - pad, hi + pad
        if t.direction == "above":
            warn, bad = (t.alert, t.trigger), (t.trigger, hi)
        else:
            warn, bad = (t.trigger, t.alert), (lo, t.trigger)
        fig = go.Figure()
        fig.add_hrect(y0=warn[0], y1=warn[1], fillcolor="#f0a020", opacity=0.12, line_width=0, layer="below")
        fig.add_hrect(y0=bad[0], y1=bad[1], fillcolor="#e5484d", opacity=0.12, line_width=0, layer="below")
        quarterly = cfg.indicator(t.series).publication_lag_days > 0
        fig.add_scatter(x=hist.index, y=hist.values, mode="lines", line=dict(color="#334155", width=1.8, shape="hv" if quarterly else "linear"),
                        hovertemplate=f"%{{x|%Y-%m-%d}}<br>%{{y:{TICK.get(t.unit, '.2f')}}}<extra></extra>")
        fig.add_scatter(x=[hist.index[-1]], y=[hist.iloc[-1]], mode="markers", hoverinfo="skip",
                        marker=dict(size=8, color=POINT[s.status], line=dict(color="#fff", width=2)))
        fig.update_layout(height=150, margin=dict(l=0, r=4, t=4, b=0), showlegend=False,
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          font=dict(family="Inter,-apple-system,'PingFang SC',sans-serif", size=10.5, color="#8a94a6"),
                          xaxis=dict(showgrid=False, linecolor="#e6e9ef", tickformat="%y年%-m月", nticks=4),
                          yaxis=dict(range=[lo, hi], gridcolor="#f1f3f7", zeroline=False, tickformat=TICK.get(t.unit, ".2f"), nticks=4))
        cards.append(
            f"<div class=mini><div class=mhead><b>{html.escape(t.name)}</b>{_badge(s.status)}</div>"
            f"<div class=mval>{triggers.fmt(s.value, t.unit)} <small>警戒 {triggers.fmt_threshold(t.alert, t.unit)} · 触发 {triggers.fmt_threshold(t.trigger, t.unit)}</small></div>"
            f"{_fig_html(fig, False, cdn)}</div>")
    return f"<div class=minis>{''.join(cards)}</div>"


def _badge(status: str) -> str:
    return f"<span class='badge s-{status}'>{triggers.LABEL[status]}</span>"


def _delta(v: float, label: str) -> str:
    cls = "up" if v >= 0.5 else "down" if v <= -0.5 else "flat"
    return f"<span>{label} <b class={cls}>{v:+.0f}</b></span>"


def build(cdn: bool = False, asof: pd.Timestamp | None = None) -> str:
    cfg = load_config()
    con = db.connect()
    series = {i.id: db.load_series(con, i.id) for i in cfg.indicators}
    asof = pd.Timestamp(asof or scoring.today()).normalize()
    day = scoring.data_day(series, cfg, asof)
    res = scoring.compute(series, cfg, day)
    if res.total.empty:
        raise SystemExit("没有可用数据，请先运行 bubblemon-fetch")

    week = scoring.last_friday(day)
    notes = commentary.history(series, cfg, res, day, weeks=8)
    note = notes[0]
    tot = res.total
    latest = tot.iloc[-1]
    b = scoring.band(latest, cfg.alerts)
    d1 = latest - tot.iloc[-2] if len(tot) > 1 else 0.0
    d4 = latest - tot.iloc[-5] if len(tot) > 4 else 0.0

    weeks = [day - pd.Timedelta(days=7 * k) for k in range(HEAT_WEEKS)][::-1]
    by_week = {w: {s.trigger.id: s for s in triggers.evaluate(series, cfg, w)} for w in weeks}
    now = by_week[day]
    prev, month = by_week[weeks[-2]], by_week[weeks[-5]]
    counts = {k: sum(s.status == k for s in now.values()) for k in ("triggered", "alert", "ok", "nodata")}

    all_news = news.load()
    assessments = news.load_assessments()
    # 评级按最近一个新闻文件的日期算：定时任务早上写文件，看板晚上发布时仍沿用当天的分析师判断
    news_day = max((x.file_date for x in all_news if x.file_date is not None and x.file_date <= asof), default=asof)
    rate = news.rating(all_news, assessments, news_day)
    alerts = news.signal_alerts(all_news, asof)

    count_cells = "".join(
        f"<div><b style='color:{c}'>{counts[k]}</b><span>{triggers.LABEL[k]}</span></div>"
        for k, c in (("triggered", "#e5484d"), ("alert", "#d98a00"), ("ok", "#1f9d61")))
    extra = []
    if counts["nodata"]:
        extra.append(f"{counts['nodata']} 项无数据")
    if alerts:
        extra.append(f"<span class=up>新闻预警 {len(alerts)} 项</span>")
    signal_note = "；".join(extra) or "衡量“有没有开始破”，与温度分开看"

    rows = []
    for s in sorted(now.values(), key=lambda s: (triggers.SEVERITY[s.status], s.trigger.name)):
        t = s.trigger
        dd = "—" if s.data_date is None else str(s.data_date.date())
        na = "".join(f"<div class=nalert><span class='badge s-news'>新闻预警</span> "
                     f"<a href='{html.escape(x.url, quote=True)}' target=_blank rel=noopener>{html.escape(x.title)}</a>"
                     f" <small>{x.published.date()}</small></div>" for x in alerts.get(t.id, []))
        rows.append(
            f"<tr><td>{_badge(s.status)}</td><td><b>{html.escape(t.name)}</b><div class=why>{html.escape(t.why)}</div>{na}</td>"
            f"<td class=n><b>{triggers.fmt(s.value, t.unit)}</b></td>"
            f"<td class=n>{triggers.fmt_threshold(t.alert, t.unit)} / {triggers.fmt_threshold(t.trigger, t.unit)}</td>"
            f"<td>{_badge(prev[t.id].status)}</td><td>{_badge(month[t.id].status)}</td><td class=n><small>{dd}</small></td></tr>"
        )

    heat_head = "".join(f"<th>{w:%m/%d}</th>" for w in weeks)
    heat_rows = []
    for t in cfg.triggers:
        cells = "".join(
            f"<td class=h-{by_week[w][t.id].status} title='{w.date()} {by_week[w][t.id].label} {triggers.fmt(by_week[w][t.id].value, t.unit)}'></td>"
            for w in weeks)
        heat_rows.append(f"<tr><td class=name>{html.escape(t.name)}</td>{cells}</tr>")
    heat_legend = "".join(f"<span><i class=h-{k}></i>{triggers.LABEL[k]}</span>" for k in ("triggered", "alert", "ok", "nodata"))

    mk = res.market[res.market.index >= tot.index[0]]
    signal_charts = _signal_charts(series, cfg, now, tot.index[0], day, cdn)
    font = "Inter,-apple-system,'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',sans-serif"
    trend = go.Figure()
    trend.add_hrect(y0=cfg.alerts["score_yellow"], y1=cfg.alerts["score_red"], fillcolor="#f0a020", opacity=0.07, line_width=0, layer="below")
    trend.add_hrect(y0=cfg.alerts["score_red"], y1=100, fillcolor="#e5484d", opacity=0.07, line_width=0, layer="below")
    trend.add_scatter(x=mk.index, y=mk.rolling(4).mean(), name="市场宽松度（非 AI 专属）",
                      line=dict(width=1.6, dash="dot", color="#94a3b8"), hovertemplate="%{y:.0f}")
    trend.add_scatter(x=tot.index, y=tot.rolling(4).mean(), name="AI 泡沫温度", line=dict(width=2.8, color="#e5484d", shape="spline"),
                      fill="tozeroy", fillcolor="rgba(229,72,77,0.06)", hovertemplate="%{y:.0f}")
    trend.update_layout(height=340, margin=dict(l=0, r=8, t=8, b=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        font=dict(family=font, size=12, color="#475569"), hovermode="x unified",
                        legend=dict(orientation="h", y=1.02, yanchor="bottom", x=0, bgcolor="rgba(0,0,0,0)"),
                        yaxis=dict(range=[0, 100], gridcolor="#eef0f4", zeroline=False, tickvals=[0, 20, 40, 60, 80, 100]),
                        xaxis=dict(showgrid=False, linecolor="#e6e9ef"))

    dim_html = _dimension_section(res, cfg, "ai")
    market_html = _dimension_section(res, cfg, "market")
    mk_now = res.market.iloc[-1] if len(res.market) else float("nan")

    last = res.indicators.iloc[-1]
    ind_rows = []
    dim_order = list(cfg.dimensions)
    by_group = sorted(cfg.scored, key=lambda i: (list(GROUPS).index(cfg.dimensions[i.dimension].get("group", "ai")), dim_order.index(i.dimension)))
    for ind in by_group:
        s = series[ind.id]
        sc = last.get(ind.id)
        has = ind.id in last and pd.notna(sc)
        ind_rows.append(
            f"<tr><td><small>{GROUPS[cfg.dimensions[ind.dimension].get('group', 'ai')]}</small><br>{html.escape(cfg.dimensions[ind.dimension]['label'])}</td><td>{html.escape(ind.name)}</td>"
            f"<td class=n>{'—' if s.empty else f'{s.iloc[-1]:,.4g}'}</td><td class=n><small>{'—' if s.empty else s.index[-1].date()}</small></td>"
            f"<td style='white-space:nowrap'>{_bar(sc * 100 if has else 0)}{f'{sc:.0%}' if has else '—'}</td></tr>")

    week_news = news.recent(all_news, asof, 7)
    heat_df = news.weekly_heat(all_news, asof)
    rate_hist = {w: news.rating(all_news, assessments, w) for w in heat_df["week_end"].unique()}
    trigger_names = {t.id: t.name for t in cfg.triggers}
    note_md = news.latest_note()
    brief = (f"<div class=card id=brief><h2>分析师周报</h2><div class=sub>{note_md[0]} · AI 分析师阅读新闻后撰写</div><div class=prose>"
             f"{markdown.markdown(note_md[1], extensions=['tables'])}</div></div>") if note_md else ""

    past = "".join(f"<details><summary>{n.week.date()}｜{html.escape(n.headline)}</summary>{_note_html(n, False)}</details>"
                   for n in notes[1:])
    asof_day = tot.index[-1].date()

    return f"""<!doctype html><html lang=zh><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>AI 泡沫监测 · {latest:.0f}°</title><style>{CSS}</style></head><body>
<header class=top><div class=in><div class=brand><i></i>AI 泡沫监测</div>
<nav><a href=#overview>概览</a><a href=#brief>周报</a><a href=#trend>走势</a><a href=#signals>破裂信号</a><a href=#news>新闻</a><a href=#build>分数构成</a><a href=#note>数据解读</a><a href=#detail>指标明细</a></nav></div></header>
<main>
<div class=title id=overview><div><h1>AI 经济泡沫监测</h1><p>AI 这一轮有多热，泡沫有没有开始破。每个工作日用公开数据更新。</p></div>
<div class=stamp>数据截至 {asof_day}<br>指标覆盖率 {res.coverage.iloc[-1]:.0%}</div></div>

<section class=hero>
<div class="kpi main"><div class=eyebrow>AI 泡沫温度 (0-100)</div>
<div class=num><div class=big style='color:{COLORS[b]}'>{latest:.0f}</div><span class=pill style='background:{COLORS[b]}1f;color:{COLORS[b]}'>{LABELS[b]}</span></div>
<div><div class=scale><b style='left:{min(max(latest, 1), 99):.0f}%'></b></div><div class=ticks><span>0</span><span>60 升温</span><span>80 过热</span><span>100</span></div></div>
<div class=deltas>{_delta(d1, '较上周')}{_delta(d4, '较 4 周前')}</div></div>
<div class=kpi><div class=eyebrow>市场宽松度 · 大环境</div>
<div class=num><div class=mid>{mk_now:.0f}</div><span class=pill style='background:#eef1f6;color:#475569'>{_level_word(mk_now)}</span></div>
<div class="scale gray"><b style='left:{min(max(mk_now, 1), 99):.0f}%'></b></div>
<div class=note>信用、波动、利率。高 = 资金松、市场自满，泡沫更容易被吹大。</div></div>
<div class=kpi><div class=eyebrow>破裂信号 · {len(now)} 项</div><div class=counts>{count_cells}</div><div class=note>{signal_note}</div></div>
{_rating_html(rate)}
</section>

{brief}

<div class=card id=trend><h2>AI 泡沫温度走势</h2><div class=sub>{tot.index[0]:%Y} 年起，4 周均值。黄色和红色底色是升温区和过热区。</div>{_fig_html(trend, True, cdn)}
<p><small>AI 泡沫温度只用和 AI 直接相关的维度，从 ChatGPT 发布后开始计算；更早的读数衡量的是整个市场的风险偏好，不发布。
市场宽松度（虚线）由信用利差、VIX、利率构成，反映的是大环境：它高说明资金松、市场自满，泡沫更容易被吹大，也更经不起冲击。</small></p></div>

<div class=card id=signals><h2>破裂信号</h2>
<div class=sub>AI 泡沫温度衡量“有多热”；这里衡量“有没有开始破”。阈值见 config/indicators.yaml 的 triggers。</div>
<div class=tw><table><tr><th>状态</th><th>信号</th><th class=n>当前</th><th class=n>警戒 / 触发</th><th>上周</th><th>4 周前</th><th class=n>数据截至</th></tr>{''.join(rows)}</table></div></div>

<div class=card><h2>信号走势</h2><div class=sub>{tot.index[0]:%Y} 年起每周五一个点，最后一点是最新交易日，都只用当时已公布的数据；黄色底色 = 警戒区，红色 = 触发区，圆点 = 当前值。财报类信号季度更新，所以是台阶状。</div>
{signal_charts}</div>

<div class=card><h2>近 12 周状态</h2><div class=sub>每格一周，最右一格是最新交易日。鼠标悬停可看当时的数值。</div>
<div class=tw><table class=heat><tr><th></th>{heat_head}</tr>{''.join(heat_rows)}</table></div>
<div class=legend>{heat_legend}</div></div>

<div class=card id=news><h2>新闻热度</h2><div class=sub>近 8 周，按主题</div>{_heat_news_html(heat_df, rate_hist)}</div>
<div class=card><h2>近 7 天要闻</h2><div class=sub>{len(week_news)} 条，按重要性排序</div><div class=prose>{_news_html(week_news, trigger_names)}</div></div>

<div class=card id=build><h2>AI 泡沫温度是怎么来的</h2>{dim_html}
<p><small>维度分 = 该维度内各指标风险分位的平均 × 100；风险分位 = 指标在自身过去最多 15 年里的位置，越高越接近泡沫。贡献合计等于分数变化（有数据的维度数变化时会有小误差）。</small></p></div>
<div class=card><h2>市场宽松度是怎么来的</h2>{market_html}</div>

<div class=grid2 id=note>
<div class=card><h2>数据解读</h2><div class=sub>{week.date()} 这一周，自动生成</div>{_note_html(note)}</div>
<div class="card past"><h2>过往解读</h2><div class=sub>最近 {len(notes) - 1} 周，点开查看</div>{past}</div>
</div>

<div class=card id=detail><h2>评分指标明细</h2><div class=tw><table><tr><th>维度</th><th>指标</th><th class=n>最新值</th><th class=n>数据日期</th><th>风险分位</th></tr>{''.join(ind_rows)}</table></div></div>
<footer>风险分位 = 该指标在自身过去最多 15 年历史中的位置（方向已处理，越高越接近泡沫）。财报数据按季末后 35 天视为可见。本页仅供参考，不构成投资建议。生成于北京时间 {scoring.now():%Y-%m-%d %H:%M}。</footer>
</main></body></html>"""


def main():
    ap = argparse.ArgumentParser(description="生成独立的 HTML 看板")
    ap.add_argument("--out", default=str(ROOT / "data" / "dashboard.html"))
    ap.add_argument("--cdn", action="store_true", help="从 CDN 加载 plotly.js，文件从 5MB 降到约 0.3MB，适合上线")
    args = ap.parse_args()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(args.cdn), encoding="utf-8")
    print(f"已生成 {out}")


if __name__ == "__main__":
    main()
