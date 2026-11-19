from datetime import UTC, datetime, timedelta
from hashlib import sha256
import csv
import io
import json

import pytest
from fastapi.testclient import TestClient

from hub.api import create_app
from hub.catalog import BASE_CONTRACTS, PRODUCTS, compatibility
from hub.refresh import SCHEDULES, launch
from hub.store import Store
from hub.synthetic import source_rows

SHIP = "shipment-reliability"
COST = "freight-spend"
RETURNS = "returns-pulse"
OPERATOR = "platform-operator"
STEWARD = "governance-steward"
OWNER = "operations-owner"


@pytest.fixture
def store(tmp_path):
    db = Store(tmp_path)
    db.init()
    return db


@pytest.fixture
def client(store):
    with TestClient(create_app(store.root)) as browser:
        yield browser


def post_run(client, product=SHIP, scenario="healthy", actor=OPERATOR):
    return client.post("/api/runs", json={"actor": actor, "scenario": scenario, "product_id": product})


def propose(client, action, actor=OWNER):
    return client.post(f"/api/products/{SHIP}/changes", json={
        "actor": actor, "action": action, "rationale": "Keep existing finance and operations workflows stable.",
    })


def decide(client, change, actor=STEWARD, decision="approve"):
    return client.post(f"/api/changes/{change['id']}/decision", json={
        "actor": actor, "decision": decision, "note": "Checked the published grain and downstream client expectations.",
    })


def test_all_three_products_publish_reconciled_results(client, store):
    for product in PRODUCTS:
        started = post_run(client, product)
        assert started.status_code == 201
        run = started.json()
        assert run["status"] == "published"
        assert run["metadata"]["checks_passed"] == 12
        result = client.get(f"/api/products/{product}/data").json()
        assert result["version"] == "1.0.0"
        assert result["total"] == run["metadata"]["row_count"]
        assert result["publication_id"] == run["id"]
        assert set(result["columns"]) == {field["name"] for field in BASE_CONTRACTS[product]["fields"]}
        assert "ref" not in result["columns"]
        assert store.artifact(run["id"], "serving").is_file()
    assert client.get("/api/overview").json()["fresh_count"] == 3


def test_failure_preserves_last_good_and_healthy_replay_resolves_alert(client, store):
    first = post_run(client, COST).json()
    current = client.get(f"/api/products/{COST}/download")
    failed = post_run(client, COST, "negative-money").json()
    assert failed["status"] == "blocked"
    events = client.get(f"/api/runs/{failed['id']}").json()["events"]
    assert [event["stage"] for event in events] == ["Bronze", "Silver", "Silver quality"]
    assert [check["name"] for check in events[-1]["details"]["checks"] if not check["passed"]] == [
        "Non-negative monetary amount"
    ]
    assert not store.artifact(failed["id"], "gold").exists()
    kept = client.get(f"/api/products/{COST}/download")
    assert kept.content == current.content
    assert kept.headers["x-publication-id"] == str(first["id"])
    alert = client.get("/api/alerts").json()["quality"][0]
    url = f"/api/alerts/{alert['id']}/acknowledge"
    assert client.post(url, json={"actor": OWNER}).status_code == 403
    assert client.post(url, json={"actor": OPERATOR}).json()["status"] == "acknowledged"
    assert client.post(url, json={"actor": OPERATOR}).status_code == 409
    replay = post_run(client, COST).json()
    assert replay["status"] == "published"
    assert client.get("/api/alerts").json()["quality"][0]["status"] == "resolved"
    assert store.current(COST)["id"] == replay["id"]


def test_shared_source_is_reproducible_and_keeps_different_business_grains(client):
    shipment = post_run(client).json()
    freight = post_run(client, COST).json()
    assert shipment["metadata"]["source_digest"] == freight["metadata"]["source_digest"]
    assert shipment["metadata"]["silver_rows"] == freight["metadata"]["silver_rows"]
    assert shipment["metadata"]["bronze_rows"] > shipment["metadata"]["silver_rows"]
    detail = client.get(f"/api/products/{COST}").json()
    assert detail["lineage"]["shared_with"][0]["id"] == SHIP
    totals = []
    for product in (SHIP, COST):
        records = csv.DictReader(io.StringIO(client.get(f"/api/products/{product}/download").text))
        totals.append(sum(int(r["shipment_count"]) for r in records))
    assert totals[1] > totals[0]  # Finance includes dispatched shipments awaiting delivery.


def test_approved_contract_and_published_contract_move_at_distinct_points(client):
    initial = post_run(client).json()
    breaking = propose(client, "remove-metric").json()
    assert breaking["status"] == "blocked"
    assert decide(client, breaking).status_code == 409
    candidate = propose(client, "add-note").json()
    assert candidate["status"] == "pending"
    assert decide(client, candidate, OWNER).status_code == 403
    assert decide(client, candidate).json()["status"] == "approved"
    detail = client.get(f"/api/products/{SHIP}").json()
    assert detail["contract"]["version"] == "1.1.0"
    assert detail["published_contract"]["version"] == "1.0.0"
    assert detail["publication"]["id"] == initial["id"]
    assert post_run(client, scenario="negative-money").json()["status"] == "blocked"
    assert client.get(f"/api/products/{SHIP}/data").json()["version"] == "1.0.0"
    assert post_run(client).json()["version"] == "1.1.0"
    updated = client.get(f"/api/products/{SHIP}/data").json()
    assert "reporting_note" in updated["columns"]
    assert all(row["reporting_note"] is None for row in updated["rows"])
    assert client.get(f"/api/products/{SHIP}/contracts/1.0.0").status_code == 200


def test_independent_decisions_reject_stale_proposals(client):
    first = propose(client, "add-note").json()
    second = propose(client, "add-note").json()
    assert decide(client, first).status_code == 200
    assert decide(client, second).status_code == 409
    assert decide(client, second, decision="reject").json()["status"] == "rejected"
    assert decide(client, second).status_code == 409


def test_out_of_role_invalid_inputs_and_bounds(client):
    assert propose(client, "add-note", "finance-owner").status_code == 403
    assert post_run(client, actor="analytics-consumer").status_code == 403
    assert post_run(client, scenario="unknown").status_code == 422
    assert client.get("/api/products/unknown").status_code == 404
    assert client.get(f"/api/products/{RETURNS}/data").status_code == 404
    assert client.get(f"/api/products/{SHIP}/data?limit=999").status_code == 422
    assert client.get(f"/api/products/{SHIP}/data?period=invalid").status_code == 422


def test_filter_and_download_return_identical_artifact_scope(client):
    post_run(client, RETURNS)
    path = f"/api/products/{RETURNS}"
    preview = client.get(path + "/data").json()
    date = preview["filters"]["periods"][0]
    params = {"dimension": "web", "period": date}
    filtered = client.get(path + "/data", params=params).json()
    csvfile = client.get(path + "/download", params=params)
    rows = list(csv.DictReader(io.StringIO(csvfile.text)))
    assert len(rows) == filtered["total"] > 0
    assert all(row["channel"] == "web" and row["period_start"] == date for row in rows)
    assert csvfile.headers["x-publication-id"] == str(filtered["publication_id"])


def test_stale_freshness_is_distinct_from_quality_failure(client, store):
    run = post_run(client, COST).json()
    old = (datetime.now(UTC) - timedelta(hours=49)).isoformat()
    with store.connection(write=True) as db:
        db.execute("UPDATE runs SET finished_at = ? WHERE id = ?", (old, run["id"]))
    alerts = client.get("/api/alerts").json()
    assert not alerts["quality"]
    assert any(alert["product_id"] == COST and alert["status"] == "stale" for alert in alerts["freshness"])
    assert client.get(f"/api/products/{COST}/data").status_code == 200


def test_concurrent_completion_does_not_replace_a_newer_pointer(store):
    old, _ = store.start(SHIP, "healthy", OPERATOR, "old")
    new, _ = store.start(SHIP, "healthy", OPERATOR, "new")
    store.publish(new, SHIP, "1.0.0", {})
    store.publish(old, SHIP, "1.0.0", {})
    assert store.current(SHIP)["id"] == new
    assert store.run(old)["status"] == "superseded"
    older_failure, _ = store.start(SHIP, "healthy", OPERATOR, "slower-failure")
    recovered, _ = store.start(SHIP, "healthy", OPERATOR, "healthy-recovery")
    store.publish(recovered, SHIP, "1.0.0", {})
    store.fail(older_failure, "Silver quality", {})
    assert store.alerts()[0]["status"] == "resolved"


def test_new_contract_takes_precedence_over_in_flight_old_contract(store):
    old, _ = store.start(SHIP, "healthy", OPERATOR, "old-contract")
    change = store.propose(SHIP, OWNER, "add-note", "Verified optional evidence from consuming teams.")
    store.decide(change["id"], STEWARD, "approve", "Approved following stakeholder consultation.")
    store.publish(old, SHIP, "1.0.0", {})
    assert store.current(SHIP) is None
    assert store.run(old)["status"] == "superseded"


def test_source_fixtures_and_schedule_are_available():
    for source in ("Dispatch events", "Return events"):
        healthy = source_rows(source, "healthy")
        assert healthy == source_rows(source, "healthy")
        anomaly = source_rows(source, "negative-money")
        assert healthy[:-1] == anomaly[:-1]
        assert healthy[-1] != anomaly[-1]
    assert len(SCHEDULES) == 3


def test_snowflake_staging_exports_raw_events_and_provenance(tmp_path):
    from hub.snowflake import export_source

    load = export_source(RETURNS, tmp_path / "snowflake", "healthy")
    manifest = json.loads(load.with_name("manifest.json").read_text())
    raw = load.with_name(manifest["source_file"])
    assert sha256(raw.read_bytes()).hexdigest() == manifest["sha256"]
    assert manifest["product_id"] == RETURNS
    assert manifest["source_id"] == "Return events"
    assert manifest["rows"] == len(source_rows("Return events", "healthy"))
    assert manifest["snowflake_execution"] == "not_executed"
    first = json.loads(raw.read_text().splitlines()[0])
    assert first["source_id"] == "Return events"
    assert first["payload"]["source_row"] == 1
    script = load.read_text()
    assert "COPY INTO EDH_DEMO.RAW.EVENTS" in script
    assert "EDH_DEMO.GOVERNANCE.PUBLISH_PRODUCT" in script
    assert "EDH_DEMO.RAW.SYNTHETIC_EVENTS" in script
    assert "CURATED.CURRENT_PUBLICATION" not in script

    rejected = export_source(COST, tmp_path / "rejected", "negative-money")
    bad_manifest = json.loads(rejected.with_name("manifest.json").read_text())
    assert bad_manifest["scenario"] == "negative-money"
    assert any(json.loads(line)["payload"]["freight_cents"] < 0
               for line in rejected.with_name(bad_manifest["source_file"]).read_text().splitlines())



def test_compatibility_rejects_new_required_fields_and_reordered_columns():
    contract = BASE_CONTRACTS[COST]
    fields = contract["fields"]
    required = {"name": "extra", "type": "date", "required": True}
    assert "required" in compatibility(contract, {**contract, "fields": fields + [required]})[0]
    assert "order" in compatibility(contract, {**contract, "fields": fields[::-1]})[0]


def test_gold_contract_blocks_a_bad_projection(client, store, monkeypatch):
    from hub import lakehouse

    previous = post_run(client, COST).json()
    sql_for = lakehouse.sql_for
    monkeypatch.setattr(
        lakehouse, "sql_for",
        lambda name: "SELECT * EXCLUDE (freight_cents) FROM (" + sql_for(name) + ") AS candidate"
        if name == COST else sql_for(name),
    )
    failed = post_run(client, COST).json()
    assert failed["status"] == "blocked"
    assert store.events(failed["id"])[-1]["stage"] == "Gold contract"
    assert not store.artifact(failed["id"], "serving").exists()
    assert store.current(COST)["id"] == previous["id"]


def test_concurrent_local_runs_have_isolated_batch_context(store):
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=2) as runner:
        futures = [runner.submit(launch, store, product) for product in (SHIP, RETURNS)]
        first, second = [future.result(timeout=20) for future in futures]
    assert first["status"] == second["status"] == "published"
    assert first["metadata"]["source_digest"] != second["metadata"]["source_digest"]
    assert store.current(SHIP)["id"] == first["id"]
    assert store.current(RETURNS)["id"] == second["id"]
