import argparse
import html
from pathlib import Path

import markdown
import pandas as pd
import plotly.graph_objects as go

from . import commentary, db, news, scoring, triggers
from .registry import GROUPS, ROOT, load_config

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
.news{border-bottom:1px solid #eee;padding:10px 0}.news a{font-weight:600;color:#1f4fbf;text-decoration:none}
.news .meta{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:3px}
.stars{color:#e0a800;letter-spacing:1px;font-size:13px}
.tag{background:#eef1f6;color:#374151;border-radius:10px;padding:2px 8px;font-size:12px}
.nheat td,.nheat th{text-align:center}.nheat td:first-child{text-align:left;white-space:nowrap}
.brief h1{font-size:20px;margin:4px 0 10px}.brief h2{font-size:16px;margin:16px 0 6px}.brief h3{font-size:14px;margin:12px 0 4px}
.brief p,.brief li{font-size:14px;line-height:1.65}
.nalert{margin-top:4px;font-size:12.5px}.nalert a{color:#b42318;text-decoration:none}
.lvl{font-size:44px;font-weight:700;line-height:1}
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


DIR_COLOR = {"risk_up": "#d64545", "risk_down": "#2e9e5b", "neutral": "#8b93a1"}


def _news_html(items: list, trigger_names: dict) -> str:
    if not items:
        return "<p><small>最近 7 天还没有新闻数据（等待分析师定时任务运行）。</small></p>"
    rows = []
    for x in sorted(items, key=lambda x: (-x.importance, -x.published.value))[:25]:
        sig = f"<span class=tag>关联信号：{html.escape(trigger_names.get(x.signal, x.signal))}</span>" if x.signal else ""
        rows.append(
            f"<div class=news><div class=meta><span class=stars>{'★' * x.importance}{'☆' * (5 - x.importance)}</span>"
            f"<span class=tag>{news.TOPICS[x.topic]}</span>"
            f"<span class=badge style='background:{DIR_COLOR[x.direction]}'>{news.DIRECTIONS[x.direction]}</span>{sig}"
            f"<small>{html.escape(x.source)}｜{x.published.date()}</small></div>"
            f"<a href='{html.escape(x.url, quote=True)}' target=_blank rel=noopener>{html.escape(x.title)}</a>"
            f"<div>{html.escape(x.summary)}</div><div class=why>→ {html.escape(x.implication)}</div></div>")
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
            color = "#f3c4c4" if r.net > 0 else "#c9ead6" if r.net < 0 else "#f1f2f4"
            cells.append(f"<td class=n style='background:{color}' title='净方向 {r.net:+d}'>{r['count'] or ''}</td>")
        rows.append(f"<tr><td>{label}</td>{''.join(cells)}</tr>")
    if rate_hist:
        cells = "".join(
            f"<td class=n style='color:{LEVEL_COLOR.get(rate_hist[w].level, '#c4c8cf')};font-weight:700'>{rate_hist[w].level or '—'}</td>"
            for w in weeks)
        rows.append(f"<tr><td><b>分析师评级</b></td>{cells}</tr>")
    return (f"<table class=nheat><tr><th></th>{head}</tr>{''.join(rows)}</table>"
            "<small>数字 = 重要性 ≥ 3 的新闻条数；红色 = 风险上升的多于下降的，绿色相反。周期为截至该日的 7 天。</small>")


LEVEL_COLOR = {1: "#2e9e5b", 2: "#7fb685", 3: "#8b93a1", 4: "#e0a800", 5: "#d64545"}


def _rating_html(r: news.Rating) -> str:
    if r.level is None:
        return "<div><div class=lvl style='color:#c4c8cf'>—</div><small>分析师风险评级：近 7 天新闻不足</small></div>"
    rule = f"规则值 {r.rule_level}（近 7 天新闻净方向 {r.balance:+.2f}，权重 {r.weight:g}）"
    if r.forced:
        rule += "，因有重要性 5 的风险上升新闻抬到至少 4"
    if r.reason:
        adj = r.level - r.rule_level
        rule += f"；分析师{'维持' if adj == 0 else '上调' if adj > 0 else '下调'}{'' if adj == 0 else f' {abs(adj)} 级'}：{html.escape(r.reason)}"
    return (f"<div style='max-width:460px'><div class=lvl style='color:{LEVEL_COLOR[r.level]}'>{r.level}<small style='font-size:16px'>/5 "
            f"{news.LEVELS[r.level]}</small></div><small>分析师风险评级（{r.asof.date()}，基于新闻，不计入泡沫温度）<br>{rule}</small></div>")


def _level_word(v: float) -> str:
    return "历史高位" if v >= 80 else "偏高" if v >= 60 else "中等" if v >= 40 else "偏低"


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
        color = "#d64545" if dc >= 1 else "#2e9e5b" if dc <= -1 else "#6b7280"
        rows.append(
            f"<tr><td><b>{label}</b><div class=why>{desc}</div></td>"
            f"<td style='white-space:nowrap'><div class=bar><i style='width:{cur:.0f}%'></i></div> {cur:.0f} <small>{_level_word(cur)}</small></td>"
            f"<td class=n>{'—' if pd.isna(old) else f'{old:.0f}'} → {cur:.0f}</td>"
            f"<td class=n><b style='color:{color}'>{dc:+.1f}</b></td><td class=why>{driver}</td></tr>")
    moves.sort(key=lambda x: -abs(x[0]))
    top = "；".join(f"{name} {'推高' if v > 0 else '拉低'} {abs(v):.1f}" for v, name in moves[:3] if abs(v) >= 0.5) or "各维度变化都不大"
    n = int(dims.loc[end].notna().sum())
    head = (f"<p>{GROUPS[group]} {score.loc[end]:.0f} = {n} 个有数据维度的平均。和 3 个月前（{then.date()}，{score.loc[then]:.0f}）相比 "
            f"<b>{delta_total:+.0f}</b>，主要来自：{top}。</p>")
    return (head + "<table><tr><th>维度（在问什么）</th><th>当前分</th><th class=n>3 个月前 → 现在</th>"
            "<th class=n>对分数变化的贡献（度）</th><th>变化最大的指标（风险分位）</th></tr>" + "".join(rows) + "</table>")


def _badge(status: str) -> str:
    return f"<span class=badge style='background:{STATUS_COLOR[status]}'>{triggers.LABEL[status]}</span>"


def build(cdn: bool = False, asof: pd.Timestamp | None = None) -> str:
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

    all_news = news.load()
    assessments = news.load_assessments()
    # 评级按最近一个新闻文件的日期算：定时任务早上写文件，看板晚上发布时仍沿用当天的分析师判断
    news_day = max((x.file_date for x in all_news if x.file_date is not None and x.file_date <= asof), default=asof)
    rate = news.rating(all_news, assessments, news_day)
    alerts = news.signal_alerts(all_news, asof)
    if alerts:
        chips += f"<span style='background:#b42318'>新闻预警 {len(alerts)}</span>"

    rows = []
    for s in sorted(now.values(), key=lambda s: (triggers.SEVERITY[s.status], s.trigger.name)):
        t = s.trigger
        dd = "—" if s.data_date is None else str(s.data_date.date())
        na = "".join(f"<div class=nalert><span class=badge style='background:#b42318'>新闻预警</span> "
                     f"<a href='{html.escape(x.url, quote=True)}' target=_blank rel=noopener>{html.escape(x.title)}</a>"
                     f" <small>{x.published.date()}</small></div>" for x in alerts.get(t.id, []))
        rows.append(
            f"<tr><td>{_badge(s.status)}</td><td><b>{html.escape(t.name)}</b><div class=why>{html.escape(t.why)}</div>{na}</td>"
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

    tot = res.total
    mk = res.market[res.market.index >= tot.index[0]]
    trend = go.Figure(go.Scatter(x=tot.index, y=tot.rolling(4).mean(), name="AI 泡沫温度（4 周均值）", line=dict(width=3, color="#d64545")))
    trend.add_scatter(x=mk.index, y=mk.rolling(4).mean(), name="市场宽松度（4 周均值，非 AI 专属）",
                      line=dict(width=1.5, dash="dash", color="#8b93a1"))
    trend.add_hline(y=cfg.alerts["score_yellow"], line_dash="dot", line_color=COLORS["yellow"])
    trend.add_hline(y=cfg.alerts["score_red"], line_dash="dot", line_color=COLORS["red"])
    trend.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10), yaxis=dict(range=[0, 100]),
                        legend=dict(orientation="h", y=1.08))

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
            f"<tr><td>{GROUPS[cfg.dimensions[ind.dimension].get('group', 'ai')]}｜{html.escape(cfg.dimensions[ind.dimension]['label'])}</td><td>{html.escape(ind.name)}</td>"
            f"<td class=n>{'—' if s.empty else f'{s.iloc[-1]:,.4g}'}</td><td>{'—' if s.empty else s.index[-1].date()}</td>"
            f"<td><div class=bar><i style='width:{sc * 100 if has else 0:.0f}%'></i></div> {f'{sc:.0%}' if has else '—'}</td></tr>")

    week_news = news.recent(all_news, asof, 7)
    heat_df = news.weekly_heat(all_news, asof)
    rate_hist = {w: news.rating(all_news, assessments, w) for w in heat_df["week_end"].unique()}
    trigger_names = {t.id: t.name for t in cfg.triggers}
    note_md = news.latest_note()
    brief = (f"<div class=card><h2>分析师周报（{note_md[0]}）</h2><div class=brief>"
             f"{markdown.markdown(note_md[1], extensions=['tables'])}</div></div>") if note_md else ""

    past = "".join(f"<details><summary>{n.week.date()}｜{html.escape(n.headline)}</summary>{_note_html(n, False)}</details>"
                   for n in notes[1:])

    return f"""<!doctype html><html lang=zh><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>AI 泡沫监测</title><style>{CSS}</style></head><body><main>
<h1>AI 经济泡沫监测</h1>
<div class=card><div class=hero>
<div><div class=score style='color:{COLORS[b]}'>{latest:.0f}</div><small>AI 泡沫温度 (0-100)</small></div>
<div><b style='color:{COLORS[b]};font-size:20px'>{LABELS[b]}</b><br>
<small>截至 {res.total.index[-1].date()}｜指标覆盖率 {res.coverage.iloc[-1]:.0%}</small><br>
<small>市场宽松度 <b>{mk_now:.0f}</b>（信用、波动、利率；非 AI 专属）</small></div>
<div><small>破裂信号（{len(now)} 项）</small><div class=chips>{chips}</div></div>
{_rating_html(rate)}
</div></div>

{brief}
<div class=card><h2>近 7 天要闻（{len(week_news)} 条，按重要性排序）</h2>{_news_html(week_news, trigger_names)}</div>

<div class=card><h2>数据解读（{week.date()}）</h2>{_note_html(note)}</div>

<div class=card><h2>破裂信号</h2>
<small>AI 泡沫温度衡量“有多热”；这里衡量“有没有开始破”。阈值见 config/indicators.yaml 的 triggers。</small>
<table><tr><th>状态</th><th>信号</th><th class=n>当前</th><th class=n>警戒 / 触发</th><th>上周</th><th>4 周前</th><th class=n>数据截至</th></tr>{''.join(rows)}</table></div>

<div class=card><h2>信号热力图（近 {HEAT_WEEKS} 周）</h2>
<table class=heat><tr><th></th>{heat_head}</tr>{''.join(heat_rows)}</table>
<small>鼠标悬停可看当周数值。</small></div>

<div class=card><h2>新闻热度（近 8 周）</h2>{_heat_news_html(heat_df, rate_hist)}</div>

<div class=card><h2>AI 泡沫温度走势（{tot.index[0]:%Y} 年起）</h2>{_fig_html(trend, True, cdn)}
<small>AI 泡沫温度只用和 AI 直接相关的维度，从 ChatGPT 发布后开始计算；更早的读数衡量的是整个市场的风险偏好，不发布。
市场宽松度（虚线）由信用利差、VIX、利率构成，反映的是大环境：它高说明资金松、市场自满，泡沫更容易被吹大，也更经不起冲击。</small></div>
<div class=card><h2>AI 泡沫温度是怎么来的</h2>{dim_html}
<small>维度分 = 该维度内各指标风险分位的平均 × 100；风险分位 = 指标在自身过去最多 15 年里的位置，越高越接近泡沫。贡献合计等于分数变化（有数据的维度数变化时会有小误差）。</small></div>
<div class=card><h2>市场宽松度是怎么来的</h2>{market_html}</div>
<div class=card><h2>评分指标明细</h2><table><tr><th>维度</th><th>指标</th><th class=n>最新值</th><th>数据日期</th><th>风险分位</th></tr>{''.join(ind_rows)}</table></div>
<div class=card><h2>过往解读</h2>{past}</div>
<small>风险分位 = 该指标在自身过去最多 15 年历史中的位置（方向已处理，越高越接近泡沫）。财报数据按季末后 35 天视为可见。生成于 {pd.Timestamp.now():%Y-%m-%d %H:%M}。</small>
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
