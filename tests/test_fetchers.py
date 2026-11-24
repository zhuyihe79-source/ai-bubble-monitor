import pandas as pd
import pytest

from bubblemon import db
from bubblemon.fetchers import edgar, yahoo


def entry(start, end, val, filed="2024-01-01"):
    return {"start": start, "end": end, "val": val, "filed": filed}


def test_cumulative_to_quarterly():
    entries = [
        entry("2023-01-01", "2023-03-31", 10),
        entry("2023-01-01", "2023-06-30", 25),
        entry("2023-01-01", "2023-09-30", 45),
        entry("2023-01-01", "2023-12-31", 70),
    ]
    s = edgar.quarterly_from_cumulative(entries)
    assert s.tolist() == [10, 15, 20, 25]


def test_trailing_twelve_month_entries_are_ignored():
    # 亚马逊 10-Q 额外披露的滚动 12 个月，起点不是财年起点
    entries = [entry("2022-04-01", "2023-03-31", 999), entry("2023-01-01", "2023-03-31", 10)]
    assert edgar.quarterly_from_cumulative(entries).tolist() == [10]


def test_restated_value_uses_latest_filing():
    entries = [entry("2023-01-01", "2023-03-31", 10, "2023-05-01"), entry("2023-01-01", "2023-03-31", 12, "2024-05-01")]
    assert edgar.quarterly_from_cumulative(entries).tolist() == [12]


def test_calendar_quarter_alignment():
    s = pd.Series([1, 2, 3], index=pd.to_datetime(["2024-05-31", "2024-06-30", "2024-12-31"]))
    out = edgar.to_calendar_quarter(s)
    assert list(out.index) == list(pd.to_datetime(["2024-06-30", "2024-12-31"]))


def test_aggregate_only_uses_quarters_all_companies_report():
    idx = pd.date_range("2022-03-31", periods=8, freq="QE")
    a = pd.Series(1.0, index=idx)
    b = pd.Series(1.0, index=idx[:6])
    out = edgar.aggregate({"A": a, "B": b}, {}, "capex_ttm")
    assert out.index[-1] == idx[5] and out.iloc[-1] == 8.0


def test_same_quarter_tagged_with_two_end_dates_is_counted_once():
    # 英伟达 2010 财年二季度：后来的 10-K 把结束日标成 7/31，原始 10-Q 是 8/1，起点分组也不同
    entries = [
        entry("2010-02-01", "2010-05-02", 1000), entry("2010-02-01", "2010-08-01", 1800),
        entry("2010-02-01", "2010-10-31", 2650), entry("2010-05-03", "2010-07-31", 800), entry("2010-05-03", "2010-08-01", 800),
    ]
    s = edgar.quarterly_from_cumulative(entries)
    assert list(s.index) == list(pd.to_datetime(["2010-05-02", "2010-08-01", "2010-10-31"]))
    assert s.tolist() == [1000, 800, 850]


def test_price_to_sales_adjusts_splits_and_waits_for_the_filing():
    from bubblemon.fetchers import valuation
    shares = valuation.split_adjusted(
        pd.Series([100.0, 400.0], index=pd.to_datetime(["2023-12-31", "2024-12-31"])),
        pd.Series([4.0], index=pd.to_datetime(["2024-06-10"])))
    assert shares.tolist() == [400.0, 400.0]            # 拆股前申报的 100 股 = 今天的 400 股
    rev = pd.Series([10.0, 10, 10, 10, 30], index=pd.to_datetime(["2023-03-31", "2023-06-30", "2023-09-30", "2023-12-31", "2024-03-31"]))
    px = pd.Series(1.0, index=pd.date_range("2024-01-01", "2024-06-30"))
    ps = valuation.price_to_sales(px, shares, rev, lag_days=35)
    assert ps.index[0] == pd.Timestamp("2024-02-04")    # 12/31 的财报 35 天后才可见
    assert ps["2024-05-04"] == pytest.approx(400 / 40) and ps["2024-05-05"] == pytest.approx(400 / 60)
    gap = rev.drop(pd.Timestamp("2023-09-30"))          # 缺一个季度就不凑四季
    assert valuation.trailing_four_quarters(gap).empty


def test_yahoo_ratio_dev_is_deviation_from_own_average():
    idx = pd.date_range("2024-01-01", periods=4)
    data = {"A": pd.Series([1.0, 1, 1, 3], index=idx), "B": pd.Series([1.0] * 4, index=idx)}
    d = yahoo.compute("ratio_dev", {"num": "A", "den": "B", "window": 3}, load=data.__getitem__)
    assert d.tolist() == pytest.approx([0.0, 3 / (5 / 3) - 1])


def test_yahoo_ratio_and_ma_gap():
    idx = pd.date_range("2024-01-01", periods=5)
    data = {"A": pd.Series([2, 4, 6, 8, 10.0], index=idx), "B": pd.Series([1.0] * 5, index=idx)}
    r = yahoo.compute("ratio", {"num": "A", "den": "B"}, load=data.__getitem__)
    assert r.tolist() == [2, 4, 6, 8, 10]
    g = yahoo.compute("ma_gap", {"ticker": "A", "window": 5}, load=data.__getitem__)
    assert abs(g.iloc[-1] - (10 / 6 - 1)) < 1e-9


def test_upsert_is_idempotent_and_overwrites():
    con = db.connect(":memory:")
    s = pd.Series([1.0, 2.0], index=pd.to_datetime(["2024-01-01", "2024-01-02"]))
    db.upsert_observations(con, "x", "t", s)
    db.upsert_observations(con, "x", "t", pd.Series([5.0], index=pd.to_datetime(["2024-01-02"])))
    out = db.load_series(con, "x")
    assert out.tolist() == [1.0, 5.0]


def test_trends_combine_shares_scale_and_rescales_to_100():
    from bubblemon.fetchers import trends
    df = pd.DataFrame({"a": [10, 50, 20], "b": [10, 50, 0], "isPartial": [False] * 3})
    s = trends.combine(df, ["a", "b"])
    assert s.tolist() == [20.0, 100.0, 20.0]  # 相加后 100 = 两个词合计的最高周

def test_drop_unfinished_bar_during_session():
    s = pd.Series([1.0, 2.0], index=pd.to_datetime(["2026-11-20", "2026-11-23"]))
    intraday = pd.Timestamp("2026-11-23 11:00", tz="America/New_York")
    after_close = pd.Timestamp("2026-11-23 17:00", tz="America/New_York")
    premarket_next = pd.Timestamp("2026-11-24 08:00", tz="America/New_York")
    assert yahoo.drop_unfinished(s, intraday).index[-1] == pd.Timestamp("2026-11-20")
    assert yahoo.drop_unfinished(s, after_close).index[-1] == pd.Timestamp("2026-11-23")
    assert yahoo.drop_unfinished(s, premarket_next).index[-1] == pd.Timestamp("2026-11-23")
