from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "indicators.yaml"
GROUPS = {"ai": "AI 泡沫温度", "market": "市场宽松度"}
# 破裂信号分层。阶段判断只看需求和价格；融资、情绪与利率是背景，决定回调来了有多疼。
LAYERS = {"demand": "需求", "price": "价格", "financing": "融资", "climate": "情绪与利率"}


@dataclass(frozen=True)
class Indicator:
    id: str
    name: str
    dimension: str
    source: str
    direction: str
    frequency: str
    max_stale_days: int
    publication_lag_days: int = 0
    params: dict = field(default_factory=dict)
    score: bool = True


@dataclass(frozen=True)
class Trigger:
    id: str
    name: str
    series: str
    transform: str
    direction: str
    alert: float
    trigger: float
    unit: str
    why: str
    days: int = 0
    tolerance_days: int = 10
    layer: str = "price"


@dataclass(frozen=True)
class Config:
    dimensions: dict
    indicators: list
    alerts: dict
    scoring: dict = field(default_factory=dict)
    triggers: list = field(default_factory=list)

    def indicator(self, iid: str) -> Indicator:
        return next(i for i in self.indicators if i.id == iid)

    @property
    def scored(self) -> list:
        return [i for i in self.indicators if i.score]

    def group_dims(self, group: str) -> list[str]:
        return [d for d, meta in self.dimensions.items() if meta.get("group", "ai") == group]


def load_config(path: Path = CONFIG_PATH) -> Config:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    indicators = [Indicator(**i) for i in raw["indicators"]]
    ids = [i.id for i in indicators]
    if len(ids) != len(set(ids)):
        raise ValueError("indicator id 重复")
    for i in indicators:
        if i.dimension not in raw["dimensions"]:
            raise ValueError(f"{i.id}: 未知维度 {i.dimension}")
        if i.direction not in ("high", "low"):
            raise ValueError(f"{i.id}: direction 必须是 high 或 low")
    for d, meta in raw["dimensions"].items():
        if meta.get("group", "ai") not in GROUPS:
            raise ValueError(f"维度 {d}: group 必须是 {list(GROUPS)} 之一")
    triggers = [Trigger(**t) for t in raw.get("triggers", [])]
    for t in triggers:
        if t.series not in ids:
            raise ValueError(f"触发器 {t.id}: 未知序列 {t.series}")
        if t.transform not in ("level", "pct_change", "diff", "drawdown"):
            raise ValueError(f"触发器 {t.id}: 未知 transform {t.transform}")
        if t.direction not in ("above", "below"):
            raise ValueError(f"触发器 {t.id}: direction 必须是 above 或 below")
        if t.layer not in LAYERS:
            raise ValueError(f"触发器 {t.id}: layer 必须是 {list(LAYERS)} 之一")
        if t.transform != "level" and t.days <= 0:
            raise ValueError(f"触发器 {t.id}: 需要 days")
        ok_order = t.trigger >= t.alert if t.direction == "above" else t.trigger <= t.alert
        if not ok_order:
            raise ValueError(f"触发器 {t.id}: 触发线应比警戒线更极端")
    return Config(raw["dimensions"], indicators, raw["alerts"], raw.get("scoring", {}), triggers)
