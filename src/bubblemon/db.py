import os
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

from .registry import ROOT

DB_PATH = Path(os.environ.get("BUBBLEMON_DB", ROOT / "data" / "bubblemon.duckdb"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    date DATE NOT NULL,
    indicator_id VARCHAR NOT NULL,
    value DOUBLE NOT NULL,
    source VARCHAR NOT NULL,
    fetched_at TIMESTAMP NOT NULL,
    PRIMARY KEY (date, indicator_id)
);
CREATE TABLE IF NOT EXISTS fetch_log (
    indicator_id VARCHAR NOT NULL,
    fetched_at TIMESTAMP NOT NULL,
    ok BOOLEAN NOT NULL,
    rows_written INTEGER,
    error VARCHAR
);
"""


def connect(path: Path = DB_PATH) -> duckdb.DuckDBPyConnection:
    path = Path(path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    con.execute(SCHEMA)
    return con


def upsert_observations(con, indicator_id: str, source: str, series: pd.Series) -> int:
    series = series.dropna()
    if series.empty:
        return 0
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(series.index).date,
            "indicator_id": indicator_id,
            "value": series.astype(float).values,
            "source": source,
            "fetched_at": datetime.now(timezone.utc).replace(tzinfo=None),
        }
    )
    con.register("incoming", df)
    con.execute("INSERT OR REPLACE INTO observations SELECT * FROM incoming")
    con.unregister("incoming")
    return len(df)


def log_fetch(con, indicator_id: str, ok: bool, rows: int = 0, error: str | None = None):
    con.execute(
        "INSERT INTO fetch_log VALUES (?, ?, ?, ?, ?)",
        [indicator_id, datetime.now(timezone.utc).replace(tzinfo=None), ok, rows, error],
    )


def load_series(con, indicator_id: str) -> pd.Series:
    df = con.execute(
        "SELECT date, value FROM observations WHERE indicator_id = ? ORDER BY date",
        [indicator_id],
    ).df()
    return pd.Series(df["value"].values, index=pd.to_datetime(df["date"]), name=indicator_id, dtype=float)
