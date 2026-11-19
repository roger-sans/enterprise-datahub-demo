"""Snowflake-first governed refresh simulation for the offline portfolio.

Cloud-native ingestion, transformations, publication procedures and Tasks are
defined separately under snowflake/. This adapter ensures a complete local demo.
"""
from contextlib import contextmanager
from shutil import copyfile
from uuid import uuid4
from . import lakehouse
from .catalog import PRODUCTS
from .store import Store
from .synthetic import source_rows

SCENARIOS = ("healthy", "negative-money")
SCHEDULES = {
    "shipment-reliability": "0 6 * * * UTC",
    "freight-spend": "20 6 * * * UTC",
    "returns-pulse": "40 6 * * * UTC",
}

@contextmanager
def guarded(store: Store, run_id: int, stage: str):
    try:
        yield
    except Exception as exc:
        store.fail(run_id, stage, {"failure": type(exc).__name__})
        raise

def launch(store: Store, product_id: str, scenario="healthy", actor="platform-operator"):
    if product_id not in PRODUCTS or scenario not in SCENARIOS:
        raise ValueError("Unknown product or scenario.")
    store.init()
    run_id, contract = store.start(product_id, scenario, actor, str(uuid4()))
    with guarded(store, run_id, "Bronze"):
        bronze = lakehouse.bronze(store, run_id, source_rows(PRODUCTS[product_id]["source"], scenario))
        store.record(run_id, "Bronze", "passed", bronze)
    with guarded(store, run_id, "Silver"):
        silver = lakehouse.silver(store, run_id, PRODUCTS[product_id]["source"])
        store.record(run_id, "Silver", "passed", silver)
    with guarded(store, run_id, "Silver quality"):
        checks = lakehouse.silver_checks(store, run_id, PRODUCTS[product_id], silver)
        if not all(item["passed"] for item in checks):
            store.fail(run_id, "Silver quality", {"checks": checks})
            return store.run(run_id)
        store.record(run_id, "Silver quality", "passed", {"checks": checks})
    with guarded(store, run_id, "Gold"):
        gold = lakehouse.gold(store, run_id, product_id, contract)
        store.record(run_id, "Gold", "passed", gold)
    with guarded(store, run_id, "Gold contract"):
        gold_checks, row_count = lakehouse.gold_checks(store, run_id, product_id, contract)
        if not all(item["passed"] for item in gold_checks):
            store.fail(run_id, "Gold contract", {"checks": gold_checks, "rows": row_count})
            return store.run(run_id)
        store.record(run_id, "Gold contract", "passed", {"checks": gold_checks, "rows": row_count})
    with guarded(store, run_id, "Serving"):
        serving = store.artifact(run_id, "serving")
        copyfile(store.artifact(run_id, "gold"), serving)
        metadata = {
            "row_count": row_count, "bronze_rows": bronze["rows"], "silver_rows": silver["rows"],
            "source_digest": bronze["sha256"], "snapshot_digest": lakehouse.hash_file(serving),
            "compressed_bytes": serving.stat().st_size,
            "checks_passed": len(checks) + len(gold_checks),
            "execution_engine": "local-snowflake-simulator",
        }
        store.publish(run_id, product_id, contract["version"], metadata)
    return store.run(run_id)
