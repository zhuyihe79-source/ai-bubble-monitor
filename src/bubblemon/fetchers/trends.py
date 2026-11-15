import time

import pandas as pd
from pytrends.request import TrendReq


def fetch(params: dict) -> pd.Series:
    """Google Trends 周频热度（0-100，相对值）。接口常限流，失败会由调用方记录。"""
    kw = params["keyword"]
    # 不用 TrendReq 的 retries 参数：pytrends 4.9 与 urllib3 2.x 不兼容
    pt = TrendReq(hl="en-US", tz=0)
    df = pd.DataFrame()
    for attempt in range(3):
        try:
            pt.build_payload([kw], timeframe="today 5-y")
            df = pt.interest_over_time()
            break
        except Exception:
            if attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))
    if df.empty:
        raise RuntimeError("Google Trends 返回空数据")
    s = df[kw].astype(float)
    s.index = pd.to_datetime(s.index)
    return s
