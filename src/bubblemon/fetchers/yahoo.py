import pandas as pd
import yfinance as yf


def _close(ticker: str) -> pd.Series:
    df = yf.download(ticker, period="max", auto_adjust=True, progress=False)
    if df.empty:
        raise RuntimeError(f"yfinance 没有返回 {ticker} 的数据")
    close = df["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    close.index = pd.to_datetime(close.index).tz_localize(None)
    return close.dropna()


def compute(kind: str, params: dict, load=_close) -> pd.Series:
    if kind == "ratio":
        num, den = load(params["num"]), load(params["den"])
        return (num / den).dropna()
    if kind == "ma_gap":
        px = load(params["ticker"])
        ma = px.rolling(params["window"]).mean()
        return (px / ma - 1).dropna()
    if kind == "price":
        return load(params["ticker"])
    raise ValueError(f"未知 yahoo kind: {kind}")


def fetch(params: dict) -> pd.Series:
    return compute(params["kind"], params)
