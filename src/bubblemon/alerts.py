import pandas as pd

from .registry import Config
from .scoring import ScoreResult, band


def evaluate(result: ScoreResult, cfg: Config) -> list[str]:
    msgs = []
    if result.total.empty:
        return ["没有可用的评分数据，请先运行采集"]
    latest = result.total.iloc[-1]
    prev = result.total.iloc[-5] if len(result.total) > 5 else latest
    b = band(latest, cfg.alerts)
    if b != "green":
        msgs.append(f"总分 {latest:.0f} 进入{'红色' if b == 'red' else '黄色'}区间")
    if band(prev, cfg.alerts) != b:
        msgs.append(f"总分区间相比 4 周前发生变化：{prev:.0f} → {latest:.0f}")
    names = {i.id: i.name for i in cfg.indicators}
    last_ind = result.indicators.iloc[-1].dropna()
    for iid, v in last_ind.items():
        if v >= cfg.alerts["indicator_extreme_pct"]:
            msgs.append(f"{names[iid]} 的泡沫风险分位达到 {v:.0%}（相对自身历史）")
    return msgs
