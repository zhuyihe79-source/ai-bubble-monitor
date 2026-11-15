import argparse
import logging

from . import db
from .fetchers import edgar, fred, manual, trends, yahoo
from .registry import load_config

log = logging.getLogger("bubblemon")

FETCHERS = {
    "fred": fred.fetch,
    "yahoo": yahoo.fetch,
    "edgar": edgar.fetch,
    "trends": trends.fetch,
    "manual": manual.fetch,
}


def run(only: list[str] | None = None, con=None) -> dict[str, str]:
    """逐个指标采集。单个指标失败只记录日志，不影响其他指标。"""
    cfg = load_config()
    con = con or db.connect()
    results = {}
    for ind in cfg.indicators:
        if only and ind.id not in only:
            continue
        try:
            series = FETCHERS[ind.source](ind.params)
            n = db.upsert_observations(con, ind.id, ind.source, series)
            db.log_fetch(con, ind.id, True, n)
            results[ind.id] = f"ok ({n} rows)"
        except Exception as exc:  # noqa: BLE001 - 数据源千奇百怪，统一记录
            db.log_fetch(con, ind.id, False, 0, str(exc)[:500])
            results[ind.id] = f"FAILED: {exc}"
        log.info("%s: %s", ind.id, results[ind.id])
    return results


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description="采集所有指标数据")
    ap.add_argument("--only", nargs="*", help="只采集指定 indicator id")
    args = ap.parse_args()
    results = run(args.only)
    failed = [k for k, v in results.items() if v.startswith("FAILED")]
    if failed:
        print(f"\n失败 {len(failed)} 个: {', '.join(failed)}")


if __name__ == "__main__":
    main()
