import argparse
import html
from pathlib import Path

import markdown
import pandas as pd
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs, get_plotlyjs_version

from . import commentary, db, news, phase, scoring, triggers
from .registry import GROUPS, LAYERS, ROOT, load_config

COLORS = {"green": "#2fd08c", "yellow": "#f5a524", "red": "#ff5459"}
LABELS = {"green": "低", "yellow": "升温", "red": "过热"}
HEAT_WEEKS = 12

CSS = """
:root{--bg:#0b0e13;--card:#12161e;--ink:#e8eaf0;--ink2:#9aa3b2;--ink3:#5f6b7d;--line:#212836;--line2:#1a212e;--soft:#1a212e;
--red:#ff5459;--amber:#f5a524;--green:#2fd08c;--r:14px;color-scheme:dark;
--mono:ui-monospace,"SF Mono","JetBrains Mono","Roboto Mono",Menlo,Consolas,monospace;
--sh:0 1px 2px rgba(0,0,0,.35),0 14px 34px -18px rgba(0,0,0,.6)}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:76px}
body{margin:0;background:radial-gradient(1200px 480px at 50% -120px,#141b28 0%,var(--bg) 62%) var(--bg);color:var(--ink);font:14.5px/1.7 Inter,-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans CJK SC",sans-serif;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
a{color:#4c8dff;text-decoration:none}a:hover{text-decoration:underline}
small{color:var(--ink3);font-size:12.5px}b{font-weight:650}
.top{position:sticky;top:0;z-index:10;background:rgba(11,14,19,.82);backdrop-filter:saturate(180%) blur(14px);-webkit-backdrop-filter:saturate(180%) blur(14px);border-bottom:1px solid var(--line)}
.top .in{max-width:1200px;margin:0 auto;padding:0 28px;height:58px;display:flex;align-items:center;gap:30px}
.brand{font-weight:750;font-size:15.5px;letter-spacing:-.01em;white-space:nowrap;display:flex;align-items:center;gap:10px;color:var(--ink)}
.brand i{width:10px;height:10px;border-radius:3px;background:linear-gradient(135deg,#ff5459,#c81e2b);box-shadow:0 0 0 4px rgba(255,84,89,.14)}
.top nav{display:flex;gap:2px;overflow-x:auto;scrollbar-width:none}.top nav::-webkit-scrollbar{display:none}
.top nav a{color:var(--ink2);padding:6px 11px;border-radius:999px;font-size:13px;white-space:nowrap;transition:background .15s}
.top nav a:hover{background:var(--soft);color:var(--ink);text-decoration:none}
main{max-width:1200px;margin:0 auto;padding:34px 28px 64px}
.title{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap;margin-bottom:22px}
.title h1{font-size:30px;line-height:1.15;letter-spacing:-.025em;margin:0;font-weight:800;color:#f2f4f8}
.title p{margin:8px 0 0;color:var(--ink2);font-size:14px}
.stamp{color:var(--ink3);font-size:12.5px;text-align:right;line-height:1.6}
.hero{display:grid;grid-template-columns:1.25fr 1fr 1.15fr;gap:18px;margin-bottom:22px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:22px 24px;display:flex;flex-direction:column;gap:10px;min-width:0;box-shadow:var(--sh)}
.kpi.main{background:linear-gradient(165deg,var(--card) 45%,#1a1216)}
.eyebrow{font-size:11px;font-weight:700;color:var(--ink3);letter-spacing:.09em;text-transform:uppercase}
.num{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
.big{font-size:58px;font-weight:750;line-height:.95;letter-spacing:-.04em;font-variant-numeric:tabular-nums}
.mid{font-size:40px;font-weight:700;line-height:1;letter-spacing:-.03em;font-variant-numeric:tabular-nums}
.mid small{font-size:15px;font-weight:600;letter-spacing:0;margin-left:2px}
.big,.mid,.mval,.counts b,td.n{font-family:var(--mono)}
.pill{display:inline-flex;align-items:center;gap:6px;padding:3px 11px;border-radius:999px;font-size:12px;font-weight:650;white-space:nowrap}
.scale{position:relative;height:6px;border-radius:999px;margin-top:8px;background:linear-gradient(90deg,#164a37 0 60%,#5c430f 60% 80%,#6b1f24 80%)}
.scale.gray{background:#232b3a}
.scale b{position:absolute;top:-5px;width:4px;height:16px;border-radius:2px;background:#f2f4f8;transform:translateX(-50%);box-shadow:0 0 0 2.5px var(--card)}
.ticks{position:relative;height:18px;font-size:11px;color:var(--ink3);font-variant-numeric:tabular-nums}
.ticks span{position:absolute;top:2px;white-space:nowrap}.ticks span:nth-child(2){left:60%}.ticks span:nth-child(3){left:80%}.ticks span:last-child{right:0}
.deltas{display:flex;gap:14px;flex-wrap:wrap;font-size:12.5px;color:var(--ink2)}.deltas b{font-variant-numeric:tabular-nums}
.up{color:var(--red)}.down{color:var(--green)}.flat{color:var(--ink3)}
.counts{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.counts div{background:var(--soft);border-radius:12px;padding:10px 12px}
.counts b{display:block;font-size:23px;line-height:1.1;font-variant-numeric:tabular-nums}
.counts span{font-size:12px;color:var(--ink2)}
.seg{display:flex;gap:4px;margin-top:4px}.seg i{flex:1;height:9px;border-radius:4px;background:#232b3a}
.kpi .note{font-size:12px;color:var(--ink3);line-height:1.6}
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:24px 26px;margin-bottom:22px;min-width:0;box-shadow:var(--sh)}
.card>h2{font-size:17.5px;line-height:1.35;margin:0;letter-spacing:-.01em;font-weight:750;display:flex;align-items:center;gap:10px;color:var(--ink)}
.card>h2::before{content:"";width:4px;height:15px;border-radius:2px;background:var(--ink)}
.card>.sub{color:var(--ink3);font-size:12.5px;margin:6px 0 16px}
.card>h2+*:not(.sub){margin-top:16px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:22px;margin-bottom:22px;align-items:start}
.grid-news{display:grid;grid-template-columns:1.7fr 1fr;gap:22px;margin-bottom:22px;align-items:start}
.grid2>.card,.grid-news>.card{margin-bottom:0}
.sticky{position:sticky;top:78px}
.tw{overflow-x:auto;margin:0 -4px;padding:0 4px}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th{font-size:11px;font-weight:700;letter-spacing:.07em;text-transform:uppercase;color:var(--ink3);text-align:left;padding:10px 12px;border-bottom:2px solid var(--line);white-space:nowrap}
td{padding:13px 12px;border-bottom:1px solid var(--line2);vertical-align:top}
tbody tr:not(.lay):hover td{background:#161d29}
tr:last-child td{border-bottom:0}
.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
td.n>b,td.n b{font-size:14.5px}
.why{color:var(--ink3);font-size:12.5px;line-height:1.6;margin-top:3px}
.badge{display:inline-flex;align-items:center;gap:6px;padding:3px 10px;border-radius:999px;font-size:11.5px;font-weight:700;white-space:nowrap;letter-spacing:.01em}
.badge::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor}
.s-triggered{background:rgba(255,84,89,.14);color:#ff8a8e}.s-alert{background:rgba(245,165,36,.13);color:#ffb84d}
.s-ok{background:rgba(47,208,140,.12);color:#3fe0a0}.s-nodata{background:#1e2530;color:#7a8496}
.s-news{background:rgba(255,84,89,.14);color:#ff8a8e}
.bar{display:inline-block;width:84px;height:6px;background:#232b3a;border-radius:999px;vertical-align:middle;margin-right:8px;overflow:hidden}
.bar i{display:block;height:100%;border-radius:999px}
.headline{font-size:15.5px;font-weight:650;line-height:1.65;padding:14px 18px;background:#161b25;border-left:3px solid var(--red);border-radius:0 12px 12px 0;margin:16px 0 8px;color:var(--ink)}
.sec h3{font-size:13px;font-weight:700;margin:18px 0 6px;color:var(--ink)}
.sec ul{margin:0;padding-left:18px}.sec li{margin:4px 0;font-size:13.5px;line-height:1.65;color:var(--ink2)}
.heat{border-collapse:separate;border-spacing:3px;width:auto}
.heat td{padding:0;border:0;width:31px;height:25px;border-radius:6px}
.heat td.name{width:auto;padding:0 14px 0 0;font-size:12.5px;color:var(--ink2);white-space:nowrap;border-radius:0}
.heat th{font-size:11px;font-weight:600;padding:0 0 6px;border:0;text-align:center;color:var(--ink3);letter-spacing:0;text-transform:none}
.h-triggered{background:#ff5459}.h-alert{background:#f5a524}.h-ok{background:#1b4a39}.h-nodata{background:#1a212e}
.legend{display:flex;gap:14px;flex-wrap:wrap;margin-top:12px;font-size:12px;color:var(--ink2)}
.legend span{display:inline-flex;align-items:center;gap:6px}.legend i{width:12px;height:12px;border-radius:4px;display:inline-block}
.minis{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}
.mini{border:1px solid var(--line);border-radius:14px;padding:14px 16px 8px;min-width:0;background:var(--card);transition:border-color .15s}
.mini:hover{border-color:#2a3342}
.mhead{display:flex;justify-content:space-between;align-items:flex-start;gap:8px;font-size:13px;line-height:1.45;font-weight:600;color:var(--ink)}
.mval{font-size:20px;font-weight:700;font-variant-numeric:tabular-nums;margin:3px 0;letter-spacing:-.01em;color:#fff}.mval small{font-size:11.5px;font-weight:500;margin-left:4px;color:var(--ink3)}
@media(max-width:1000px){.minis{grid-template-columns:1fr 1fr}}@media(max-width:700px){.minis{grid-template-columns:1fr}}
.past details{border:1px solid var(--line);border-radius:12px;padding:12px 16px;margin-top:10px;transition:background .15s}
.past details:hover{background:#161b25}
.past details[open]{background:#161b25}
.past summary{cursor:pointer;font-weight:600;font-size:13.5px;line-height:1.55;list-style:none;color:var(--ink)}
.past summary::-webkit-details-marker{display:none}
.past summary::before{content:"›";display:inline-block;margin-right:8px;color:var(--ink3);transition:transform .15s}
.past details[open] summary::before{transform:rotate(90deg)}
.news{padding:16px 0;border-bottom:1px solid var(--line2)}.news:first-of-type{padding-top:4px}.news:last-child{border-bottom:0}
.news .meta{display:flex;gap:9px;align-items:center;flex-wrap:wrap;margin-bottom:7px}
.news a.t{display:block;font-weight:650;color:var(--ink);font-size:14.5px;line-height:1.55}
.news a.t:hover{color:#4c8dff;text-decoration:none}
.news .sum{color:var(--ink2);font-size:13.5px;margin-top:5px}
.news .imp{margin-top:8px;font-size:12.5px;color:var(--ink2);background:#161b25;border-left:2px solid #3a4557;border-radius:0 8px 8px 0;padding:8px 12px}
.stars{color:#f5a524;letter-spacing:1.5px;font-size:12px}.stars em{color:#2a3242;font-style:normal}
.tag{background:#1e2530;color:var(--ink2);border-radius:6px;padding:2px 8px;font-size:12px;font-weight:500}
.nheat{border-collapse:separate;border-spacing:3px}
.nheat td,.nheat th{text-align:center;border:0;padding:4px 2px;font-size:12px}
.nheat td{border-radius:6px;font-weight:650;font-variant-numeric:tabular-nums}
.nheat td:first-child{text-align:left;white-space:nowrap;padding-right:12px;font-weight:500;color:var(--ink2)}
.prose{max-width:none}
.prose h1{font-size:21px;line-height:1.45;letter-spacing:-.01em;margin:16px 0 12px;color:var(--ink)}
.prose h2{font-size:15.5px;margin:24px 0 8px;padding-top:18px;border-top:1px solid var(--line);color:var(--ink)}
.prose h3{font-size:14px;margin:16px 0 4px;color:var(--ink)}
.prose p,.prose li{font-size:14.5px;line-height:1.85;color:#c6ccd8}
.prose ul,.prose ol{padding-left:22px}.prose li{margin:5px 0}
.prose table{margin:12px 0}.prose th,.prose td{border-bottom:1px solid var(--line)}
.nalert{margin-top:10px;font-size:12.5px;display:flex;gap:6px;align-items:center;flex-wrap:wrap}.nalert a{color:#ff8a8e}
.lead{color:var(--ink2);margin:8px 0 16px;font-size:14px;line-height:1.75}.lead b{color:var(--ink)}
footer{color:var(--ink3);font-size:12px;line-height:1.75;margin-top:12px;text-align:center}
.phase{display:grid;grid-template-columns:1.5fr 1fr;gap:36px;align-items:start}
.pname{font-size:34px;font-weight:800;line-height:1.2;letter-spacing:-.025em;margin:8px 0 10px}
.pdesc{font-size:14.5px;margin:0 0 12px;line-height:1.8;color:var(--ink2)}
.basis{margin:6px 0 0;padding:0;list-style:none}
.basis li{font-size:13px;color:var(--ink2);line-height:1.75;padding:10px 0;border-top:1px solid var(--line2)}.basis li b{color:var(--ink)}
.mx{display:grid;grid-template-columns:auto 1fr 1fr;gap:6px;font-size:12px;color:var(--ink3)}
.mx .h{text-align:center;padding-bottom:2px;font-weight:600}
.mx .v{display:flex;align-items:center;padding-right:6px;white-space:nowrap;font-weight:600}
.mx .c{border:1px solid #2a3342;border-radius:12px;padding:18px 6px;text-align:center;font-weight:650;font-size:13.5px;color:#5f6b7d;background:#161b25}
.mx .c.on{color:#fff;border-color:transparent;box-shadow:0 6px 20px -6px rgba(0,0,0,.5)}
.layers{margin-top:18px;display:grid;grid-template-columns:1fr 1fr;gap:10px}
.layers>div{display:flex;justify-content:space-between;align-items:center;gap:8px;font-size:13px;font-weight:600;background:#161b25;border:1px solid var(--line2);border-radius:10px;padding:8px 12px;color:var(--ink)}
.layers .dot{display:inline-block;width:8px;height:8px;border-radius:3px;margin-right:8px;vertical-align:1px}
.layers small{margin-left:7px;font-weight:500;color:var(--ink3)}
.dimrow{display:grid;grid-template-columns:5.5em 1fr 2em;gap:10px;align-items:center;font-size:12.5px;color:var(--ink2);margin:5px 0}
.dimrow .bar{width:100%;margin:0}.dimrow b{text-align:right;color:var(--ink);font-variant-numeric:tabular-nums}
tr.lay td{font-size:12px;font-weight:700;letter-spacing:.05em;padding:9px 12px;border-bottom:1px solid var(--line);text-transform:uppercase;color:var(--ink)}
tr.lay small{font-weight:500;margin-left:10px;text-transform:none;letter-spacing:0;color:var(--ink3)}
tr.lay .badge{margin-left:10px}
.h3{font-size:15px;margin:26px 0 10px;font-weight:700;letter-spacing:-.01em;color:var(--ink)}.h3:first-of-type{margin-top:8px}
.callout{background:rgba(245,165,36,.08);border:1px solid rgba(245,165,36,.32);border-radius:12px;padding:12px 16px;font-size:13px;line-height:1.7;color:#ffb84d;margin:0 0 16px}
.method ul{margin:0;padding-left:20px;columns:2;column-gap:36px}.method li{margin:0 0 10px;font-size:13.5px;line-height:1.8;color:var(--ink2);break-inside:avoid}.method li b{color:var(--ink)}
@media(max-width:1000px){.phase{grid-template-columns:1fr;gap:24px}.method ul{columns:1}}
@media(max-width:1000px){.hero{grid-template-columns:1fr 1fr}.grid-news{grid-template-columns:1fr}.sticky{position:static}}
@media(max-width:700px){.hero,.grid2{grid-template-columns:1fr}main{padding:22px 16px 48px}.card{padding:20px 18px}
.big{font-size:50px}.pname{font-size:27px}.title h1{font-size:24px}.stamp{text-align:left}.top .in{padding:0 16px;gap:16px}.brand span{display:none}.layers{grid-template-columns:1fr}.pq{display:none}.big-t{min-width:560px}}
.big-t{min-width:700px}
"""


def _plotly_tag(cdn: bool) -> str:
    """plotly.js 放在 <head> 里加载一次。跟着某一张图加载的话，页面上排在它前面的图会画不出来。"""
    if cdn:
        return f"<script src='https://cdn.plot.ly/plotly-{get_plotlyjs_version()}.min.js' charset=utf-8></script>"
    return f"<script>{get_plotlyjs()}</script>"


def _fig_html(fig: go.Figure) -> str:
    return fig.to_html(full_html=False, include_plotlyjs=False, config={"displayModeBar": False, "responsive": True})


def _note_html(note: commentary.Note, with_headline: bool = True) -> str:
    parts = [f"<div class=headline>{html.escape(note.headline)}</div>"] if with_headline else []
    for title, items in note.sections:
        lis = "".join(f"<li>{html.escape(x)}</li>" for x in items)
        parts.append(f"<div class=sec><h3>{html.escape(title)}</h3><ul>{lis}</ul></div>")
    return "".join(parts)


DIR_CLASS = {"risk_up": "s-triggered", "risk_down": "s-ok", "neutral": "s-nodata"}
LAYER_COLOR = {"demand": "#4c8dff", "price": "#ff5459", "financing": "#a78bfa", "climate": "#8b94a7"}


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
            style = ("background:rgba(255,84,89,.16);color:#ff8a8e" if r.net > 0 else "background:rgba(47,208,140,.13);color:#3fe0a0" if r.net < 0
                     else "background:#1a212e;color:#7a8496")
            cells.append(f"<td style='{style}' title='净方向 {r.net:+d}'>{r['count'] or ''}</td>")
        rows.append(f"<tr><td>{label}</td>{''.join(cells)}</tr>")
    if rate_hist:
        cells = "".join(
            f"<td style='color:{LEVEL_COLOR.get(rate_hist[w].level, '#3d4b63')};font-size:13px'>{rate_hist[w].level or '—'}</td>"
            for w in weeks)
        rows.append(f"<tr><td><b>分析师评级</b></td>{cells}</tr>")
    return (f"<div class=tw><table class=nheat><tr><th></th>{head}</tr>{''.join(rows)}</table></div>"
            "<p><small>数字 = 重要性 ≥ 3 的新闻条数。红 = 风险上升的多于下降的，绿相反。每列为截至该日的 7 天。</small></p>")


LEVEL_COLOR = {1: "#23b26d", 2: "#5fd39a", 3: "#8b94a7", 4: "#f5a524", 5: "#ff5459"}


def _rating_html(r: news.Rating) -> str:
    if r.level is None:
        return ("<div class=kpi><div class=eyebrow>分析师风险评级</div><div class=mid style='color:#3d4b63'>—</div>"
                "<div class=note>近 7 天新闻不足</div></div>")
    rule = f"规则值 {r.rule_level}（近 7 天新闻净方向 {r.balance:+.2f}，权重 {r.weight:g}）"
    if r.forced:
        rule += "，因有重要性 5 的风险上升新闻抬到至少 4"
    if r.reason:
        adj = r.level - r.rule_level
        rule += f"；分析师{'维持' if adj == 0 else '上调' if adj > 0 else '下调'}{'' if adj == 0 else f' {abs(adj)} 级'}：{html.escape(r.reason)}"
    seg = "".join(f"<i style='background:{LEVEL_COLOR[r.level] if k <= r.level else '#232b3a'}'></i>" for k in range(1, 6))
    return (f"<div class=kpi><div class=eyebrow>分析师风险评级 · 新闻</div>"
            f"<div class=num><div class=mid style='color:{LEVEL_COLOR[r.level]}'>{r.level}<small>/5</small></div>"
            f"<span class=pill style='background:{LEVEL_COLOR[r.level]}1f;color:{LEVEL_COLOR[r.level]}'>{news.LEVELS[r.level]}</span></div>"
            f"<div class=seg>{seg}</div><div class=note>{r.asof.date()}，基于新闻，不计入温度。{rule}</div></div>")


def _level_word(v: float) -> str:
    return "历史高位" if v >= 80 else "偏高" if v >= 60 else "中等" if v >= 40 else "偏低"


def _bar(v: float) -> str:
    """v 是 0–100。"""
    color = "#ff5459" if v >= 80 else "#f5a524" if v >= 60 else "#5f6b7d"
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
POINT = {"triggered": "#ff5459", "alert": "#f5a524", "ok": "#2fd08c", "nodata": "#5f6b7d"}


def _signal_charts(series, cfg, states: dict, start: pd.Timestamp, end: pd.Timestamp) -> str:
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
        fig.add_hrect(y0=warn[0], y1=warn[1], fillcolor="#f5a524", opacity=0.13, line_width=0, layer="below")
        fig.add_hrect(y0=bad[0], y1=bad[1], fillcolor="#ff5459", opacity=0.13, line_width=0, layer="below")
        quarterly = cfg.indicator(t.series).publication_lag_days > 0
        fig.add_scatter(x=hist.index, y=hist.values, mode="lines", line=dict(color="#c9d5e8", width=1.8, shape="hv" if quarterly else "linear"),
                        hovertemplate=f"%{{x|%Y-%m-%d}}<br>%{{y:{TICK.get(t.unit, '.2f')}}}<extra></extra>")
        fig.add_scatter(x=[hist.index[-1]], y=[hist.iloc[-1]], mode="markers", hoverinfo="skip",
                        marker=dict(size=8, color=POINT[s.status], line=dict(color="#fff", width=2)))
        fig.update_layout(height=150, margin=dict(l=0, r=4, t=4, b=0), showlegend=False,
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          font=dict(family="Inter,-apple-system,'PingFang SC',sans-serif", size=10.5, color="#5f6b7d"),
                          xaxis=dict(showgrid=False, linecolor="#212836", tickformat="%y年%-m月", nticks=4),
                          yaxis=dict(range=[lo, hi], gridcolor="#1a212e", zeroline=False, tickformat=TICK.get(t.unit, ".2f"), nticks=4))
        cards.append(
            f"<div class=mini><div class=mhead><b>{html.escape(t.name)}</b>{_badge(s.status)}</div>"
            f"<div class=mval>{triggers.fmt(s.value, t.unit)} <small>警戒 {triggers.fmt_threshold(t.alert, t.unit)} · 触发 {triggers.fmt_threshold(t.trigger, t.unit)}</small></div>"
            f"{_fig_html(fig)}</div>")
    return f"<div class=minis>{''.join(cards)}</div>"


def _badge(status: str) -> str:
    return f"<span class='badge s-{status}'>{triggers.LABEL[status]}</span>"


def _delta(v: float, label: str) -> str:
    cls = "up" if v >= 0.5 else "down" if v <= -0.5 else "flat"
    return f"<span>{label} <b class={cls}>{v:+.0f}</b></span>"


def _pct_range(values: list[float]) -> str:
    lo, hi = min(values), max(values)
    return f"{abs(lo):.0%}" if round(lo, 2) == round(hi, 2) else f"{abs(hi):.0%}–{abs(lo):.0%}"


def _episode_summary(episodes: list, dd_trigger) -> str:
    """一句话：过去每次跌破这条线之后怎么样了。"""
    past = [e for e in episodes if not e.ongoing]
    if not past:
        return ""
    conf, unconf = [e for e in past if e.confirmed], [e for e in past if not e.confirmed]
    line = triggers.fmt_threshold(dd_trigger.trigger, dd_trigger.unit)
    txt = f"{past[0].start.year} 年以来 NVDA 跌破 {line} 共 {len(past)} 次（不含进行中的）。"
    if conf:
        txt += (f"其中 {len(conf)} 次前后三个季度内单季收入环比跌超 10%，这几次从跌破那天算又跌了 "
                f"{_pct_range([e.further for e in conf])}；")
    if unconf:
        worst = min(e.further for e in unconf)
        txt += (f"{len(unconf)} 次收入没有掉，" + ("跌破那几天就是低点。" if worst > -0.03 else
                f"跌破后最多再跌 {_pct_range([e.further for e in unconf])}。"))
    seen = [e for e in conf if not pd.isna(e.drop_at_confirm)]
    if seen:
        txt += (f"财报比股价慢：这 {len(seen)} 次等财报证实时，股价已经比高点低了 {_pct_range([e.drop_at_confirm for e in seen])}，"
                f"之后又跌了 {_pct_range([e.after_confirm for e in seen])}。")
    return txt


def _episodes_html(episodes: list, dd_trigger) -> str:
    if not episodes:
        return "<p><small>数据不足。</small></p>"
    line = triggers.fmt_threshold(dd_trigger.trigger, dd_trigger.unit)
    rows = []
    for e in episodes[::-1]:
        if e.confirmed:
            rev = f"<span class='badge s-triggered'>掉了</span> 截至 {e.demand_quarter.date()} 的财季环比 {e.demand_qoq:+.0%}"
            conf = ("—" if pd.isna(e.drop_at_confirm) else
                    f"{e.confirm_date.date()}：已比高点低 {abs(e.drop_at_confirm):.0%}，之后最多再跌 {abs(e.after_confirm):.0%}")
        elif e.ongoing:
            rev, conf = "<span class='badge s-nodata'>还不知道</span> 等之后三个季度的财报", "—"
        else:
            rev, conf = "<span class='badge s-ok'>没掉</span>", "—"
        rows.append(
            f"<tr><td><b>{e.start.date()}</b>{' <span class=tag>进行中</span>' if e.ongoing else ''}</td>"
            f"<td class=n>{e.max_drawdown:.0%}<br><small>{e.trough.date()}</small></td><td>{rev}</td>"
            f"<td class=n><b>{e.further:.0%}</b>{'<br><small>到目前为止</small>' if e.ongoing else ''}</td>"
            f"<td class=n>{'—' if pd.isna(e.after_12m) else f'{e.after_12m:+.0%}'}</td><td class=why>{conf}</td></tr>")
    return (f"<p class=lead>{_episode_summary(episodes, dd_trigger)}</p>"
            f"<div class=tw><table><tr><th>第一次跌破 {line}</th><th class=n>距高点最深</th><th>收入有没有跟着掉</th>"
            f"<th class=n>跌破后最多再跌</th><th class=n>跌破后 12 个月</th><th>财报证实需求转差那天</th></tr>{''.join(rows)}</table></div>"
            "<p><small>“收入跟着掉”= 跌破前后三个季度内，有一个财季的收入环比跌超 10%（和需求层的触发线一致）。"
            "样本很少，2010–2012 年英伟达还是 PC 显卡公司，这张表只用来说明两种结局差别有多大，不能当概率用。</small></p>")


def _span_text(spans: list, last: pd.Timestamp) -> str:
    out = []
    for a, b in spans:
        if b >= last:
            out.append(f"{a:%Y-%m} 至今")
        else:
            out.append(f"{a:%Y-%m}" if (a.year, a.month) == (b.year, b.month) else f"{a:%Y-%m} 至 {b:%Y-%m}")
    return "；".join(out) or "没有出现过"


def _track_html(track: dict, current: int, last: pd.Timestamp, start: pd.Timestamp) -> str:
    rows = []
    for p, r in track.items():
        name = f"<b style='color:{phase.PHASE_COLOR[p]}'>{phase.PHASES[p][0]}</b>" + (" <span class=tag>当前</span>" if p == current else "")
        ret = "—" if pd.isna(r["median_return"]) else f"{r['median_return']:+.0%}"
        worst = "—" if pd.isna(r["median_worst"]) else f"{r['median_worst']:.0%}"
        rows.append(f"<tr><td>{name}</td><td class=n>{r['share']:.0%}</td><td class=why>{_span_text(r['spans'], last)}</td>"
                    f"<td class=n>{ret}</td><td class=n>{worst}</td></tr>")
    return (f"<div class=tw><table><tr><th>阶段</th><th class=n>{start:%Y} 年以来占多少周</th><th>出现在什么时候</th>"
            f"<th class=n>之后半年 NVDA 涨跌（中位数）</th><th class=n>半年内最深跌到（中位数）</th></tr>{''.join(rows)}</table></div>"
            "<p><small>按现在的规则和当时已公布的数据逐周回算。每个阶段只来自两三段行情，同一段里相邻的周高度相关，"
            "这些数字只说明方向。能看出的是：最难受的是“价格回调”这一格；等到“破裂确认”，大部分跌幅已经发生。</small></p>")


def _phase_card(ph: int, layers: dict, now: dict, cfg, episodes: list, alerts: dict) -> str:
    name, desc = phase.PHASES[ph]
    color = phase.PHASE_COLOR[ph]

    def members(layer: str) -> str:
        return " · ".join(f"{html.escape(s.trigger.name)} <b>{triggers.fmt(s.value, s.trigger.unit)}</b>"
                          for s in now.values() if s.trigger.layer == layer and s.status != "nodata")

    def data_date(layer: str) -> str:
        days = [s.data_date for s in now.values() if s.trigger.layer == layer and s.data_date is not None]
        return f"{max(days).date()}" if days else "—"

    basis = [f"<li>{_badge(layers['price'])} <b>价格</b>：{members('price') or '无数据'}</li>",
             f"<li>{_badge(layers['demand'])} <b>需求</b>：{members('demand') or '无数据'}"
             f"<br><small>来自财报，最新一期截至 {data_date('demand')}；季末后约 35 天才更新</small></li>"]
    early = [x for t in cfg.triggers if t.layer == "demand" for x in alerts.get(t.id, [])]
    if early:
        links = "；".join(f"<a href='{html.escape(x.url, quote=True)}' target=_blank rel=noopener>{html.escape(x.title)}</a>" for x in early[:3])
        basis.append(f"<li><span class='badge s-news'>新闻预警</span> 财报出来之前，近 7 天有 {len(early)} 条指向需求转弱的重要新闻：{links}</li>")
    dd = now.get("nvda_drawdown")
    if dd is not None and dd.status == "triggered" and episodes:
        basis.append(f"<li>{_episode_summary(episodes, dd.trigger)} <a href=#analog>看每一次的明细</a></li>")

    def cell(p: int) -> str:
        on = f" on' style='background:{phase.PHASE_COLOR[p]}" if p == ph else ""
        return f"<div class='c{on}'>{phase.SHORT[p]}</div>"

    matrix = (f"<div class=mx><div></div><div class=h>需求没破</div><div class=h>需求已破</div>"
              f"<div class=v>价格没破</div>{cell(1)}{cell(3)}<div class=v>价格已破</div>{cell(2)}{cell(4)}</div>")
    role = {"demand": "定阶段", "price": "定阶段", "financing": "背景", "climate": "背景"}
    lay = "".join(f"<div><span><i class=dot style='background:{LAYER_COLOR[k]}'></i>{label}<small>{role[k]}</small></span>"
                  f"{_badge(layers[k])}</div>" for k, label in LAYERS.items())
    return (f"<section class='card phase' style='border-top:3px solid {color};background:linear-gradient(165deg,{color}14 0%,#12161e 55%)'>"
            f"<div><div class=eyebrow>当前阶段</div>"
            f"<div class=pname style='color:{color}'>{name}</div><p class=pdesc>{desc}</p><ul class=basis>{''.join(basis)}</ul></div>"
            f"<div>{matrix}<div class=layers>{lay}</div>"
            f"<div class=note style='margin-top:10px'>“破”= 该层有信号越过触发线。融资、情绪与利率不改变阶段，但它们越差，回调来了越疼。</div></div></section>")


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
    phase_by_week = {w: phase.phase_of(phase.layer_states({k: s.status for k, s in by_week[w].items()}, cfg)) for w in weeks}
    layers = phase.layer_states({k: s.status for k, s in now.items()}, cfg)
    ph = phase_by_week[day]

    # 回测：信号的历史频率、各阶段之后发生了什么、NVDA 每次深度回撤的结局
    bt_start = pd.Timestamp(cfg.scoring.get("backtest_start", "2016-01-01"))
    bt_weeks = pd.date_range(bt_start, day, freq="W-FRI")
    if day not in bt_weeks:
        bt_weeks = bt_weeks.append(pd.DatetimeIndex([day]))
    status_hist = triggers.history(series, cfg, bt_weeks)
    rates = triggers.base_rates(status_hist)
    track = phase.track_record(phase.history(status_hist, cfg)["phase"], series["nvda_price"])
    has_dd = any(t.id == "nvda_drawdown" for t in cfg.triggers)
    episodes = phase.drawdown_episodes(series["nvda_price"], series["nvda_revenue_q"], cfg) if has_dd else []

    all_news = news.load()
    assessments = news.load_assessments()
    # 评级按最近一个新闻文件的日期算：定时任务早上写文件，看板晚上发布时仍沿用当天的分析师判断
    news_day = max((x.file_date for x in all_news if x.file_date is not None and x.file_date <= asof), default=asof)
    rate = news.rating(all_news, assessments, news_day)
    alerts = news.signal_alerts(all_news, asof)

    rows = []
    for layer, label in LAYERS.items():
        members = sorted((s for s in now.values() if s.trigger.layer == layer), key=lambda s: triggers.SEVERITY[s.status])
        if not members:
            continue
        role = "和价格一起决定阶段" if layer == "demand" else "和需求一起决定阶段" if layer == "price" else "背景，不改变阶段"
        c = LAYER_COLOR[layer]
        rows.append(f"<tr class=lay><td colspan=8 style='background:{c}0a;box-shadow:inset 3px 0 0 {c}'>"
                    f"{label}层 {_badge(layers[layer])}<small>{role}</small></td></tr>")
        for s in members:
            t = s.trigger
            dd = "—" if s.data_date is None else str(s.data_date.date())
            na = "".join(f"<div class=nalert><span class='badge s-news'>新闻预警</span> "
                         f"<a href='{html.escape(x.url, quote=True)}' target=_blank rel=noopener>{html.escape(x.title)}</a>"
                         f" <small>{x.published.date()}</small></div>" for x in alerts.get(t.id, []))
            r = rates.get(t.id)
            freq = "—" if r is None else (f"<span title='{bt_start:%Y} 年以来有数据的 {r[1]} 周里，处于警戒或触发的比例'>{r[0]:.0%}</span>"
                                           + (f"<br><small>只有 {r[1]} 周</small>" if r[1] < 156 else ""))
            rows.append(
                f"<tr><td>{_badge(s.status)}</td><td><b>{html.escape(t.name)}</b><div class=why>{html.escape(t.why)}</div>{na}</td>"
                f"<td class=n><b>{triggers.fmt(s.value, t.unit)}</b></td>"
                f"<td class=n>{triggers.fmt_threshold(t.alert, t.unit)} / {triggers.fmt_threshold(t.trigger, t.unit)}</td>"
                f"<td class=pq>{_badge(prev[t.id].status)}</td><td class=pq>{_badge(month[t.id].status)}</td><td class=n>{freq}</td><td class=n><small>{dd}</small></td></tr>"
            )

    heat_head = "".join(f"<th>{w:%m/%d}</th>" for w in weeks)
    heat_rows = ["<tr><td class=name><b>阶段</b></td>" + "".join(
        f"<td style='background:{phase.PHASE_COLOR[phase_by_week[w]]}' title='{w.date()} {phase.PHASES[phase_by_week[w]][0]}'></td>"
        for w in weeks) + "</tr>"]
    for t in cfg.triggers:
        cells = "".join(
            f"<td class=h-{by_week[w][t.id].status} title='{w.date()} {by_week[w][t.id].label} {triggers.fmt(by_week[w][t.id].value, t.unit)}'></td>"
            for w in weeks)
        heat_rows.append(f"<tr><td class=name><small>{LAYERS[t.layer]}</small> {html.escape(t.name)}</td>{cells}</tr>")
    heat_legend = ("".join(f"<span><i class=h-{k}></i>{triggers.LABEL[k]}</span>" for k in ("triggered", "alert", "ok", "nodata"))
                   + "".join(f"<span><i style='background:{phase.PHASE_COLOR[p]}'></i>阶段：{phase.SHORT[p]}</span>" for p in phase.PHASES))

    mk = res.market[res.market.index >= tot.index[0]]
    signal_charts = _signal_charts(series, cfg, now, tot.index[0], day)
    font = "Inter,-apple-system,'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',sans-serif"
    ai_dims = [d for d in cfg.group_dims("ai") if d in res.dimensions]
    trend = go.Figure()
    trend.add_hrect(y0=cfg.alerts["score_yellow"], y1=cfg.alerts["score_red"], fillcolor="#f5a524", opacity=0.07, line_width=0, layer="below")
    trend.add_hrect(y0=cfg.alerts["score_red"], y1=100, fillcolor="#ff5459", opacity=0.07, line_width=0, layer="below")
    trend.add_scatter(x=mk.index, y=mk.rolling(4).mean(), name="市场宽松度（非 AI 专属）", visible="legendonly",
                      line=dict(width=1.6, dash="dot", color="#5f6b7d"), hovertemplate="%{y:.0f}")
    for d, c in zip(ai_dims, ("#4c8dff", "#f5a524")):
        s = res.dimensions[d][res.dimensions.index >= tot.index[0]]
        trend.add_scatter(x=s.index, y=s.rolling(4).mean(), name=cfg.dimensions[d]["label"], line=dict(width=1.5, color=c), hovertemplate="%{y:.0f}")
    trend.add_scatter(x=tot.index, y=tot.rolling(4).mean(), name="AI 泡沫温度", line=dict(width=3, color="#ff5459"), hovertemplate="%{y:.0f}")
    trend.update_layout(height=340, margin=dict(l=0, r=8, t=8, b=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        font=dict(family=font, size=12, color="#9aa3b2"), hovermode="x unified",
                        legend=dict(orientation="h", y=1.02, yanchor="bottom", x=0, bgcolor="rgba(0,0,0,0)"),
                        yaxis=dict(range=[0, 100], gridcolor="#1a212e", zeroline=False, tickvals=[0, 20, 40, 60, 80, 100]),
                        xaxis=dict(showgrid=False, linecolor="#212836", tickformat="%Y-%m"))

    dim_html = _dimension_section(res, cfg, "ai")
    market_html = _dimension_section(res, cfg, "market")
    mk_now = res.market.iloc[-1] if len(res.market) else float("nan")
    dim_rows = "".join(
        f"<div class=dimrow><span>{html.escape(cfg.dimensions[d]['label'])}</span>{_bar(v)}<b>{v:.0f}</b></div>"
        for d in ai_dims if pd.notna(v := res.dimensions[d].iloc[-1]))

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
    changed = cfg.scoring.get("method_changed")
    stale = (f"<div class=callout>这篇周报写于 {changed} 算法调整之前，里面引用的 AI 泡沫温度和破裂信号个数是旧口径，"
             f"和本页现在的数字对不上；新闻事实和判断不受影响。</div>") if note_md and changed and note_md[0] < str(changed) else ""
    if note_md:
        # 周报按北京时间早上写，当时能看到的是前一个美股交易日的数据
        seen = {s.trigger.id: s.status for s in triggers.evaluate(series, cfg, pd.Timestamp(note_md[0]) - pd.Timedelta(days=1))}
        note_ph = phase.phase_of(phase.layer_states(seen, cfg))
        if note_ph != ph:
            stale += (f"<div class=callout>这篇周报写于 {note_md[0]}，当时阶段是「{phase.SHORT[note_ph]}」；"
                      f"按 {tot.index[-1].date()} 的最新数据，阶段已变为「{phase.SHORT[ph]}」。周报里的数字是写作当时的，以本页上方为准。</div>")
    brief = (f"<div class=card id=brief><h2>分析师周报</h2><div class=sub>{note_md[0]} · AI 分析师阅读新闻后撰写</div>{stale}<div class=prose>"
             f"{markdown.markdown(note_md[1], extensions=['tables'])}</div></div>") if note_md else ""

    past = "".join(f"<details><summary>{n.week.date()}｜{html.escape(n.headline)}</summary>{_note_html(n, False)}</details>"
                   for n in notes[1:])
    asof_day = tot.index[-1].date()
    n_dir = {k: sum(x.direction == k for x in week_news) for k in news.DIRECTIONS}
    dd_trigger = now["nvda_drawdown"].trigger if has_dd else None
    analog = (f"<h3 class=h3>NVDA 每次跌破 {triggers.fmt_threshold(dd_trigger.trigger, dd_trigger.unit)} 之后</h3>"
              f"{_episodes_html(episodes, dd_trigger)}") if has_dd else ""

    return f"""<!doctype html><html lang=zh><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>AI 泡沫监测 · {phase.SHORT[ph]} · {latest:.0f}°</title><style>{CSS}</style>{_plotly_tag(cdn)}</head><body>
<header class=top><div class=in><div class=brand><i></i>AI 泡沫监测</div>
<nav><a href=#overview>概览</a><a href=#brief>周报</a><a href=#signals>破裂信号</a><a href=#analog>历史对照</a><a href=#trend>温度走势</a><a href=#news>新闻</a><a href=#build>分数构成</a><a href=#note>数据解读</a><a href=#detail>指标明细</a><a href=#method>方法与局限</a></nav></div></header>
<main>
<div class=title id=overview><div><h1>AI 经济泡沫监测</h1><p>先看处在哪个阶段，再看有多热。每个工作日用公开数据更新。</p></div>
<div class=stamp>数据截至 {asof_day}<br>指标覆盖率 {res.coverage.iloc[-1]:.0%}</div></div>

{_phase_card(ph, layers, now, cfg, episodes, alerts)}

<section class=hero>
<div class="kpi main"><div class=eyebrow>AI 泡沫温度 (0-100)</div>
<div class=num><div class=big style='color:{COLORS[b]}'>{latest:.0f}</div><span class=pill style='background:{COLORS[b]}1f;color:{COLORS[b]}'>{LABELS[b]}</span></div>
<div><div class=scale><b style='left:{min(max(latest, 1), 99):.0f}%'></b></div><div class=ticks><span>0</span><span>60 升温</span><span>80 过热</span><span></span></div></div>
<div class=deltas>{_delta(d1, '较上周')}{_delta(d4, '较 4 周前')}</div>
<div>{dim_rows}</div><div class=note>温度 = 这两项的平均。衡量“吹得多大”，不衡量“破没破”。</div></div>
<div class=kpi><div class=eyebrow>市场宽松度 · 大环境</div>
<div class=num><div class=mid>{mk_now:.0f}</div><span class=pill style='background:#1e2530;color:#9aa3b2'>{_level_word(mk_now)}</span></div>
<div class="scale gray"><b style='left:{min(max(mk_now, 1), 99):.0f}%'></b></div>
<div class=note>信用、波动、利率，不是 AI 专属。高 = 资金松、市场自满，泡沫更容易被吹大。</div>
<div class=note>破裂信号 {len(now)} 项：<b class=up>{counts['triggered']}</b> 触发 · <b style='color:#f5a524'>{counts['alert']}</b> 警戒 · <b class=down>{counts['ok']}</b> 正常{f" · {counts['nodata']} 无数据" if counts['nodata'] else ''}。个数只作参考，价格类信号总是一起亮。</div></div>
{_rating_html(rate)}
</section>

{brief}

<div class=card id=signals><h2>破裂信号</h2>
<div class=sub>按层看，不要数个数。“历史频率”= {bt_start:%Y} 年以来这个信号有多大比例的周处于警戒或触发：比例高说明这条线平时就常被越过。阈值见 config/indicators.yaml。</div>
<div class=tw><table class=big-t><tr><th>状态</th><th>信号</th><th class=n>当前</th><th class=n>警戒 / 触发</th><th class=pq>上周</th><th class=pq>4 周前</th><th class=n>历史频率</th><th class=n>数据截至</th></tr>{''.join(rows)}</table></div></div>

<div class=card id=analog><h2>历史对照</h2><div class=sub>同样的局面过去发生过几次，之后怎么样了。按当时已公布的数据回算。</div>
<h3 class=h3>四个阶段的历史记录</h3>{_track_html(track, ph, day, bt_start)}
{analog}</div>

<div class=card><h2>信号走势</h2><div class=sub>{tot.index[0]:%Y} 年起每周五一个点，最后一点是最新交易日，都只用当时已公布的数据；黄色底色 = 警戒区，红色 = 触发区，圆点 = 当前值。财报类信号季度更新，所以是台阶状。</div>
{signal_charts}</div>

<div class=card><h2>近 12 周状态</h2><div class=sub>每格一周，最右一格是最新交易日。鼠标悬停可看当时的数值。</div>
<div class=tw><table class=heat><tr><th></th>{heat_head}</tr>{''.join(heat_rows)}</table></div>
<div class=legend>{heat_legend}</div></div>

<div class=card id=trend><h2>AI 泡沫温度走势</h2><div class=sub>{tot.index[0]:%Y} 年起，4 周均值。红线是温度，蓝线和黄线是它的两个组成部分。黄色和红色底色是升温区和过热区。</div>{_fig_html(trend)}
<p><small>两条细线分开走的时候最值得看：价格与估值回落而投资强度不降，说明股价已经在消化，但投入的规模还没有调整。
点图例里的“市场宽松度”可以叠加大环境（信用利差、VIX、利率）。</small></p></div>

<div class=card id=news><h2>新闻热度</h2><div class=sub>近 8 周，按主题</div>{_heat_news_html(heat_df, rate_hist)}</div>
<div class=card><h2>近 7 天要闻</h2><div class=sub>{len(week_news)} 条，按重要性排序：风险上升 {n_dir['risk_up']} 条 · 风险下降 {n_dir['risk_down']} 条 · 中性 {n_dir['neutral']} 条</div><div class=prose>{_news_html(week_news, trigger_names)}</div></div>

<div class=card id=build><h2>AI 泡沫温度是怎么来的</h2>{dim_html}
<p><small>维度分 = 该维度内各指标风险分位的平均 × 100；风险分位 = 指标在自身过去最多 15 年里的位置，越高越接近泡沫。贡献合计等于分数变化（有数据的维度数变化时会有小误差）。</small></p></div>
<div class=card><h2>市场宽松度是怎么来的</h2>{market_html}</div>

<div class=grid2 id=note>
<div class=card><h2>数据解读</h2><div class=sub>{week.date()} 这一周，自动生成</div>{_note_html(note)}</div>
<div class="card past"><h2>过往解读</h2><div class=sub>最近 {len(notes) - 1} 周，点开查看</div>{past}</div>
</div>

<div class=card id=detail><h2>评分指标明细</h2><div class=tw><table><tr><th>维度</th><th>指标</th><th class=n>最新值</th><th class=n>数据日期</th><th>风险分位</th></tr>{''.join(ind_rows)}</table></div></div>

<div class="card method" id=method><h2>方法与局限</h2><div class=sub>这个看板能回答什么，不能回答什么</div><ul>
<li><b>阶段</b>只看两件事：价格层有没有信号触发、需求层有没有信号触发。这是对现状的分类，不是预测。它的用处是把“跌了很多”和“需求真的坏了”分开。</li>
<li><b>财报比股价慢一到两个季度。</b>需求层用的是已提交给 SEC 的季报，季末后约 35 天才更新。过去每次真的破裂，都是股价先跌、财报后证实。所以需求层显示“正常”不等于安全，要同时看新闻预警和分析师评级。</li>
<li><b>AI 泡沫温度</b>衡量吹得多大：价格相对收入和大盘走了多远，投资相对现金流有多重。它是各指标在自身 15 年历史里的分位，高不代表马上会破，也不能和 2000 年直接比。它不是择时工具。</li>
<li><b>破裂信号的阈值是人定的</b>，表里的“历史频率”用来校准：平时就常亮的信号（比如 NVDA 回撤 20%）单独出现不值得紧张。需求层的警戒线是按这一轮的高增速定的，在 2023 年以前属于常态，所以只有“触发”才改变阶段。</li>
<li><b>样本很少。</b>英伟达深度回撤 2010 年以来只有几次，云厂商有息负债只有 2 年数据，高收益债利差只有 3 年。历史对照说明的是方向，不是概率。</li>
<li><b>分析师评级只基于新闻</b>，而收录新闻本身偏向坏消息（见“近 7 天要闻”里上升和下降的条数）。评级高说明坏消息密集，不代表数据已经转差。</li>
<li>没有覆盖：未上市公司（OpenAI、Anthropic 等）的财务、表外和私募信贷融资、GPU 租金、企业端 AI 实际付费。这些只能靠新闻。</li>
</ul></div>
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
