import pandas as pd

from bubblemon import report, scoring
from bubblemon.registry import load_config


def test_dimension_section_flags_newly_entered_indicator_and_sums_contributions():
    cfg = load_config()
    idx = pd.date_range("2026-01-02", periods=20, freq="W-FRI")
    dims = pd.DataFrame({"valuation": 60.0, "capex": 80.0, "leverage": 90.0, "sentiment": 30.0}, index=idx)
    dims.loc[idx[-1], "valuation"] = 70.0
    inds = pd.DataFrame({"spy_rsp_ratio": 0.6, "baa_spread": 0.9}, index=idx)
    inds["hyperscaler_capex_yoy"] = float("nan")
    inds.loc[idx[-1], "hyperscaler_capex_yoy"] = 0.5
    total = dims[["valuation", "capex"]].mean(axis=1)
    market = dims[["leverage", "sentiment"]].mean(axis=1)
    res = scoring.ScoreResult(inds, dims, total, pd.Series(1.0, index=idx), market)
    ai = report._dimension_section(res, cfg, "ai")
    assert "AI 泡沫温度 75 = 2 个有数据维度" in ai and "估值与集中度 推高 5.0" in ai  # 2 个维度平均，+10 贡献 5 度
    assert "新加入 五大云厂商 capex 同比" in ai                                      # 指标进出单独说明
    assert "信用环境" not in ai                                                     # 市场维度不进 AI 温度
    mk = report._dimension_section(res, cfg, "market")
    assert "市场宽松度 60" in mk and "信用环境" in mk and "估值与集中度" not in mk
