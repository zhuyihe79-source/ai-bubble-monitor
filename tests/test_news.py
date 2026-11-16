import json

import pandas as pd

from bubblemon import news


def item(**kw):
    base = {"published": "2026-11-14", "title": "T", "source": "Reuters", "url": "https://x.com/a", "topic": "memory",
            "importance": 4, "direction": "risk_up", "summary": "s", "implication": "i"}
    base.update(kw)
    return base


def write(tmp_path, date, items):
    p = tmp_path / f"{date}.json"
    p.write_text(json.dumps({"date": date, "items": items}, ensure_ascii=False), encoding="utf-8")
    return p


def test_validate_accepts_good_and_flags_each_bad_field():
    assert news.validate({"date": "2026-11-16", "items": [item()]}, "f") == []
    bad = [item(url="ftp://x"), item(url="https://b", topic="x"), item(url="https://c", importance=6),
           item(url="https://d", direction="up"), item(url="https://e", published="14/11/2026"),
           item(url="https://f", signal="nope"), {"title": "only"}]
    errs = news.validate({"date": "2026-11-16", "items": bad}, "f", trigger_ids={"capex_yoy"})
    for word in ("url", "topic", "importance", "direction", "published", "signal", "缺少"):
        assert any(word in e for e in errs), word


def test_validate_flags_duplicate_url_and_bad_date():
    errs = news.validate({"date": "16-11", "items": [item(), item()]}, "f")
    assert any("重复" in e for e in errs) and any("date" in e for e in errs)


def test_load_dedupes_across_days_keeps_first_and_skips_bad_files(tmp_path):
    write(tmp_path, "2026-11-10", [item(url="https://a", published="2026-11-09")])
    write(tmp_path, "2026-11-12", [item(url="https://a", published="2026-11-09", title="later copy"),
                                   item(url="https://b", published="2026-11-11")])
    write(tmp_path, "2026-11-13", [item(topic="bad")])
    items = news.load(tmp_path)
    assert [x.url for x in items] == ["https://b", "https://a"]
    assert next(x for x in items if x.url == "https://a").title == "T"


def test_recent_and_weekly_heat(tmp_path):
    write(tmp_path, "2026-11-16", [
        item(url="https://1", published="2026-11-15", direction="risk_up"),
        item(url="https://2", published="2026-11-14", direction="risk_down", topic="demand"),
        item(url="https://3", published="2026-11-13", importance=2),          # 重要性不足，不计热度
        item(url="https://4", published="2026-11-05", direction="risk_up"),   # 上一周
    ])
    items = news.load(tmp_path)
    asof = pd.Timestamp("2026-11-16")
    assert {x.url for x in news.recent(items, asof, 7)} == {"https://1", "https://2", "https://3"}
    heat = news.weekly_heat(items, asof, weeks=2)
    this_week = heat[heat.week_end == asof].set_index("topic")
    assert this_week.loc["memory", "count"] == 1 and this_week.loc["memory", "net"] == 1
    assert this_week.loc["demand", "net"] == -1
    last_week = heat[heat.week_end == asof - pd.Timedelta(days=7)].set_index("topic")
    assert last_week.loc["memory", "count"] == 1


def test_latest_note_picks_newest_dated_file(tmp_path):
    (tmp_path / "2026-11-09.md").write_text("# old", encoding="utf-8")
    (tmp_path / "2026-11-16.md").write_text("# new", encoding="utf-8")
    (tmp_path / "README.md").write_text("ignore", encoding="utf-8")
    assert news.latest_note(tmp_path) == ("2026-11-16", "# new")
    assert news.latest_note(tmp_path / "missing") is None
