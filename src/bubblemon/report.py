import argparse
import html
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from . import alerts, db, scoring
from .registry import ROOT, load_config

COLORS = {"green": "#2e9e5b", "yellow": "#e0a800", "red": "#d64545"}
LABELS = {"green": "低", "yellow": "升温", "red": "过热"}


def _fig_html(fig: go.Figure, first: bool, cdn: bool = False) -> str:
    if not first:
        return fig.to_html(full_html=False, include_plotlyjs=False)
    return fig.to_html(full_html=False, include_plotlyjs="cdn" if cdn else True)


def build(years: int = 10, cdn: bool = False) -> str:
    cfg = load_config()
    con = db.connect()
    series = {i.id: db.load_series(con, i.id) for i in cfg.indicators}
    res = scoring.compute(series, cfg)
    if res.total.empty:
        raise SystemExit("没有可用数据，请先运行 bubblemon-fetch")

    latest = res.total.iloc[-1]
    prev = res.total.iloc[-5] if len(res.total) > 5 else latest
    b = scoring.band(latest, cfg.alerts)
    cut = res.total.index[-1] - pd.DateOffset(years=years)

    trend = go.Figure(go.Scatter(x=res.total[res.total.index >= cut].index, y=res.total[res.total.index >= cut], name="总分"))
    trend.add_hline(y=cfg.alerts["score_yellow"], line_dash="dot", line_color=COLORS["yellow"])
    trend.add_hline(y=cfg.alerts["score_red"], line_dash="dot", line_color=COLORS["red"])
    trend.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10), yaxis=dict(range=[0, 100]))

    dims = res.dimensions.iloc[-1].dropna()
    labels = [cfg.dimensions[d]["label"] for d in dims.index]
    radar = go.Figure(go.Scatterpolar(r=list(dims.values) + [dims.values[0]], theta=labels + [labels[0]], fill="toself"))
    radar.update_layout(polar=dict(radialaxis=dict(range=[0, 100])), height=360, margin=dict(l=40, r=40, t=10, b=10))

    dim_trend = go.Figure()
    d = res.dimensions[res.dimensions.index >= cut]
    for col in d.columns:
        dim_trend.add_scatter(x=d.index, y=d[col], name=cfg.dimensions[col]["label"], mode="lines")
    dim_trend.update_layout(height=360, margin=dict(l=10, r=10, t=10, b=10), yaxis=dict(range=[0, 100]))

    last = res.indicators.iloc[-1]
    rows = []
    for ind in cfg.indicators:
        s = series[ind.id]
        sc = last.get(ind.id)
        has = ind.id in last and pd.notna(sc)
        pct = f"{sc:.0%}" if has else "—"
        width = f"{sc * 100:.0f}" if has else "0"
        val = "—" if s.empty else f"{s.iloc[-1]:,.4g}"
        dt = "—" if s.empty else str(s.index[-1].date())
        rows.append(
            f"<tr><td>{html.escape(cfg.dimensions[ind.dimension]['label'])}</td><td>{html.escape(ind.name)}</td>"
            f"<td class=n>{val}</td><td>{dt}</td>"
            f"<td><div class=bar><i style='width:{width}%'></i></div> {pct}</td></tr>"
        )

    msgs = alerts.evaluate(res, cfg)
    alert_html = "".join(f"<li>{html.escape(m)}</li>" for m in msgs) or "<li>没有触发告警</li>"

    return f"""<!doctype html><html lang=zh><head><meta charset=utf-8><title>AI 泡沫监测</title>
<style>
body{{font-family:-apple-system,Segoe UI,sans-serif;margin:0;background:#f5f6f8;color:#1c1f24}}
main{{max-width:1200px;margin:0 auto;padding:24px}}
.card{{background:#fff;border-radius:10px;padding:16px 20px;box-shadow:0 1px 3px #0001;margin-bottom:16px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
.hero{{display:flex;gap:32px;align-items:center}}
.score{{font-size:64px;font-weight:700;color:{COLORS[b]}}}
table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{padding:6px 8px;border-bottom:1px solid #eee;text-align:left}}
.n{{text-align:right;font-variant-numeric:tabular-nums}}
.bar{{display:inline-block;width:100px;height:8px;background:#e8eaee;border-radius:4px;vertical-align:middle}}
.bar i{{display:block;height:8px;background:{COLORS['yellow']};border-radius:4px}}
h2{{font-size:16px;margin:0 0 8px}}small{{color:#6b7280}}
</style></head><body><main>
<h1>AI 经济泡沫监测</h1>
<div class=card><div class=hero>
<div><div class=score>{latest:.0f}</div><small>泡沫温度 (0-100)</small></div>
<div><b style='color:{COLORS[b]};font-size:20px'>{LABELS[b]}</b><br>
<small>较 4 周前 {latest - prev:+.0f}｜截至 {res.total.index[-1].date()}｜指标覆盖率 {res.coverage.iloc[-1]:.0%}</small></div>
<ul>{alert_html}</ul></div></div>
<div class=card><h2>总分趋势（近 {years} 年）</h2>{_fig_html(trend, True, cdn)}</div>
<div class=grid>
<div class=card><h2>六个维度（当前）</h2>{_fig_html(radar, False)}</div>
<div class=card><h2>维度趋势</h2>{_fig_html(dim_trend, False)}</div></div>
<div class=card><h2>指标明细</h2><table><tr><th>维度</th><th>指标</th><th>最新值</th><th>数据日期</th><th>风险分位</th></tr>{''.join(rows)}</table></div>
<small>风险分位 = 该指标在自身过去最多 15 年历史中的位置（方向已处理，越高越接近泡沫）。生成于 {pd.Timestamp.now():%Y-%m-%d %H:%M}。</small>
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
