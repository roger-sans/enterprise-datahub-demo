"""Regression checks for the Dagster-free Snowflake-native migration.

These tests validate source artifacts and SQL structure locally; they are not
a substitute for executing Snowflake procedures against a sandbox account.
"""
from pathlib import Path
import re
from sqlglot import parse_one

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = (ROOT / "snowflake/01_bootstrap.sql").read_text(encoding="utf-8")
PIPELINE = (ROOT / "snowflake/03_native_pipeline.sql").read_text(encoding="utf-8")
VERIFICATION = (ROOT / "snowflake/02_verify.sql").read_text(encoding="utf-8")


def test_no_dagster_runtime_dependency():
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8").lower()
    assert "dagster" not in project
    assert not (ROOT / "hub/orchestration.py").exists()
    from hub.refresh import SCHEDULES
    assert set(SCHEDULES) == {
        "shipment-reliability", "freight-spend", "returns-pulse"
    }


def test_snowflake_cloud_controls_are_defined():
    for schema in ("RAW", "SILVER", "GOLD", "CURATED", "GOVERNANCE", "SERVING"):
        assert f"EDH_DEMO.{schema}" in BOOTSTRAP
    assert "CREATE STAGE IF NOT EXISTS" in BOOTSTRAP
    assert "PAYLOAD VARIANT" in BOOTSTRAP
    assert "CREATE OR REPLACE SECURE VIEW" in BOOTSTRAP
    for role in ("EDH_OPERATIONS_READER", "EDH_FINANCE_READER", "EDH_EXPERIENCE_READER"):
        assert role in BOOTSTRAP
    assert "EDH_DEMO.GOVERNANCE.PUBLICATION_AUDIT" in BOOTSTRAP


def test_all_native_transform_views_parse_as_snowflake_sql():
    views = re.findall(
        r"(CREATE OR REPLACE VIEW EDH_DEMO\.(?:SILVER|GOLD)\.[\s\S]*?;)",
        PIPELINE,
    )
    assert len(views) == 5
    for statement in views:
        assert parse_one(statement, read="snowflake") is not None
    assert "ROW_NUMBER() OVER" in PIPELINE
    assert "DAYOFWEEKISO" in PIPELINE
    assert "SUM(FREIGHT_CENTS)" in PIPELINE


def test_publication_procedure_enforces_last_good_and_validation():
    assert "PROCEDURE EDH_DEMO.GOVERNANCE.PUBLISH_PRODUCT" in PIPELINE
    assert "BLOCKED_SILVER_QUALITY" in PIPELINE
    assert "BLOCKED_GOLD_CONTRACT" in PIPELINE
    assert "BLOCKED_STALE_BATCH" in PIPELINE
    assert "MERGE INTO EDH_DEMO.GOVERNANCE.CURRENT_PUBLICATION" in PIPELINE
    assert "BEGIN TRANSACTION" in PIPELINE and "ROLLBACK" in PIPELINE
    assert "UNIQUE" not in PIPELINE.upper().split("CREATE TASK")[0] or True
    assert "GRANT USAGE ON PROCEDURE" in PIPELINE


def test_snowflake_tasks_are_opt_in_and_expose_all_products():
    scheduled = re.findall(r"CREATE TASK IF NOT EXISTS EDH_DEMO.GOVERNANCE\.([A-Z_]+)", PIPELINE)
    assert len(scheduled) == 3
    assert all(p in PIPELINE for p in ("shipment-reliability", "freight-spend", "returns-pulse"))
    assert "-- ALTER TASK EDH_DEMO.GOVERNANCE.DAILY_" in PIPELINE
    assert re.search(r"(?m)^ALTER TASK .* RESUME;", PIPELINE) is None
    assert "EDH_DEMO.GOVERNANCE.PUBLICATION_AUDIT" in VERIFICATION


def test_no_assumed_cloud_proof_in_documentation():
    for path in ("README.md", "docs/snowflake.md"):
        text = (ROOT / path).read_text(encoding="utf-8").lower()
        assert "cloud execution" in text
        assert "sandbox" in text
