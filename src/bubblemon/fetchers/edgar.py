import os

import pandas as pd
import requests

COMPANIES = {
    "MSFT": "0000789019",
    "GOOGL": "0001652044",
    "AMZN": "0001018724",
    "META": "0001326801",
    "ORCL": "0001341439",
}
CAPEX_CONCEPTS = [
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsToAcquireProductiveAssets",
    "PaymentsForCapitalImprovements",
]
OCF_CONCEPTS = [
    "NetCashProvidedByUsedInOperatingActivities",
    "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
]
URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"


def _headers() -> dict:
    # SEC 要求 User-Agent 带联系方式：export SEC_USER_AGENT="Your Name you@example.com"
    ua = os.environ.get("SEC_USER_AGENT", "ai-bubble-monitor research contact@example.com")
    return {"User-Agent": ua}


def quarterly_from_cumulative(entries: list[dict]) -> pd.Series:
    """把 10-Q/10-K 里的累计现金流（3/6/9/12 个月）拆成单季值，索引为季度结束日。

    同一财年起点的条目按结束日排序后逐个相减。起点条目必须是约 3 个月长，
    这样可以排除亚马逊 10-Q 里额外披露的滚动 12 个月数据。
    """
    latest: dict[tuple, dict] = {}
    for e in entries:
        key = (e["start"], e["end"])
        if key not in latest or e["filed"] > latest[key]["filed"]:
            latest[key] = e

    by_start: dict[str, list[dict]] = {}
    for e in latest.values():
        by_start.setdefault(e["start"], []).append(e)

    out = {}
    for start, items in by_start.items():
        items.sort(key=lambda e: e["end"])
        first_days = (pd.Timestamp(items[0]["end"]) - pd.Timestamp(start)).days
        if not 80 <= first_days <= 100:
            continue
        prev_val = 0.0
        for e in items:
            days = (pd.Timestamp(e["end"]) - pd.Timestamp(start)).days
            if days > 380:
                break
            out[pd.Timestamp(e["end"])] = e["val"] - prev_val
            prev_val = e["val"]
    return pd.Series(out, dtype=float).sort_index()


def _company_quarterly(cik: str, concepts: list[str]) -> pd.Series:
    resp = requests.get(URL.format(cik=cik), headers=_headers(), timeout=60)
    resp.raise_for_status()
    gaap = resp.json()["facts"]["us-gaap"]
    merged = pd.Series(dtype=float)
    for concept in concepts:  # 公司会换用不同的 XBRL 标签，按优先级拼接各时期
        units = gaap.get(concept, {}).get("units", {}).get("USD")
        if not units:
            continue
        entries = [e for e in units if "start" in e and e.get("form") in ("10-Q", "10-K")]
        merged = merged.combine_first(quarterly_from_cumulative(entries))
    if merged.empty:
        raise RuntimeError(f"CIK {cik} 找不到 {concepts}")
    return merged.sort_index()


def to_calendar_quarter(s: pd.Series) -> pd.Series:
    """各公司财年不同（MSFT 6 月、ORCL 5 月），按最近的日历季末对齐。"""
    idx = [pd.Timestamp(d) + pd.Timedelta(days=45) for d in s.index]
    q_end = pd.PeriodIndex(idx, freq="Q").asfreq("Q", "end").to_timestamp(how="end").normalize()
    # 上一步把日期推后 45 天再取季末，会落到下一个季度，这里退回一个季度
    q_end = (q_end - pd.offsets.QuarterEnd(1)).normalize()
    out = pd.Series(s.values, index=q_end)
    return out[~out.index.duplicated(keep="last")]


def aggregate(capex: dict[str, pd.Series], ocf: dict[str, pd.Series], metric: str) -> pd.Series:
    cap = pd.DataFrame({k: to_calendar_quarter(v) for k, v in capex.items()})
    cap = cap.dropna()  # 只保留所有公司都有数据的季度
    cap_ttm = cap.sum(axis=1).rolling(4).sum().dropna()
    if metric == "capex_ttm":
        return cap_ttm
    if metric == "capex_to_ocf":
        o = pd.DataFrame({k: to_calendar_quarter(v) for k, v in ocf.items()}).dropna()
        o_ttm = o.sum(axis=1).rolling(4).sum().dropna()
        return (cap_ttm / o_ttm).dropna()
    raise ValueError(f"未知 edgar metric: {metric}")


def fetch(params: dict) -> pd.Series:
    metric = params["metric"]
    capex = {t: _company_quarterly(c, CAPEX_CONCEPTS) for t, c in COMPANIES.items()}
    ocf = {t: _company_quarterly(c, OCF_CONCEPTS) for t, c in COMPANIES.items()} if metric == "capex_to_ocf" else {}
    return aggregate(capex, ocf, metric)
