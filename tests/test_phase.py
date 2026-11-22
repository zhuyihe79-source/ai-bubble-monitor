import numpy as np
import pandas as pd
import pytest

from bubblemon import commentary, phase, report, scoring, triggers
from bubblemon.registry import LAYERS, Config, Indicator, Trigger, load_config


def test_real_config_every_layer_has_signals_and_phase_layers_exist():
    cfg = load_config()
    by_layer = {k: [t.id for t in cfg.triggers if t.layer == k] for k in LAYERS}
    assert all(by_layer.values())
    assert {"nvda_rev_qoq", "capex_yoy"} <= set(by_layer["demand"]) and "nvda_drawdown" in by_layer["price"]


def test_config_rejects_unknown_layer(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("""
dimensions: {valuation: {label: v, weight: 1}}
indicators:
  - {id: x, name: x, dimension: valuation, source: manual, direction: high, frequency: daily, max_stale_days: 10}
alerts: {score_yellow: 60, score_red: 80}
triggers:
  - {id: t, name: t, series: x, transform: level, direction: above, alert: 1, trigger: 2, unit: num, why: w, layer: mood}
""", encoding="utf-8")
    with pytest.raises(ValueError, match="layer"):
        load_config(p)


def test_layer_takes_worst_status_and_ignores_missing_data():
    cfg = load_config()
    ids = [t.id for t in cfg.triggers]
    st = dict.fromkeys(ids, "ok")
    st.update(nvda_rev_qoq="nodata", capex_yoy="alert", nvda_drawdown="triggered", vix_level="nodata",
              real_yield_3m="nodata", bubble_search="nodata")
    assert phase.layer_states(st, cfg) == {"demand": "alert", "price": "triggered", "financing": "ok", "climate": "nodata"}


@pytest.mark.parametrize("demand,price,expected", [
    ("ok", "ok", 1), ("ok", "alert", 1), ("alert", "ok", 1),     # 警戒不改变阶段
    ("ok", "triggered", 2), ("alert", "triggered", 2),
    ("triggered", "ok", 3), ("triggered", "alert", 3),
    ("triggered", "triggered", 4), ("nodata", "triggered", 2),
])
def test_phase_only_depends_on_demand_and_price_triggers(demand, price, expected):
    layers = {"demand": demand, "price": price, "financing": "triggered", "climate": "triggered"}
    assert phase.phase_of(layers) == expected


def test_history_and_base_rates_use_only_weeks_with_data():
    ind = Indicator("x", "x", "valuation", "manual", "high", "daily", 10)
    t = Trigger("t", "t", "x", "level", "above", 1.0, 2.0, "num", "why")
    cfg = Config({"valuation": {"label": "v", "weight": 1.0}}, [ind], {"score_yellow": 60, "score_red": 80}, {}, [t])
    s = pd.Series([0.0, 0.0, 1.5, 3.0], index=pd.to_datetime(["2024-01-12", "2024-01-19", "2024-01-26", "2024-02-02"]))
    dates = pd.date_range("2024-01-05", "2024-02-02", freq="W-FRI")   # 第一周还没有数据
    hist = triggers.history({"x": s}, cfg, dates)
    assert hist["t"].tolist() == ["nodata", "ok", "ok", "alert", "triggered"]
    assert triggers.base_rates(hist) == {"t": (0.5, 4)}
    ph = phase.history(hist, cfg)
    assert ph["price"].tolist() == hist["t"].tolist() and ph["phase"].tolist() == [1, 1, 1, 1, 2]


def _nvda_like():
    idx = pd.bdate_range("2019-01-01", "2023-12-29")
    px = pd.Series(100.0, index=idx)
    px["2020-06-01":"2020-08-31"] = 60.0      # 跌破 -35%
    px["2020-09-01":"2021-02-26"] = 50.0
    px["2022-09-01":"2022-09-14"] = 60.0      # 第二次，很快收回
    rev = pd.Series(100.0, index=pd.date_range("2019-03-31", "2023-09-30", freq="QE"))
    rev["2020-09-30"], rev["2020-12-31"] = 80.0, 90.0
    return px, rev


def test_drawdown_episodes_separate_confirmed_from_unconfirmed():
    px, rev = _nvda_like()
    first, second = phase.drawdown_episodes(px, rev, load_config())
    assert first.start == pd.Timestamp("2020-06-01") and first.max_drawdown == pytest.approx(-0.5)
    assert first.confirmed and first.demand_quarter == pd.Timestamp("2020-09-30") and first.demand_qoq == pytest.approx(-0.2)
    assert first.further == pytest.approx(50 / 60 - 1) and first.after_12m == pytest.approx(100 / 60 - 1)
    # 财报 9/30 + 35 天才可见，那时股价已经比高点低一半，之后没有再跌
    assert first.confirm_date == pd.Timestamp("2020-11-04")
    assert first.drop_at_confirm == pytest.approx(-0.5) and first.after_confirm == pytest.approx(0.0)
    assert second.start == pd.Timestamp("2022-09-01") and not second.confirmed and second.further == pytest.approx(0.0)
    assert not first.ongoing and not second.ongoing


def test_ongoing_episode_has_no_outcome_yet():
    px, rev = _nvda_like()
    (e,) = phase.drawdown_episodes(px[:"2020-07-15"], rev[:"2020-06-30"], load_config())
    assert e.ongoing and not e.confirmed and np.isnan(e.after_12m) and np.isnan(e.drop_at_confirm)
    text = report._episodes_html([e], next(t for t in load_config().triggers if t.id == "nvda_drawdown"))
    assert "进行中" in text and "还不知道" in text


def test_episode_summary_reports_both_outcomes():
    px, rev = _nvda_like()
    cfg = load_config()
    txt = report._episode_summary(phase.drawdown_episodes(px, rev, cfg), next(t for t in cfg.triggers if t.id == "nvda_drawdown"))
    assert "共 2 次" in txt and "其中 1 次" in txt and "又跌了 17%" in txt
    assert "1 次收入没有掉，跌破那几天就是低点" in txt and "已经比高点低了 50%" in txt


def test_track_record_spans_and_outcomes():
    weeks = pd.date_range("2024-01-05", periods=60, freq="W-FRI")
    phases = pd.Series(1, index=weeks)
    phases.iloc[10:14] = 2
    px = pd.Series(np.linspace(100, 160, len(pd.bdate_range(weeks[0], weeks[-1]))), index=pd.bdate_range(weeks[0], weeks[-1]))
    rec = phase.track_record(phases, px, days=91)
    assert rec[2]["weeks"] == 4 and rec[2]["spans"] == [(weeks[10], weeks[13])] and rec[2]["share"] == pytest.approx(4 / 60)
    assert len(rec[1]["spans"]) == 2 and rec[1]["median_return"] > 0 and rec[1]["median_worst"] == pytest.approx(0.0)
    assert rec[4]["weeks"] == 0 and np.isnan(rec[4]["median_return"])
    assert report._span_text(rec[2]["spans"], weeks[-1]) == "2024-03 至 2024-04"
    assert report._span_text(rec[1]["spans"], weeks[-1]).endswith("至今")


def test_weekly_note_leads_with_phase():
    idx = pd.date_range("2015-01-02", periods=400, freq="W-FRI")
    a = pd.Series(np.linspace(1, 2, 400), index=idx)
    cfg = Config({"valuation": {"label": "估值", "weight": 1.0}}, [Indicator("a", "A", "valuation", "manual", "high", "weekly", 30)],
                 {"score_yellow": 60, "score_red": 80, "indicator_extreme_pct": 0.95}, {"min_dimensions": 1},
                 [Trigger("p", "P", "a", "level", "above", 1.5, 1.9, "num", "w", layer="price")])
    note = commentary.weekly_note({"a": a}, cfg, scoring.compute({"a": a}, cfg, asof=idx[-1]), idx[-1])
    assert note.headline.startswith("阶段：价格回调，需求未证实转弱。") and "估值 100" in note.headline
    basis = dict(note.sections)["阶段判断"]
    assert any(x.startswith("价格层 触发：P") for x in basis)


def test_phase_card_highlights_current_cell_and_surfaces_demand_news():
    cfg = load_config()
    now = {t.id: triggers.TriggerState(t, "ok", 0.5, pd.Timestamp("2026-09-30")) for t in cfg.triggers}
    dd = next(t for t in cfg.triggers if t.id == "nvda_drawdown")
    now["nvda_drawdown"] = triggers.TriggerState(dd, "triggered", -0.4, pd.Timestamp("2026-11-20"))
    layers = phase.layer_states({k: s.status for k, s in now.items()}, cfg)
    from bubblemon.news import NewsItem
    item = NewsItem(pd.Timestamp("2026-11-20"), "Guidance cut", "Reuters", "https://x", "nvidia", 5, "risk_up", "s", "i", "nvda_rev_qoq")
    card = report._phase_card(phase.phase_of(layers), layers, now, cfg, [], {"nvda_rev_qoq": [item]})
    assert "价格回调，需求未证实转弱" in card and card.count("class='c on'") == 1
    assert "Guidance cut" in card and "指向需求转弱" in card
