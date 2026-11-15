import os
from functools import lru_cache

import pandas as pd
import requests

COMPANIES = {
    "MSFT": "0000789019",
    "GOOGL": "0001652044",
    "AMZN": "0001018724",
    "META": "0001326801",
    "ORCL": "0001341439",
}
NVDA_CIK = "0001045810"
CAPEX_CONCEPTS = [
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsToAcquireProductiveAssets",
    "PaymentsForCapitalImprovements",
]
OCF_CONCEPTS = [
    "NetCashProvidedByUsedInOperatingActivities",
    "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
]
REVENUE_CONCEPTS = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"]
# 甲骨文不用 LongTermDebt* 标签，而是 LongTermNotesAndLoans / NotesPayableCurrent。租赁负债不计入。
DEBT_NONCURRENT_CONCEPTS = ["LongTermDebtNoncurrent", "LongTermNotesAndLoans", "LongTermNotesPayable"]
DEBT_CURRENT_CONCEPTS = ["LongTermDebtCurrent", "NotesPayableCurrent", "DebtCurrent"]
URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"


def _headers() -> dict:
    # SEC 要求 User-Agent 带联系方式：export SEC_USER_AGENT="Your Name you@example.com"
    # 未配置的 Actions secret 会注入空字符串，所以用 or 而不是 get 的默认值
    ua = os.environ.get("SEC_USER_AGENT") or "ai-bubble-monitor research contact@example.com"
    return {"User-Agent": ua}


@lru_cache(maxsize=None)
def _gaap(cik: str) -> dict:
    resp = requests.get(URL.format(cik=cik), headers=_headers(), timeout=60)
    resp.raise_for_status()
    return resp.json()["facts"]["us-gaap"]


def _usd_entries(cik: str, concept: str) -> list[dict]:
    units = _gaap(cik).get(concept, {}).get("units", {}).get("USD") or []
    return [e for e in units if e.get("form") in ("10-Q", "10-K")]


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


def instant_values(entries: list[dict]) -> pd.Series:
    """资产负债表类时点数据：同一日期取最晚提交的版本。"""
    latest: dict[str, dict] = {}
    for e in entries:
        if "start" in e:
            continue
        if e["end"] not in latest or e["filed"] > latest[e["end"]]["filed"]:
            latest[e["end"]] = e
    return pd.Series({pd.Timestamp(k): v["val"] for k, v in latest.items()}, dtype=float).sort_index()


def _merge(cik: str, concepts: list[str], parse) -> pd.Series:
    merged = pd.Series(dtype=float)
    for concept in concepts:  # 公司会换用不同的 XBRL 标签，按优先级拼接各时期
        entries = _usd_entries(cik, concept)
        if parse is quarterly_from_cumulative:
            entries = [e for e in entries if "start" in e]
        if entries:
            merged = merged.combine_first(parse(entries))
    return merged.sort_index()


def _company_quarterly(cik: str, concepts: list[str]) -> pd.Series:
    s = _merge(cik, concepts, quarterly_from_cumulative)
    if s.empty:
        raise RuntimeError(f"CIK {cik} 找不到 {concepts}")
    return s


def _company_debt(cik: str) -> pd.Series:
    noncurrent = _merge(cik, DEBT_NONCURRENT_CONCEPTS, instant_values)
    current = _merge(cik, DEBT_CURRENT_CONCEPTS, instant_values)
    if noncurrent.empty:
        raise RuntimeError(f"CIK {cik} 找不到长期负债")
    return noncurrent.add(current.reindex(noncurrent.index).fillna(0.0))


def to_calendar_quarter(s: pd.Series) -> pd.Series:
    """各公司财年不同（MSFT 6 月、ORCL 5 月），按最近的日历季末对齐。"""
    idx = [pd.Timestamp(d) + pd.Timedelta(days=45) for d in s.index]
    q_end = pd.PeriodIndex(idx, freq="Q").asfreq("Q", "end").to_timestamp(how="end").normalize()
    # 上一步把日期推后 45 天再取季末，会落到下一个季度，这里退回一个季度
    q_end = (q_end - pd.offsets.QuarterEnd(1)).normalize()
    out = pd.Series(s.values, index=q_end)
    return out[~out.index.duplicated(keep="last")]


def sum_aligned(by_company: dict[str, pd.Series]) -> pd.Series:
    """按日历季度对齐后求和，只保留所有公司都有数据的季度。"""
    df = pd.DataFrame({k: to_calendar_quarter(v) for k, v in by_company.items()}).dropna()
    return df.sum(axis=1)


def aggregate(capex: dict[str, pd.Series], ocf: dict[str, pd.Series], metric: str) -> pd.Series:
    cap_q = sum_aligned(capex)
    if metric == "capex_q":
        return cap_q
    cap_ttm = cap_q.rolling(4).sum().dropna()
    if metric == "capex_ttm":
        return cap_ttm
    if metric == "capex_to_ocf":
        o_ttm = sum_aligned(ocf).rolling(4).sum().dropna()
        return (cap_ttm / o_ttm).dropna()
    raise ValueError(f"未知 edgar metric: {metric}")


def fetch(params: dict) -> pd.Series:
    metric = params["metric"]
    if metric == "nvda_revenue_q":
        return _company_quarterly(NVDA_CIK, REVENUE_CONCEPTS)
    if metric == "debt_total":
        return sum_aligned({t: _company_debt(c) for t, c in COMPANIES.items()})
    capex = {t: _company_quarterly(c, CAPEX_CONCEPTS) for t, c in COMPANIES.items()}
    ocf = {t: _company_quarterly(c, OCF_CONCEPTS) for t, c in COMPANIES.items()} if metric == "capex_to_ocf" else {}
    return aggregate(capex, ocf, metric)
