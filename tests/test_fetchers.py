import pandas as pd

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
