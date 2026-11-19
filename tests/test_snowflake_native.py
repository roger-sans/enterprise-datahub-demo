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


def test_cloud_consumer_fails_closed_without_credentials(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from hub.api import create_app
    monkeypatch.delenv("HUB_SNOWFLAKE_CONNECTION", raising=False)
    with TestClient(create_app(tmp_path)) as client:
        response = client.get("/api/snowflake/freight-spend/data")
        assert response.status_code == 503
        assert "HUB_SNOWFLAKE_CONNECTION" in response.json()["detail"]


def test_cloud_reader_uses_only_allowlisted_secure_view_and_bound_parameters(monkeypatch):
    import sys
    import types
    from hub.catalog import BASE_CONTRACTS
    from hub.snowflake_reader import read_secure_view

    calls = []
    class Cursor:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def execute(self, sql, params=None):
            calls.append((sql, params))
        @property
        def description(self):
            return [(field["name"].upper(),) for field in BASE_CONTRACTS["freight-spend"]["fields"]]
        def fetchall(self):
            return []
    class Connection:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def cursor(self):
            return Cursor()
    connector = types.ModuleType("snowflake.connector")
    connector.connect = lambda **kwargs: Connection()
    snowflake = types.ModuleType("snowflake")
    snowflake.connector = connector
    monkeypatch.setitem(sys.modules, "snowflake", snowflake)
    monkeypatch.setitem(sys.modules, "snowflake.connector", connector)
    monkeypatch.setenv("HUB_SNOWFLAKE_CONNECTION", "synthetic-reader")

    result = read_secure_view("freight-spend", 10, "WEST")
    assert result["source"].startswith("Snowflake")
    assert calls[0][0] == "USE SECONDARY ROLES NONE"
    assert "EDH_DEMO.SERVING.FREIGHT_SPEND_V1" in calls[1][0]
    assert calls[1][1] == ["WEST", 10]
    assert "WEST" not in calls[1][0]  # parameterised, never interpolated
