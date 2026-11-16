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
        errs += validate(doc, p.name, trigger_ids)
    for e in errs:
        print(e)
    print(f"校验 {len(paths)} 个文件，{len(errs)} 个问题")
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
