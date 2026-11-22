import numpy as np
import pandas as pd

from bubblemon import scoring
from bubblemon.registry import Config, Indicator, load_config


def make_ind(direction="high", lag=0, stale=10, dim="valuation", iid="x"):
    return Indicator(iid, iid, dim, "manual", direction, "daily", stale, lag, {})


def test_today_is_beijing_date_even_when_machine_is_utc(monkeypatch):
    # 07:41 北京时间 = 前一天 23:41 UTC；新闻文件按北京日期命名，必须算作同一天
    utc = pd.Timestamp("2026-11-21 23:41", tz="UTC")
    monkeypatch.setattr(pd.Timestamp, "now", classmethod(lambda cls, tz=None: utc.tz_convert(tz) if tz else utc.tz_localize(None)))
    assert scoring.today() == pd.Timestamp("2026-11-22")
    assert scoring.now() == pd.Timestamp("2026-11-22 07:41")


def test_config_loads_and_is_valid():
    cfg = load_config()
    assert len(cfg.indicators) >= 10
    assert all(i.dimension in cfg.dimensions for i in cfg.indicators)


def test_to_weekly_marks_stale_data_as_missing():
    idx = pd.date_range("2024-01-01", "2024-03-01", freq="D")
    s = pd.Series(1.0, index=idx)
    w = scoring.to_weekly(s, max_stale_days=10, asof=pd.Timestamp("2024-06-01"))
    assert w.loc["2024-03-01"] == 1.0
    assert np.isnan(w.loc["2024-05-31"])


def test_to_weekly_respects_publication_lag():
    s = pd.Series([1.0, 2.0], index=pd.to_datetime(["2024-03-31", "2024-06-30"]))
    w = scoring.to_weekly(s, 200, pd.Timestamp("2024-07-26"), lag_days=45)
    # 6/30 的数据要到 8/14 才公布，7/26 时看到的还是 3 月那条
    assert w.iloc[-1] == 1.0


def test_to_weekly_never_goes_past_asof():
    s = pd.Series(range(51), index=pd.date_range("2024-01-01", "2024-02-20"), dtype=float)
    w = scoring.to_weekly(s, 10, pd.Timestamp("2024-02-15"))
    # 周四：前面是各周五，最后一点是本周截至周四的值，不用到周四之后的数据
    assert list(w.index[-2:]) == [pd.Timestamp("2024-02-09"), pd.Timestamp("2024-02-15")]
    assert w.iloc[-1] == s["2024-02-15"] and w.iloc[-2] == s["2024-02-09"]


def test_data_day_is_latest_market_date_not_today():
    cfg = load_config()
    s = pd.Series(1.0, index=pd.date_range("2024-01-01", "2024-02-14"))
    assert scoring.data_day({"vix": s}, cfg, pd.Timestamp("2024-02-15")) == pd.Timestamp("2024-02-14")


def test_percentile_monotonic_series_is_extreme():
    idx = pd.date_range("2015-01-02", periods=500, freq="W-FRI")
    p = scoring.rolling_percentile(pd.Series(np.arange(500.0), index=idx))
    assert p.dropna().iloc[-1] == 1.0


def test_direction_low_inverts_score():
    idx = pd.date_range("2015-01-02", periods=500, freq="W-FRI")
    s = pd.Series(np.arange(500.0)[::-1], index=idx)  # 一路下降
    asof = idx[-1]
    hi = scoring.indicator_score(s, make_ind("high", stale=30), asof).dropna().iloc[-1]
    lo = scoring.indicator_score(s, make_ind("low", stale=30), asof).dropna().iloc[-1]
    assert hi == 0.0 and lo == 1.0


def test_total_requires_min_dimensions():
    idx = pd.date_range("2015-01-02", periods=300, freq="W-FRI")
    s = pd.Series(np.arange(300.0), index=idx)
    inds = [make_ind(stale=30, dim="valuation", iid="a"), make_ind(stale=30, dim="macro", iid="b")]
    dims = {"valuation": {"label": "v", "weight": 1.0}, "macro": {"label": "m", "weight": 1.0}}
    cfg = Config(dims, inds, {"score_yellow": 60, "score_red": 80}, {"min_dimensions": 3})
    r = scoring.compute({"a": s, "b": s}, cfg, asof=idx[-1])
    assert r.total.empty
    cfg2 = Config(dims, inds, cfg.alerts, {"min_dimensions": 2})
    r2 = scoring.compute({"a": s, "b": s}, cfg2, asof=idx[-1])
    assert r2.total.iloc[-1] == 100.0


def test_band():
    a = {"score_yellow": 60, "score_red": 80}
    assert [scoring.band(x, a) for x in (10, 60, 85)] == ["green", "yellow", "red"]


def test_ai_temperature_excludes_market_dims_and_starts_at_ai_start():
    idx = pd.date_range("2015-01-02", periods=500, freq="W-FRI")
    up = pd.Series(np.arange(500.0), index=idx)
    inds = [make_ind(stale=30, dim="valuation", iid="a"), make_ind(stale=30, dim="macro", iid="b", direction="low")]
    dims = {"valuation": {"label": "v", "weight": 1.0, "group": "ai"},
            "macro": {"label": "m", "weight": 1.0, "group": "market"}}
    cfg = Config(dims, inds, {"score_yellow": 60, "score_red": 80},
                 {"min_dimensions": 1, "market_min_dimensions": 1, "ai_start": "2023-01-01"})
    r = scoring.compute({"a": up, "b": up}, cfg, asof=idx[-1])
    assert r.total.index[0] >= pd.Timestamp("2023-01-01")
    assert r.total.iloc[-1] == 100.0          # 只有 a（一路上涨 → 100），不受 b 影响
    assert r.market.iloc[-1] == 0.0           # b 方向为 low，一路上涨 → 0
    assert r.market.index[0] < pd.Timestamp("2023-01-01")   # 市场宽松度保留长历史
