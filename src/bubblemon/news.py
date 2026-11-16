"""分析师（定时任务里的 AI）写入的新闻文件：news/YYYY-MM-DD.json。

本模块只负责读取、校验和汇总，不抓新闻。
"""
import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .registry import ROOT

NEWS_DIR = ROOT / "news"
NOTES_DIR = ROOT / "notes"

TOPICS = {
    "memory": "存储与供应链",
    "nvidia": "英伟达与芯片竞争",
    "financing": "融资与循环交易",
    "demand": "需求与电力",
}
DIRECTIONS = {"risk_up": "风险上升", "risk_down": "风险下降", "neutral": "中性"}
REQUIRED = ("published", "title", "source", "url", "topic", "importance", "direction", "summary", "implication")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class NewsItem:
    published: pd.Timestamp
    title: str
    source: str
    url: str
    topic: str
    importance: int
    direction: str
    summary: str
    implication: str
    signal: str | None = None
    file_date: pd.Timestamp | None = None


def validate(doc: dict, name: str, trigger_ids: set[str] | None = None) -> list[str]:
    errs = []
    if not isinstance(doc, dict) or not isinstance(doc.get("items"), list):
        return [f"{name}: 顶层必须是包含 items 列表的对象"]
    if not DATE_RE.match(str(doc.get("date", ""))):
        errs.append(f"{name}: date 必须是 YYYY-MM-DD")
    a = doc.get("assessment")
    if a is not None:
        if not isinstance(a, dict) or not isinstance(a.get("level"), int) or not 1 <= a["level"] <= 5:
            errs.append(f"{name}: assessment.level 必须是 1-5 的整数")
        elif not str(a.get("reason", "")).strip():
            errs.append(f"{name}: assessment.reason 不能为空")
    seen = set()
    for i, it in enumerate(doc["items"]):
        where = f"{name} items[{i}]"
        if not isinstance(it, dict):
            errs.append(f"{where}: 必须是对象")
            continue
        missing = [k for k in REQUIRED if not it.get(k) and it.get(k) != 0]
        if missing:
            errs.append(f"{where}: 缺少 {', '.join(missing)}")
            continue
        if not DATE_RE.match(str(it["published"])):
            errs.append(f"{where}: published 必须是 YYYY-MM-DD")
        if not str(it["url"]).startswith(("https://", "http://")):
            errs.append(f"{where}: url 必须是 http(s) 链接")
        if it["topic"] not in TOPICS:
            errs.append(f"{where}: topic 必须是 {list(TOPICS)} 之一")
        if it["direction"] not in DIRECTIONS:
            errs.append(f"{where}: direction 必须是 {list(DIRECTIONS)} 之一")
        if not isinstance(it["importance"], int) or not 1 <= it["importance"] <= 5:
            errs.append(f"{where}: importance 必须是 1-5 的整数")
        if it.get("signal") and trigger_ids is not None and it["signal"] not in trigger_ids:
            errs.append(f"{where}: signal {it['signal']} 不是已定义的触发器 id")
        if it["url"] in seen:
            errs.append(f"{where}: url 重复")
        seen.add(it["url"])
    return errs


def load(news_dir: Path = NEWS_DIR) -> list[NewsItem]:
    """读取所有新闻文件；同一链接出现在多天时保留最早那天的记录。"""
    items: dict[str, NewsItem] = {}
    for path in sorted(news_dir.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if validate(doc, path.name):
            continue  # 坏文件不进看板；bubblemon-news-check 会报出来
        for it in doc["items"]:
            if it["url"] in items:
                continue
            items[it["url"]] = NewsItem(
                published=pd.Timestamp(it["published"]), title=it["title"], source=it["source"], url=it["url"],
                topic=it["topic"], importance=it["importance"], direction=it["direction"],
                summary=it["summary"], implication=it["implication"], signal=it.get("signal") or None,
                file_date=pd.Timestamp(doc["date"]),
            )
    return sorted(items.values(), key=lambda x: (x.published, x.importance), reverse=True)


def recent(items: list[NewsItem], asof: pd.Timestamp, days: int = 7) -> list[NewsItem]:
    start = asof - pd.Timedelta(days=days)
    return [x for x in items if start < x.published <= asof]


def weekly_heat(items: list[NewsItem], asof: pd.Timestamp, weeks: int = 8) -> pd.DataFrame:
    """每个主题每周：重要性 >= 3 的新闻条数，以及“风险上升 - 风险下降”的净条数。"""
    end = asof.normalize()
    rows = []
    for k in range(weeks):
        w_end = end - pd.Timedelta(days=7 * k)
        w_items = [x for x in items if w_end - pd.Timedelta(days=7) < x.published <= w_end and x.importance >= 3]
        for topic in TOPICS:
            t_items = [x for x in w_items if x.topic == topic]
            rows.append({
                "week_end": w_end, "topic": topic, "count": len(t_items),
                "net": sum(x.direction == "risk_up" for x in t_items) - sum(x.direction == "risk_down" for x in t_items),
            })
    return pd.DataFrame(rows)


def latest_note(notes_dir: Path = NOTES_DIR) -> tuple[str, str] | None:
    files = sorted(p for p in notes_dir.glob("*.md") if DATE_RE.match(p.stem))
    if not files:
        return None
    return files[-1].stem, files[-1].read_text(encoding="utf-8")


# ---------- 分析师风险评级 ----------
# 规则：近 7 天新闻的“加权净方向”= Σ 权重×方向 / Σ 权重，落在 -1 到 +1。
# 用比例而不是总和，是为了不让“这周收录得多”本身推高评级。
WEIGHT = {1: 0.0, 2: 0.5, 3: 1.0, 4: 2.0, 5: 4.0}
SIGN = {"risk_up": 1, "risk_down": -1, "neutral": 0}
LEVELS = {1: "低", 2: "偏低", 3: "中性", 4: "偏高", 5: "高"}
BALANCE_CUTS = (-0.5, -0.15, 0.15, 0.5)   # 1 | 2 | 3 | 4 | 5
MIN_WEIGHT = 3.0                          # 近 7 天权重合计不到 3（约 3 条中等新闻）就不出评级
RATING_DAYS = 7
ALERT_MIN_IMPORTANCE = 4


@dataclass(frozen=True)
class Rating:
    asof: pd.Timestamp
    level: int | None          # 最终评级：有分析师判断就用它，否则用规则值
    rule_level: int | None
    balance: float | None
    weight: float
    forced: bool               # 规则值因为出现重要性 5 的风险上升新闻被抬到至少 4
    reason: str | None = None  # 分析师的理由（只有写了 assessment 才有）


def rule_rating(items: list[NewsItem], asof: pd.Timestamp, days: int = RATING_DAYS) -> tuple[int | None, float | None, float, bool]:
    window = recent(items, asof, days)
    weight = sum(WEIGHT[x.importance] for x in window)
    if weight < MIN_WEIGHT:
        return None, None, weight, False
    balance = sum(WEIGHT[x.importance] * SIGN[x.direction] for x in window) / weight
    level = 1 + sum(balance > c if c < 0 else balance >= c for c in BALANCE_CUTS)
    forced = level < 4 and any(x.importance == 5 and x.direction == "risk_up" for x in window)
    return (4 if forced else level), balance, weight, forced


def load_assessments(news_dir: Path = NEWS_DIR) -> dict[pd.Timestamp, tuple[int, str]]:
    out = {}
    for path in sorted(news_dir.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        a = doc.get("assessment")
        if not validate(doc, path.name) and a:
            out[pd.Timestamp(doc["date"])] = (a["level"], a["reason"])
    return out


def rating(items: list[NewsItem], assessments: dict, asof: pd.Timestamp) -> Rating:
    """asof 当天如果有分析师判断就用它（只能在规则值上下各调一级），否则用规则值。"""
    asof = pd.Timestamp(asof).normalize()
    rule, balance, weight, forced = rule_rating(items, asof)
    level, reason = rule, None
    if asof in assessments and rule is not None:
        a_level, reason = assessments[asof]
        level = max(rule - 1, min(rule + 1, a_level))
    return Rating(asof, level, rule, balance, weight, forced, reason)


def signal_alerts(items: list[NewsItem], asof: pd.Timestamp, days: int = RATING_DAYS) -> dict[str, list[NewsItem]]:
    """近 7 天内关联到某个破裂信号、重要性 >= 4、方向为风险上升的新闻。财报数据滞后时，用它提前提示。"""
    out: dict[str, list[NewsItem]] = {}
    for x in recent(items, asof, days):
        if x.signal and x.importance >= ALERT_MIN_IMPORTANCE and x.direction == "risk_up":
            out.setdefault(x.signal, []).append(x)
    return out


def main():
    from .registry import load_config

    ap = argparse.ArgumentParser(description="校验 news/*.json")
    ap.add_argument("files", nargs="*", help="默认校验 news/ 下全部文件")
    args = ap.parse_args()
    trigger_ids = {t.id for t in load_config().triggers}
    paths = [Path(f) for f in args.files] or sorted(NEWS_DIR.glob("*.json"))
    errs = []
    for p in paths:
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errs.append(f"{p.name}: 无法解析 JSON：{exc}")
            continue
        file_errs = validate(doc, p.name, trigger_ids)
        errs += file_errs
        a = doc.get("assessment")
        if a and not file_errs:
            rule = rule_rating(load(p.parent), pd.Timestamp(doc["date"]))[0]
            if rule is None:
                errs.append(f"{p.name}: 近 {RATING_DAYS} 天新闻不足，规则不出评级，不要写 assessment")
            elif abs(a["level"] - rule) > 1:
                errs.append(f"{p.name}: assessment.level={a['level']} 与规则值 {rule} 相差超过 1 级")
    for e in errs:
        print(e)
    print(f"校验 {len(paths)} 个文件，{len(errs)} 个问题")
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
