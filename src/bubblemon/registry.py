from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "indicators.yaml"


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


@dataclass(frozen=True)
class Config:
    dimensions: dict
    indicators: list
    alerts: dict
    scoring: dict = field(default_factory=dict)


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
    return Config(raw["dimensions"], indicators, raw["alerts"], raw.get("scoring", {}))
