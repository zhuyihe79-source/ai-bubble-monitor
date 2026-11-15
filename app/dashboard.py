import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from bubblemon import alerts, db, scoring
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
result = scoring.compute(series, cfg)
st.title("AI 经济泡沫监测")

if result.total.empty:
    st.warning("数据库里还没有可用数据。先运行 `bubblemon-fetch`。")
    st.stop()

latest, prev = result.total.iloc[-1], result.total.iloc[-5] if len(result.total) > 5 else result.total.iloc[-1]
b = scoring.band(latest, cfg.alerts)

c1, c2, c3 = st.columns([1, 1, 2])
c1.metric("泡沫温度 (0-100)", f"{latest:.0f}", f"{latest - prev:+.0f} vs 4 周前", delta_color="inverse")
c2.markdown(f"### 状态：<span style='color:{BAND_COLOR[b]}'>{BAND_LABEL[b]}</span>", unsafe_allow_html=True)
c2.caption(f"截至 {result.total.index[-1].date()}，指标覆盖率 {result.coverage.iloc[-1]:.0%}")
with c3:
    msgs = alerts.evaluate(result, cfg)
    for m in msgs:
        st.warning(m)
    if not msgs:
        st.success("没有触发告警")

years = st.slider("显示最近几年", 1, 25, 10)
cut = result.total.index[-1] - pd.DateOffset(years=years)
fig = go.Figure(go.Scatter(x=result.total[result.total.index >= cut].index,
                           y=result.total[result.total.index >= cut], name="总分"))
fig.add_hline(y=cfg.alerts["score_yellow"], line_dash="dot", line_color=BAND_COLOR["yellow"])
fig.add_hline(y=cfg.alerts["score_red"], line_dash="dot", line_color=BAND_COLOR["red"])
fig.update_layout(height=320, margin=dict(l=0, r=0, t=10, b=0), yaxis=dict(range=[0, 100]))
st.plotly_chart(fig, width="stretch")

left, right = st.columns(2)
with left:
    st.subheader("六个维度")
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
    for ind in cfg.indicators:
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
