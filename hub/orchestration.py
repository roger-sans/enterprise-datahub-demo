"""Dagster assets, blocking checks and opt-in daily schedules."""

from contextlib import contextmanager
import os
from shutil import copyfile

from dagster import (
    AssetCheckResult, AssetCheckSeverity, AssetSelection, Config,
    ConfigurableResource, DagsterInstance, Definitions, ScheduleDefinition,
    asset, asset_check, define_asset_job, in_process_executor, mem_io_manager,
)

from . import lakehouse
from .catalog import PRODUCTS
from .store import Store
from .synthetic import source_rows

SCENARIOS = ("healthy", "negative-money")


class HubResource(ConfigurableResource):
    state_dir: str = ""

    def store(self):
        return Store(self.state_dir)


class BatchConfig(Config):
    product_id: str
    scenario: str = "healthy"
    actor: str = "platform-operator"


@contextmanager
def governed_stage(store, run_id, stage):
    try:
        yield
    except Exception as exc:
        store.fail(run_id, stage, {"failure": type(exc).__name__})
        raise


@asset(group_name="governed_lakehouse", compute_kind="Python")
def bronze_capture(context, config: BatchConfig, hub: HubResource) -> dict:
    if config.product_id not in PRODUCTS or config.scenario not in SCENARIOS:
        raise ValueError("Unknown product or source scenario.")
    store = hub.store()
    store.init()
    product = PRODUCTS[config.product_id]
    run_id, contract = store.start(config.product_id, config.scenario, config.actor, context.run.run_id)
    with governed_stage(store, run_id, "Bronze"):
        metadata = lakehouse.bronze(store, run_id, source_rows(product["source"], config.scenario))
        store.record(run_id, "Bronze", "passed", metadata)
        context.add_output_metadata(metadata)
    return {"run_id": run_id, "product_id": config.product_id, "contract": contract, "bronze": metadata}


@asset(group_name="governed_lakehouse", compute_kind="DuckDB")
def silver_standardise(context, bronze_capture: dict, hub: HubResource) -> dict:
    store, batch = hub.store(), bronze_capture
    run_id = batch["run_id"]
    with governed_stage(store, run_id, "Silver"):
        counts = lakehouse.silver(store, run_id, PRODUCTS[batch["product_id"]]["source"])
        store.record(run_id, "Silver", "passed", counts)
        context.add_output_metadata({"records": counts["rows"], "revisions_collapsed": counts["revisions_collapsed"]})
    return {**batch, "silver": counts}


def apply_gate(store, run_id, stage, checks, details=None):
    passed = all(check["passed"] for check in checks)
    evidence = {"checks": checks, **(details or {})}
    if passed:
        store.record(run_id, stage, "passed", evidence)
    else:
        store.fail(run_id, stage, evidence)
    return AssetCheckResult(passed=passed, severity=AssetCheckSeverity.ERROR, metadata=evidence)


@asset_check(asset=silver_standardise, blocking=True)
def source_quality(silver_standardise: dict, hub: HubResource):
    store, batch = hub.store(), silver_standardise
    run_id = batch["run_id"]
    with governed_stage(store, run_id, "Silver quality"):
        checks = lakehouse.silver_checks(store, run_id, PRODUCTS[batch["product_id"]], batch["silver"])
        return apply_gate(store, run_id, "Silver quality", checks)


@asset(group_name="governed_lakehouse", compute_kind="SQL")
def gold_model(context, silver_standardise: dict, hub: HubResource) -> dict:
    store, batch = hub.store(), silver_standardise
    run_id = batch["run_id"]
    with governed_stage(store, run_id, "Gold"):
        profile = lakehouse.gold(store, run_id, batch["product_id"], batch["contract"])
        store.record(run_id, "Gold", "passed", profile)
        context.add_output_metadata(profile)
    return {**batch, "gold": profile}


@asset_check(asset=gold_model, blocking=True)
def serving_contract(gold_model: dict, hub: HubResource):
    store, batch = hub.store(), gold_model
    run_id = batch["run_id"]
    with governed_stage(store, run_id, "Gold contract"):
        checks, rows = lakehouse.gold_checks(store, run_id, batch["product_id"], batch["contract"])
        return apply_gate(store, run_id, "Gold contract", checks, {"rows": rows})


@asset(group_name="governed_lakehouse", compute_kind="Python")
def serving_publish(context, gold_model: dict, hub: HubResource) -> None:
    store, batch = hub.store(), gold_model
    run_id = batch["run_id"]
    with governed_stage(store, run_id, "Serving"):
        gold_profile = next(event["details"] for event in store.events(run_id) if event["stage"] == "Gold contract")
        snapshot = store.artifact(run_id, "serving")
        copyfile(store.artifact(run_id, "gold"), snapshot)
        metadata = {
            "row_count": gold_profile["rows"],
            "bronze_rows": batch["bronze"]["rows"],
            "silver_rows": batch["silver"]["rows"],
            "source_digest": batch["bronze"]["sha256"],
            "snapshot_digest": lakehouse.hash_file(snapshot),
            "compressed_bytes": snapshot.stat().st_size,
            "checks_passed": len(gold_profile["checks"]) + 4,
        }
        store.publish(run_id, batch["product_id"], batch["contract"]["version"], metadata)
        context.add_output_metadata(metadata)


def run_config(product_id, scenario="healthy", actor="platform-operator", store=None):
    config = {"ops": {"bronze_capture": {"config": {
        "product_id": product_id, "scenario": scenario, "actor": actor,
    }}}}
    if store is not None:
        config["resources"] = {"hub": {"config": {"state_dir": str(store.root)}}}
    return config


job = define_asset_job("refresh_data_product", selection=AssetSelection.all(), executor_def=in_process_executor)
defs = Definitions(
    assets=[bronze_capture, silver_standardise, gold_model, serving_publish],
    asset_checks=[source_quality, serving_contract],
    jobs=[job],
    resources={"hub": HubResource(), "io_manager": mem_io_manager},
    schedules=[
        ScheduleDefinition(name=f"daily_{key.replace('-', '_')}", job=job,
                           cron_schedule=f"{index * 20} 6 * * *", execution_timezone="UTC",
                           run_config=run_config(key))
        for index, key in enumerate(PRODUCTS)
    ],
)


def launch(store: Store, product_id: str, scenario="healthy", actor="platform-operator"):
    instance = DagsterInstance.get() if os.environ.get("DAGSTER_HOME") else DagsterInstance.ephemeral()
    with instance:
        result = defs.resolve_job_def("refresh_data_product").execute_in_process(
            run_config=run_config(product_id, scenario, actor, store), instance=instance, raise_on_error=False,
        )
    run = store.run_for_dagster(result.run_id)
    if run is None:
        raise RuntimeError("Dagster stopped before the run could be journaled.")
    if run["status"] == "running":
        store.fail(run["id"], "Dagster", {"failure": "execution_interrupted"})
        run = store.run(run["id"])
    return run
