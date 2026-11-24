import pandas as pd
import yfinance as yf


def _close(ticker: str, dividends: bool = True) -> pd.Series:
    """dividends=False 时只按拆股调整，不把分红折进历史价格（算市值要用这个）。"""
    df = yf.download(ticker, period="max", auto_adjust=dividends, progress=False)
    if df.empty:
        raise RuntimeError(f"yfinance 没有返回 {ticker} 的数据")
    close = df["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    close.index = pd.to_datetime(close.index).tz_localize(None)
    return drop_unfinished(close.dropna())


def drop_unfinished(close: pd.Series, now: pd.Timestamp | None = None) -> pd.Series:
    """盘中运行时 yfinance 把当天还没收盘的最新价当作日线收盘价，去掉这根未完成的 K 线。"""
    now = now if now is not None else pd.Timestamp.now(tz="America/New_York")
    today = now.tz_localize(None).normalize()
    if len(close) and close.index[-1] >= today and (now.hour, now.minute) < (16, 20):
        return close[close.index < today]
    return close


def compute(kind: str, params: dict, load=_close) -> pd.Series:
    if kind == "ratio":
        num, den = load(params["num"]), load(params["den"])
        return (num / den).dropna()
    if kind == "ratio_dev":
        # 比值相对自身滚动均值的偏离：长期上行的比值直接取分位会常年贴着 100
        ratio = (load(params["num"]) / load(params["den"])).dropna()
        return (ratio / ratio.rolling(params["window"]).mean() - 1).dropna()
    if kind == "ma_gap":
        px = load(params["ticker"])
        ma = px.rolling(params["window"]).mean()
        return (px / ma - 1).dropna()
    if kind == "price":
        return load(params["ticker"])
    raise ValueError(f"未知 yahoo kind: {kind}")


def fetch(params: dict) -> pd.Series:
    return compute(params["kind"], params)
