import numpy as np
import pandas as pd
import pytest

from bubblemon import commentary, scoring, triggers
from bubblemon.fetchers import edgar
from bubblemon.registry import Config, Indicator, Trigger, load_config


def trig(transform="level", direction="above", alert=1.0, trigger=2.0, days=0, unit="num", series="x", tol=10):
    return Trigger("t", "t", series, transform, direction, alert, trigger, unit, "why", days, tol)


def daily(values, start="2024-01-01"):
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq="D"), dtype=float)


def test_real_config_triggers_are_valid():
    cfg = load_config()
    assert len(cfg.triggers) >= 10
    assert all(cfg.indicator(t.series) for t in cfg.triggers)


@pytest.mark.parametrize("value,expected", [(0.5, "ok"), (1.0, "alert"), (1.9, "alert"), (2.0, "triggered"), (np.nan, "nodata")])
def test_classify_above_boundaries(value, expected):
    assert triggers.classify(value, trig()) == expected


@pytest.mark.parametrize("value,expected", [(0.1, "ok"), (0.0, "alert"), (-0.1, "triggered")])
def test_classify_below_boundaries(value, expected):
    assert triggers.classify(value, trig(direction="below", alert=0.0, trigger=-0.1)) == expected


def test_drawdown_uses_window_high():
    s = daily([100, 200, 150, 120])
    assert triggers.compute_value(s, trig("drawdown", days=365)) == pytest.approx(-0.4)
    # 高点在窗口之外就不算
    assert triggers.compute_value(s, trig("drawdown", days=2)) == pytest.approx(120 / 150 - 1)


def test_pct_change_and_diff_use_nearest_observation():
    q = pd.Series([100.0, 110.0, 121.0], index=pd.to_datetime(["2025-03-31", "2025-06-30", "2025-09-30"]))
    # 9/30 往前 91 天是 7/1，就近取 6/30
    assert triggers.compute_value(q, trig("pct_change", days=91)) == pytest.approx(0.1)
    assert triggers.compute_value(q, trig("diff", days=91)) == pytest.approx(11.0)
    # 往前一年没有数据 → 无法计算
    assert np.isnan(triggers.compute_value(q, trig("pct_change", days=365)))


def _cfg(ind: Indicator, t: Trigger) -> Config:
    return Config({"valuation": {"label": "v", "weight": 1.0}}, [ind], {"score_yellow": 60, "score_red": 80}, {}, [t])


def test_evaluate_respects_publication_lag():
    ind = Indicator("x", "x", "valuation", "manual", "high", "quarterly", 200, 35)
    s = pd.Series([1.0, 5.0], index=pd.to_datetime(["2025-06-30", "2025-09-30"]))
    cfg = _cfg(ind, trig())
    before = triggers.evaluate({"x": s}, cfg, pd.Timestamp("2025-10-31"))[0]   # 9/30 + 35 天 = 11/4
    after = triggers.evaluate({"x": s}, cfg, pd.Timestamp("2025-11-07"))[0]
    assert (before.value, before.status) == (1.0, "alert")
    assert (after.value, after.status) == (5.0, "triggered")


def test_evaluate_marks_stale_data_as_nodata():
    ind = Indicator("x", "x", "valuation", "manual", "high", "daily", 10)
    cfg = _cfg(ind, trig())
    assert triggers.evaluate({"x": daily([5.0] * 10)}, cfg, pd.Timestamp("2024-03-01"))[0].status == "nodata"
    assert triggers.evaluate({}, cfg, pd.Timestamp("2024-03-01"))[0].status == "nodata"


def test_config_rejects_threshold_order(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("""
dimensions: {valuation: {label: v, weight: 1}}
indicators:
  - {id: x, name: x, dimension: valuation, source: manual, direction: high, frequency: daily, max_stale_days: 10}
alerts: {score_yellow: 60, score_red: 80}
triggers:
  - {id: t, name: t, series: x, transform: level, direction: above, alert: 2, trigger: 1, unit: num, why: w}
""", encoding="utf-8")
    with pytest.raises(ValueError, match="更极端"):
        load_config(p)


def test_formatting():
    assert triggers.fmt(0.1234, "pct") == "+12.3%"
    assert triggers.fmt(0.5, "pp") == "+0.50 个百分点"
    assert triggers.fmt(np.nan, "num") == "—"
    assert triggers.fmt_threshold(-0.35, "pct") == "-35%"


def _scored_setup():
    idx = pd.date_range("2015-01-02", periods=400, freq="W-FRI")
    rng = np.random.default_rng(0)
    a = pd.Series(rng.normal(size=400).cumsum(), index=idx)
    b = pd.Series(rng.normal(size=400).cumsum(), index=idx)
    inds = [Indicator("a", "A", "valuation", "manual", "high", "weekly", 30),
            Indicator("b", "B", "macro", "manual", "low", "weekly", 30)]
    dims = {"valuation": {"label": "v", "weight": 2.0}, "macro": {"label": "m", "weight": 1.0}}
    cfg = Config(dims, inds, {"score_yellow": 60, "score_red": 80, "indicator_extreme_pct": 0.95}, {"min_dimensions": 1},
                 [Trigger("ta", "TA", "a", "level", "above", float(a.iloc[-1]) - 1, float(a.iloc[-1]) + 100, "num", "w")])
    return {"a": a, "b": b}, cfg, idx


def test_driver_contributions_add_up_to_total_change():
    series, cfg, idx = _scored_setup()
    res = scoring.compute(series, cfg, asof=idx[-1])
    week, prev = idx[-1], idx[-2]
    lines = commentary._drivers(res, cfg, week, prev, top=10)
    contribs = [float(x.split("拉动温度 ")[1]) for x in lines]
    assert sum(contribs) == pytest.approx(res.total[week] - res.total[prev], abs=0.1 * len(contribs) + 0.05)


def test_weekly_note_reports_status_change():
    series, cfg, idx = _scored_setup()
    res = scoring.compute(series, cfg, asof=idx[-1])
    a = series["a"].copy()
    a.iloc[-1] = a.iloc[-2] + 1000  # 最后一周突然越过触发线
    series = dict(series, a=a)
    note = commentary.weekly_note(series, cfg, res, idx[-1])
    changes = dict(note.sections)["信号状态变化"]
    assert any("TA" in c and "→ 触发" in c and "恶化" in c for c in changes)
    assert "1 项触发" in note.headline

def test_past_weekly_notes_use_that_weeks_extremes():
    series, cfg, idx = _scored_setup()
    res = scoring.compute(series, cfg, asof=idx[-1])
    inds = res.indicators.copy()
    inds.iloc[:, :] = 0.5
    inds.iloc[-1, 0] = 0.99  # 只有最后一周处于极端
    res = scoring.ScoreResult(inds, res.dimensions, res.total, res.coverage, res.market)
    now = dict(commentary.weekly_note(series, cfg, res, idx[-1]).sections)
    past = dict(commentary.weekly_note(series, cfg, res, idx[-3]).sections)
    assert "处于历史极端的评分指标" in now and "处于历史极端的评分指标" not in past


def test_edgar_instant_values_and_debt_sum():
    entries = [
        {"end": "2025-03-31", "val": 10, "filed": "2025-05-01"},
        {"end": "2025-03-31", "val": 11, "filed": "2026-05-01"},  # 后续申报修订
        {"end": "2025-06-30", "val": 12, "filed": "2025-08-01"},
        {"start": "2025-01-01", "end": "2025-06-30", "val": 999, "filed": "2025-08-01"},  # 区间数据应忽略
    ]
    assert edgar.instant_values(entries).tolist() == [11, 12]
    out = edgar.sum_aligned({"A": pd.Series([1.0, 2.0], index=pd.to_datetime(["2025-03-31", "2025-06-30"])),
                             "B": pd.Series([10.0], index=pd.to_datetime(["2025-05-31"]))})
    assert out.to_dict() == {pd.Timestamp("2025-06-30"): 12.0}
