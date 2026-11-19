import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from bubblemon import commentary, db, news, scoring, triggers
from bubblemon.registry import load_config

st.set_page_config(page_title="AI 泡沫监测", layout="wide")
cfg = load_config()
BAND_COLOR = {"green": "#2e9e5b", "yellow": "#e0a800", "red": "#d64545"}
BAND_LABEL = {"green": "低", "yellow": "升温", "red": "过热"}


@st.cache_data(ttl=3600)
def load():
    con = db.connect()
    series = {i.id: db.load_series(con, i.id) for i in cfg.indicators}
    log = con.execute(
        "SELECT indicator_id, max(fetched_at) AS last_fetch, "
        "bool_and(ok) FILTER (WHERE fetched_at = (SELECT max(f2.fetched_at) FROM fetch_log f2 WHERE f2.indicator_id = fetch_log.indicator_id)) AS last_ok "
        "FROM fetch_log GROUP BY indicator_id"
    ).df()
    return series, log


series, log = load()
day = scoring.data_day(series, cfg, pd.Timestamp.today())
result = scoring.compute(series, cfg, day)
st.title("AI 经济泡沫监测")

if result.total.empty:
    st.warning("数据库里还没有可用数据。先运行 `bubblemon-fetch`。")
    st.stop()

latest, prev = result.total.iloc[-1], result.total.iloc[-5] if len(result.total) > 5 else result.total.iloc[-1]
b = scoring.band(latest, cfg.alerts)

c1, c2, c3 = st.columns([1, 1, 2])
c1.metric("AI 泡沫温度 (0-100)", f"{latest:.0f}", f"{latest - prev:+.0f} vs 4 周前", delta_color="inverse")
if len(result.market):
    c1.caption(f"市场宽松度 {result.market.iloc[-1]:.0f}（信用、波动、利率；非 AI 专属）")
c2.markdown(f"### 状态：<span style='color:{BAND_COLOR[b]}'>{BAND_LABEL[b]}</span>", unsafe_allow_html=True)
c2.caption(f"截至 {result.total.index[-1].date()}，指标覆盖率 {result.coverage.iloc[-1]:.0%}")
all_news = news.load()
news_day = max((x.file_date for x in all_news if x.file_date is not None), default=pd.Timestamp.today().normalize())
rate = news.rating(all_news, news.load_assessments(), news_day)
alerts = news.signal_alerts(all_news, pd.Timestamp.today().normalize())
if rate.level is None:
    c2.caption("分析师风险评级：近 7 天新闻不足")
else:
    c2.markdown(f"**分析师风险评级 {rate.level}/5（{news.LEVELS[rate.level]}）**，规则值 {rate.rule_level}"
                + (f"；{rate.reason}" if rate.reason else ""))

states = triggers.evaluate(series, cfg, day)
before = {s.trigger.id: s for s in triggers.evaluate(series, cfg, day - pd.Timedelta(days=7))}
with c3:
    counts = {k: sum(s.status == k for s in states) for k in ("triggered", "alert", "ok", "nodata")}
    cols = st.columns(4)
    for col, (k, v) in zip(cols, counts.items()):
        col.metric(f"破裂信号·{triggers.LABEL[k]}", v)

notes = commentary.history(series, cfg, result, pd.Timestamp.today(), weeks=8)
st.subheader(f"本周解读（{notes[0].week.date()}）")
st.markdown(f"**{notes[0].headline}**")
left_n, right_n = st.columns(2)
for idx, (title, items) in enumerate(notes[0].sections):
    with (left_n if idx % 2 == 0 else right_n):
        st.markdown(f"**{title}**\n" + "\n".join(f"- {x}" for x in items))

st.subheader("破裂信号")
st.dataframe(
    pd.DataFrame([{
        "状态": s.label,
        "信号": s.trigger.name,
        "当前": triggers.fmt(s.value, s.trigger.unit),
        "警戒 / 触发": f"{triggers.fmt_threshold(s.trigger.alert, s.trigger.unit)} / {triggers.fmt_threshold(s.trigger.trigger, s.trigger.unit)}",
        "上周": before[s.trigger.id].label,
        "新闻预警": "；".join(x.title for x in alerts.get(s.trigger.id, [])),
        "数据截至": None if s.data_date is None else s.data_date.date(),
        "为什么重要": s.trigger.why,
    } for s in sorted(states, key=lambda s: triggers.SEVERITY[s.status])]),
    hide_index=True, width="stretch",
)
with st.expander("过往解读"):
    for n in notes[1:]:
        st.markdown(f"**{n.week.date()}**｜{n.headline}")
        for title, items in n.sections:
            st.markdown(f"*{title}*\n" + "\n".join(f"- {x}" for x in items))
st.subheader(f"AI 泡沫温度走势（{result.total.index[0]:%Y} 年起）")
st.caption("AI 泡沫温度只用和 AI 直接相关的维度，从 ChatGPT 发布后开始计算；虚线是市场宽松度（信用、波动、利率），反映大环境。")
cut = result.total.index[0]
mk = result.market[result.market.index >= cut]
fig = go.Figure(go.Scatter(x=result.total.index, y=result.total.rolling(4).mean(), name="AI 泡沫温度（4 周均值）"))
fig.add_scatter(x=mk.index, y=mk.rolling(4).mean(), name="市场宽松度（4 周均值）", line=dict(dash="dash"))
fig.add_hline(y=cfg.alerts["score_yellow"], line_dash="dot", line_color=BAND_COLOR["yellow"])
fig.add_hline(y=cfg.alerts["score_red"], line_dash="dot", line_color=BAND_COLOR["red"])
fig.update_layout(height=320, margin=dict(l=0, r=0, t=10, b=0), yaxis=dict(range=[0, 100]))
st.plotly_chart(fig, width="stretch")

left, right = st.columns(2)
with left:
    st.subheader("各维度（当前）")
    dims = result.dimensions.iloc[-1].dropna()
    labels = [cfg.dimensions[d]["label"] for d in dims.index]
    radar = go.Figure(go.Scatterpolar(r=list(dims.values) + [dims.values[0]], theta=labels + [labels[0]], fill="toself"))
    radar.update_layout(polar=dict(radialaxis=dict(range=[0, 100])), height=380, margin=dict(l=30, r=30, t=10, b=10))
    st.plotly_chart(radar, width="stretch")
    missing = [v["label"] for k, v in cfg.dimensions.items() if k not in dims.index]
    if missing:
        st.caption("暂无数据的维度：" + "、".join(missing))
with right:
    st.subheader("指标明细")
    rows = []
    last = result.indicators.iloc[-1]
    for ind in cfg.scored:
        s = series[ind.id]
        rows.append({
            "维度": cfg.dimensions[ind.dimension]["label"],
            "指标": ind.name,
            "最新值": None if s.empty else float(s.iloc[-1]),
            "数据日期": None if s.empty else s.index[-1].date(),
            "风险分位": None if ind.id not in last or pd.isna(last[ind.id]) else float(last[ind.id]),
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                 column_config={"风险分位": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.2f")})

st.subheader("单个指标历史")
pick = st.selectbox("指标", cfg.indicators, format_func=lambda i: i.name)
s = series[pick.id]
if s.empty:
    st.info("这个指标还没有数据（手工指标请在 data/manual/ 下录入）。")
else:
    st.line_chart(s[s.index >= cut])

with st.expander("数据源状态"):
    st.dataframe(log, hide_index=True, width="stretch")
