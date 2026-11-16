import pandas as pd

from bubblemon import report, scoring
from bubblemon.registry import load_config


def test_dimension_section_flags_newly_entered_indicator_and_sums_contributions():
    cfg = load_config()
    idx = pd.date_range("2026-01-02", periods=20, freq="W-FRI")
    dims = pd.DataFrame({"valuation": 60.0, "capex": 80.0, "leverage": 90.0, "sentiment": 50.0}, index=idx)
    dims.loc[idx[-1], "valuation"] = 70.0
    inds = pd.DataFrame({"spy_rsp_ratio": 0.6, "baa_spread": 0.9}, index=idx)
    inds["vix"] = float("nan")
    inds.loc[idx[-1], "vix"] = 0.3
    total = dims.mean(axis=1)
    res = scoring.ScoreResult(inds, dims, total, pd.Series(1.0, index=idx))
    out = report._dimension_section(res, cfg)
    assert "<b>+2</b>" in out and "估值与集中度 推高 2.5" in out      # 4 个维度平均，+10 贡献 2.5 度
    assert "新加入 VIX 波动率指数（30%）" in out                      # 指标进出单独说明，不当作市场变化
    assert "暂无数据" in out
