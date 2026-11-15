import argparse
import html
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from . import commentary, db, scoring, triggers
from .registry import ROOT, load_config

COLORS = {"green": "#2e9e5b", "yellow": "#e0a800", "red": "#d64545"}
LABELS = {"green": "低", "yellow": "升温", "red": "过热"}
STATUS_COLOR = {"triggered": "#d64545", "alert": "#e0a800", "ok": "#2e9e5b", "nodata": "#c4c8cf"}
HEAT_WEEKS = 12

CSS = """
body{font-family:-apple-system,Segoe UI,"PingFang SC","Noto Sans CJK SC",sans-serif;margin:0;background:#f5f6f8;color:#1c1f24}
main{max-width:1200px;margin:0 auto;padding:24px}
.card{background:#fff;border-radius:10px;padding:16px 20px;box-shadow:0 1px 3px #0001;margin-bottom:16px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.hero{display:flex;gap:32px;align-items:center;flex-wrap:wrap}
.score{font-size:64px;font-weight:700;line-height:1}
.chips span{display:inline-block;padding:4px 10px;border-radius:12px;color:#fff;font-size:13px;margin-right:6px}
table{border-collapse:collapse;width:100%;font-size:13.5px}
td,th{padding:7px 8px;border-bottom:1px solid #eee;text-align:left;vertical-align:top}
th{color:#6b7280;font-weight:600}
.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.badge{display:inline-block;padding:2px 8px;border-radius:10px;color:#fff;font-size:12px;white-space:nowrap}
.why{color:#4b5563;font-size:12.5px}
.bar{display:inline-block;width:90px;height:8px;background:#e8eaee;border-radius:4px;vertical-align:middle}
.bar i{display:block;height:8px;background:#e0a800;border-radius:4px}
.headline{font-size:17px;font-weight:600;margin:4px 0 12px}
.sec h3{font-size:14px;margin:12px 0 4px;color:#374151}
.sec ul{margin:0;padding-left:20px}.sec li{margin:3px 0;font-size:14px;line-height:1.55}
.heat td{padding:0;border:2px solid #fff;height:22px;min-width:26px}
.heat td.name{padding:0 8px;font-size:13px;white-space:nowrap;min-width:auto}
.heat th{font-size:11px;font-weight:400;padding:2px}
details{border-top:1px solid #eee;padding:8px 0}summary{cursor:pointer;font-weight:600}
h2{font-size:16px;margin:0 0 8px}small{color:#6b7280}
@media(max-width:800px){.grid{grid-template-columns:1fr}}
"""


def _fig_html(fig: go.Figure, first: bool, cdn: bool = False) -> str:
    if not first:
        return fig.to_html(full_html=False, include_plotlyjs=False)
    return fig.to_html(full_html=False, include_plotlyjs="cdn" if cdn else True)


def _note_html(note: commentary.Note, with_headline: bool = True) -> str:
    parts = [f"<div class=headline>{html.escape(note.headline)}</div>"] if with_headline else []
    for title, items in note.sections:
        lis = "".join(f"<li>{html.escape(x)}</li>" for x in items)
        parts.append(f"<div class=sec><h3>{html.escape(title)}</h3><ul>{lis}</ul></div>")
    return "".join(parts)


def _badge(status: str) -> str:
    return f"<span class=badge style='background:{STATUS_COLOR[status]}'>{triggers.LABEL[status]}</span>"


def build(years: int = 10, cdn: bool = False, asof: pd.Timestamp | None = None) -> str:
    cfg = load_config()
    con = db.connect()
    series = {i.id: db.load_series(con, i.id) for i in cfg.indicators}
    asof = pd.Timestamp(asof or pd.Timestamp.today()).normalize()
    res = scoring.compute(series, cfg, asof)
    if res.total.empty:
        raise SystemExit("没有可用数据，请先运行 bubblemon-fetch")

    week = scoring.last_friday(asof)
    notes = commentary.history(series, cfg, res, asof, weeks=8)
    note = notes[0]
    latest = res.total.iloc[-1]
    b = scoring.band(latest, cfg.alerts)

    weeks = [week - pd.Timedelta(days=7 * k) for k in range(HEAT_WEEKS)][::-1]
    by_week = {w: {s.trigger.id: s for s in triggers.evaluate(series, cfg, w)} for w in weeks}
    now = by_week[week]
    prev, month = by_week[weeks[-2]], by_week[weeks[-5]]
    counts = {k: sum(s.status == k for s in now.values()) for k in ("triggered", "alert", "ok", "nodata")}
    chips = "".join(f"<span style='background:{STATUS_COLOR[k]}'>{triggers.LABEL[k]} {v}</span>" for k, v in counts.items() if v)

    rows = []
    for s in sorted(now.values(), key=lambda s: (triggers.SEVERITY[s.status], s.trigger.name)):
        t = s.trigger
        dd = "—" if s.data_date is None else str(s.data_date.date())
        rows.append(
            f"<tr><td>{_badge(s.status)}</td><td><b>{html.escape(t.name)}</b><div class=why>{html.escape(t.why)}</div></td>"
            f"<td class=n>{triggers.fmt(s.value, t.unit)}</td>"
            f"<td class=n>{triggers.fmt_threshold(t.alert, t.unit)} / {triggers.fmt_threshold(t.trigger, t.unit)}</td>"
            f"<td>{_badge(prev[t.id].status)}</td><td>{_badge(month[t.id].status)}</td><td class=n>{dd}</td></tr>"
        )

    heat_head = "".join(f"<th>{w:%m/%d}</th>" for w in weeks)
    heat_rows = []
    for t in cfg.triggers:
        cells = "".join(
            f"<td title='{w.date()} {by_week[w][t.id].label} {triggers.fmt(by_week[w][t.id].value, t.unit)}' "
            f"style='background:{STATUS_COLOR[by_week[w][t.id].status]}'></td>" for w in weeks)
        heat_rows.append(f"<tr><td class=name>{html.escape(t.name)}</td>{cells}</tr>")

    cut = res.total.index[-1] - pd.DateOffset(years=years)
    tot = res.total[res.total.index >= cut]
    trend = go.Figure(go.Scatter(x=tot.index, y=tot, name="总分"))
    trend.add_scatter(x=tot.index, y=tot.rolling(4).mean(), name="4 周均值", line=dict(width=3))
    trend.add_hline(y=cfg.alerts["score_yellow"], line_dash="dot", line_color=COLORS["yellow"])
    trend.add_hline(y=cfg.alerts["score_red"], line_dash="dot", line_color=COLORS["red"])
    trend.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10), yaxis=dict(range=[0, 100]),
                        legend=dict(orientation="h", y=1.08))

    dims = res.dimensions.iloc[-1].dropna()
    labels = [cfg.dimensions[d]["label"] for d in dims.index]
    radar = go.Figure(go.Scatterpolar(r=list(dims.values) + [dims.values[0]], theta=labels + [labels[0]], fill="toself"))
    radar.update_layout(polar=dict(radialaxis=dict(range=[0, 100])), height=340, margin=dict(l=40, r=40, t=10, b=10))

    dim_trend = go.Figure()
    d = res.dimensions[res.dimensions.index >= cut].rolling(4).mean()
    for col in d.columns:
        dim_trend.add_scatter(x=d.index, y=d[col], name=cfg.dimensions[col]["label"], mode="lines")
    dim_trend.update_layout(height=340, margin=dict(l=10, r=10, t=10, b=10), yaxis=dict(range=[0, 100]))

    last = res.indicators.iloc[-1]
    ind_rows = []
    for ind in cfg.scored:
        s = series[ind.id]
        sc = last.get(ind.id)
        has = ind.id in last and pd.notna(sc)
        ind_rows.append(
            f"<tr><td>{html.escape(cfg.dimensions[ind.dimension]['label'])}</td><td>{html.escape(ind.name)}</td>"
            f"<td class=n>{'—' if s.empty else f'{s.iloc[-1]:,.4g}'}</td><td>{'—' if s.empty else s.index[-1].date()}</td>"
            f"<td><div class=bar><i style='width:{sc * 100 if has else 0:.0f}%'></i></div> {f'{sc:.0%}' if has else '—'}</td></tr>")

    past = "".join(f"<details><summary>{n.week.date()}｜{html.escape(n.headline)}</summary>{_note_html(n, False)}</details>"
                   for n in notes[1:])

    return f"""<!doctype html><html lang=zh><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>AI 泡沫监测</title><style>{CSS}</style></head><body><main>
<h1>AI 经济泡沫监测</h1>
<div class=card><div class=hero>
<div><div class=score style='color:{COLORS[b]}'>{latest:.0f}</div><small>泡沫温度 (0-100)</small></div>
<div><b style='color:{COLORS[b]};font-size:20px'>{LABELS[b]}</b><br>
<small>截至 {res.total.index[-1].date()}｜评分指标覆盖率 {res.coverage.iloc[-1]:.0%}</small></div>
<div><small>破裂信号（{len(now)} 项）</small><div class=chips>{chips}</div></div>
</div></div>

<div class=card><h2>本周解读（{week.date()}）</h2>{_note_html(note)}</div>

<div class=card><h2>破裂信号</h2>
<small>泡沫温度衡量“有多热”；这里衡量“有没有开始破”。阈值见 config/indicators.yaml 的 triggers。</small>
<table><tr><th>状态</th><th>信号</th><th class=n>当前</th><th class=n>警戒 / 触发</th><th>上周</th><th>4 周前</th><th class=n>数据截至</th></tr>{''.join(rows)}</table></div>

<div class=card><h2>信号热力图（近 {HEAT_WEEKS} 周）</h2>
<table class=heat><tr><th></th>{heat_head}</tr>{''.join(heat_rows)}</table>
<small>鼠标悬停可看当周数值。</small></div>

<div class=card><h2>总分趋势（近 {years} 年）</h2>{_fig_html(trend, True, cdn)}</div>
<div class=grid>
<div class=card><h2>六个维度（当前）</h2>{_fig_html(radar, False)}</div>
<div class=card><h2>维度趋势（4 周均值）</h2>{_fig_html(dim_trend, False)}</div></div>
<div class=card><h2>评分指标明细</h2><table><tr><th>维度</th><th>指标</th><th class=n>最新值</th><th>数据日期</th><th>风险分位</th></tr>{''.join(ind_rows)}</table></div>
<div class=card><h2>过往解读</h2>{past}</div>
<small>风险分位 = 该指标在自身过去最多 15 年历史中的位置（方向已处理，越高越接近泡沫）。财报数据按季末后 35 天视为可见。生成于 {pd.Timestamp.now():%Y-%m-%d %H:%M}。</small>
</main></body></html>"""


def main():
    ap = argparse.ArgumentParser(description="生成独立的 HTML 看板")
    ap.add_argument("--out", default=str(ROOT / "data" / "dashboard.html"))
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--cdn", action="store_true", help="从 CDN 加载 plotly.js，文件从 5MB 降到约 0.3MB，适合上线")
    args = ap.parse_args()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(args.years, args.cdn), encoding="utf-8")
    print(f"已生成 {out}")


if __name__ == "__main__":
    main()
