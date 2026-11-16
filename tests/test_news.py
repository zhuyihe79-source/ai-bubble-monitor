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


def test_rule_rating_uses_weighted_balance_not_count(tmp_path):
    asof = pd.Timestamp("2026-11-16")
    # 两条 4 分风险上升 + 一条 4 分风险下降 → (2+2-2)/6 = +0.33 → 4 偏高
    write(tmp_path, "2026-11-16", [item(url="https://1"), item(url="https://2"),
                                   item(url="https://3", direction="risk_down")])
    level, balance, weight, forced = news.rule_rating(news.load(tmp_path), asof)
    assert (level, round(balance, 2), weight, forced) == (4, 0.33, 6.0, False)
    # 同样的比例、两倍的条数，评级不变
    write(tmp_path, "2026-11-15", [item(url=f"https://x{i}", direction="risk_down" if i == 0 else "risk_up")
                                   for i in range(3)])
    assert news.rule_rating(news.load(tmp_path), asof)[0] == 4


def test_rule_rating_thresholds_floor_and_minimum(tmp_path):
    asof = pd.Timestamp("2026-11-16")
    cases = {1: ["risk_down"] * 3, 3: ["neutral"] * 3, 5: ["risk_up"] * 3}
    for expected, dirs in cases.items():
        d = tmp_path / str(expected)
        d.mkdir()
        write(d, "2026-11-16", [item(url=f"https://{i}", direction=x) for i, x in enumerate(dirs)])
        assert news.rule_rating(news.load(d), asof)[0] == expected
    # 重要性 5 的风险上升新闻把中性抬到 4
    d = tmp_path / "forced"
    d.mkdir()
    write(d, "2026-11-16", [item(url="https://a", importance=5)] +
          [item(url=f"https://n{i}", direction="risk_down") for i in range(2)])
    level, _, _, forced = news.rule_rating(news.load(d), asof)
    assert (level, forced) == (4, True)
    # 权重不足不出评级；7 天前的新闻不算
    d = tmp_path / "thin"
    d.mkdir()
    write(d, "2026-11-16", [item(url="https://t", importance=3), item(url="https://old", published="2026-11-01")])
    assert news.rule_rating(news.load(d), asof)[0] is None


def test_rating_applies_assessment_within_one_level(tmp_path):
    asof = pd.Timestamp("2026-11-16")
    write(tmp_path, "2026-11-16", [item(url=f"https://{i}") for i in range(3)])
    items = news.load(tmp_path)
    r = news.rating(items, {asof: (4, "同一事件重复")}, asof)
    assert (r.level, r.rule_level, r.reason) == (4, 5, "同一事件重复")
    assert news.rating(items, {asof: (1, "x")}, asof).level == 4      # 超出一级会被截断
    assert news.rating(items, {}, asof).level == 5


def test_validate_assessment_fields():
    ok = {"date": "2026-11-16", "assessment": {"level": 4, "reason": "r"}, "items": [item()]}
    assert news.validate(ok, "f") == []
    assert any("assessment.level" in e for e in news.validate({**ok, "assessment": {"level": 7, "reason": "r"}}, "f"))
    assert any("reason" in e for e in news.validate({**ok, "assessment": {"level": 3, "reason": " "}}, "f"))


def test_news_check_rejects_assessment_two_levels_off(tmp_path, monkeypatch, capsys):
    p = tmp_path / "2026-11-16.json"
    p.write_text(json.dumps({"date": "2026-11-16", "assessment": {"level": 3, "reason": "r"},
                             "items": [item(url=f"https://{i}") for i in range(3)]}), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["bubblemon-news-check", str(p)])
    try:
        news.main()
    except SystemExit as exc:
        assert exc.code == 1
    assert "相差超过 1 级" in capsys.readouterr().out


def test_signal_alerts_only_strong_risk_up_with_signal(tmp_path):
    write(tmp_path, "2026-11-16", [
        item(url="https://a", signal="debt_yoy"),
        item(url="https://b", signal="debt_yoy", importance=3),
        item(url="https://c", signal="capex_yoy", direction="risk_down"),
        item(url="https://d"),
    ])
    alerts = news.signal_alerts(news.load(tmp_path), pd.Timestamp("2026-11-16"))
    assert {k: [x.url for x in v] for k, v in alerts.items()} == {"debt_yoy": ["https://a"]}
