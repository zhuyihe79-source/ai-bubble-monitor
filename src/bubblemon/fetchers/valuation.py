"""市销率 = 市值 / 近四季收入。价格来自 Yahoo，股数和收入来自 SEC 申报。"""
import pandas as pd
import yfinance as yf

from . import edgar, yahoo


def split_adjusted(shares: pd.Series, splits: pd.Series) -> pd.Series:
    """申报里的股数是当时的口径，Yahoo 的历史价格已按拆股调整；把股数换算成今天的口径才能相乘。"""
    out = shares.sort_index().astype(float).copy()
    for day, ratio in splits.items():
        out[out.index < day] *= ratio
    return out


def trailing_four_quarters(quarterly: pd.Series) -> pd.Series:
    q = quarterly.sort_index()
    span = (q.index.to_series() - q.index.to_series().shift(3)).dt.days
    return q.rolling(4).sum()[span <= 300].dropna()  # 中间缺季度时不凑数


def price_to_sales(price: pd.Series, shares: pd.Series, revenue_q: pd.Series, lag_days: int) -> pd.Series:
    ttm = trailing_four_quarters(revenue_q)
    ttm.index = ttm.index + pd.Timedelta(days=lag_days)  # 财报公布后才知道收入
    df = pd.DataFrame({"px": price.sort_index()})
    df["shares"] = shares.sort_index().reindex(df.index, method="ffill")
    df["ttm"] = ttm.reindex(df.index, method="ffill")
    return (df["px"] * df["shares"] / df["ttm"]).dropna()


def _splits(ticker: str) -> pd.Series:
    s = yf.Ticker(ticker).splits
    s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
    return s


def fetch(params: dict) -> pd.Series:
    ticker, cik = params["ticker"], params["cik"]
    shares = split_adjusted(edgar.shares_outstanding(cik), _splits(ticker))
    revenue = edgar._company_quarterly(cik, edgar.REVENUE_CONCEPTS)
    return price_to_sales(yahoo._close(ticker, dividends=False), shares, revenue, params.get("lag_days", 35))
