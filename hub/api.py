"""Read governed publications and exercise the simulated operating model."""

import csv
import json
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from io import StringIO
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from .catalog import ACTORS, PACKAGE, PRODUCTS
from .lakehouse import read_publication, trend
from .refresh import launch
from .store import Conflict, Forbidden, Store, require_role


class Action(BaseModel):
    actor: str = Field(examples=["platform-operator"])


class RunRequest(Action):
    product_id: str = Field(examples=["shipment-reliability"])
    scenario: Literal["healthy", "negative-money"] = "healthy"


class GovernanceAction(Action):
    @field_validator("actor")
    @classmethod
    def trim_actor(cls, value):
        return value.strip()


class Proposal(GovernanceAction):
    action: Literal["add-note", "remove-metric"]
    rationale: str = Field(min_length=10, max_length=500)

    @field_validator("rationale", mode="before")
    @classmethod
    def strip_rationale(cls, value):
        return value.strip() if isinstance(value, str) else value


class Decision(GovernanceAction):
    decision: Literal["approve", "reject"]
    note: str = Field(min_length=10, max_length=500)

    @field_validator("note", mode="before")
    @classmethod
    def strip_note(cls, value):
        return value.strip() if isinstance(value, str) else value


def catalog_item(store, product_id):
    product = PRODUCTS[product_id]
    current = store.current(product_id)
    age = None
    if current:
        age = round((datetime.now(UTC) - datetime.fromisoformat(current["finished_at"])).total_seconds() / 3600, 2)
    freshness = "pending" if age is None else ("fresh" if age < product["freshness_hours"] else "stale")
    return {**product, "freshness": freshness, "age_hours": age, "publication": current,
            "approved_version": store.active(product_id)["version"]}


def require_product(product_id):
    if product_id not in PRODUCTS:
        raise HTTPException(404, "Unknown data product.")


def require_snapshot(store, product_id):
    require_product(product_id)
    snapshot = store.current(product_id)
    if snapshot is None:
        raise HTTPException(404, "This product has no accepted snapshot yet.")
    return snapshot


def create_app(root=None):
    @asynccontextmanager
    async def lifespan(app):
        Store(root).init()
        yield

    app = FastAPI(title="Enterprise Data Hub", version="2.0.0", lifespan=lifespan,
                  description="Synthetic data products, local publications and simulated governance approvals.")
    app.mount("/static", StaticFiles(directory=PACKAGE / "static"), name="static")

    @app.exception_handler(Conflict)
    async def conflict(_request: Request, exception: Conflict):
        return JSONResponse({"detail": str(exception)}, status_code=409)

    @app.exception_handler(Forbidden)
    async def forbidden(_request: Request, exception: Forbidden):
        return JSONResponse({"detail": str(exception)}, status_code=403)

    @app.get("/", include_in_schema=False)
    def home():
        return FileResponse(PACKAGE / "static/index.html")

    @app.get("/health", tags=["Platform"])
    def health():
        with Store(root).connection() as db:
            db.execute("SELECT 1 FROM current_snapshot LIMIT 1")
        return {"status": "ok"}

    @app.get("/api/actors", tags=["Governance"])
    def actors():
        return ACTORS

    @app.get("/api/delivery", tags=["Platform"])
    def delivery():
        return json.loads((PACKAGE / "contracts/delivery.json").read_text(encoding="utf-8"))

    @app.get("/api/products", tags=["Catalogue"])
    def products():
        store = Store(root)
        return [catalog_item(store, product_id) for product_id in PRODUCTS]

    @app.get("/api/overview", tags=["Platform"])
    def overview():
        store = Store(root)
        items = [catalog_item(store, product_id) for product_id in PRODUCTS]
        latest = store.runs(6)
        alerts = store.alerts()
        reliability = items[0]["publication"]
        return {
            "products": items, "runs": latest, "active_alerts": sum(a["status"] != "resolved" for a in alerts),
            "fresh_count": sum(item["freshness"] == "fresh" for item in items),
            "published_rows": sum(item["publication"]["metadata"]["row_count"] for item in items if item["publication"]),
            "trend": trend(store, reliability) if reliability else [],
        }

    @app.get("/api/products/{product_id}", tags=["Catalogue"])
    def product(product_id: str):
        require_product(product_id)
        store = Store(root)
        item = catalog_item(store, product_id)
        snapshot = item["publication"]
        dependents = [{"id": p["id"], "name": p["name"]} for p in PRODUCTS.values()
                      if p["id"] != product_id and p["source"] == item["source"]]
        return {**item, "contract": store.active(product_id),
                "published_contract": store.contract(product_id, snapshot["version"]) if snapshot else None,
                "trend": trend(store, snapshot) if snapshot else [],
                "lineage": {
                    "stages": ["Source", "Bronze", "Silver", "Gold", "Serving"],
                    "events": store.events(snapshot["id"]) if snapshot else [],
                    "shared_with": dependents,
                }}

    @app.get("/api/products/{product_id}/contracts/{version}", tags=["Governance"])
    def contract(product_id: str, version: str):
        require_product(product_id)
        record = Store(root).contract(product_id, version)
        if not record:
            raise HTTPException(404, "Unknown approved contract version.")
        return record

    @app.get("/api/products/{product_id}/data", tags=["Serving"])
    def preview(product_id: str, limit: int = Query(30, ge=1, le=250),
                dimension: str | None = Query(None, max_length=60), period: date | None = None):
        store = Store(root)
        snapshot = require_snapshot(store, product_id)
        return {"version": snapshot["version"], "publication_id": snapshot["id"],
                **read_publication(store, snapshot, limit, dimension, period)}

    @app.get("/api/products/{product_id}/download", tags=["Serving"])
    def download(product_id: str, dimension: str | None = Query(None, max_length=60), period: date | None = None):
        store = Store(root)
        snapshot = require_snapshot(store, product_id)
        data = read_publication(store, snapshot, None, dimension, period)
        output = StringIO()
        writer = csv.DictWriter(output, fieldnames=data["columns"])
        writer.writeheader()
        writer.writerows(data["rows"])
        return Response(output.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{product_id}-v{snapshot["version"]}.csv"',
                                 "X-Publication-Id": str(snapshot["id"])})

    @app.get("/api/snowflake/{product_id}/data", tags=["Snowflake"])
    def snowflake_preview(product_id: str, limit: int = Query(30, ge=1, le=250),
                          dimension: str | None = Query(None, max_length=60), period: date | None = None):
        """Opt-in cloud consumer. Fails closed rather than returning local demo rows."""
        require_product(product_id)
        from .snowflake_reader import CloudNotConfigured, read_secure_view
        try:
            return read_secure_view(product_id, limit, dimension, period)
        except CloudNotConfigured as exc:
            raise HTTPException(503, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/api/runs", tags=["Operations"])
    def runs():
        return Store(root).runs()

    @app.get("/api/runs/{run_id}", tags=["Operations"])
    def run_detail(run_id: int):
        store = Store(root)
        run = store.run(run_id)
        if not run:
            raise HTTPException(404, "Unknown pipeline run.")
        return {**run, "events": store.events(run_id)}

    @app.post("/api/runs", status_code=201, tags=["Operations"])
    def start_run(request: RunRequest):
        require_product(request.product_id)
        require_role(request.actor, "operator")
        store = Store(root)
        return launch(store, request.product_id, request.scenario, request.actor)

    @app.get("/api/alerts", tags=["Operations"])
    def alerts():
        store = Store(root)
        items = [catalog_item(store, pid) for pid in PRODUCTS]
        freshness = [{"product_id": item["id"], "status": item["freshness"], "owner": item["owner"],
                      "age_hours": item["age_hours"], "target_hours": item["freshness_hours"]}
                     for item in items if item["freshness"] != "fresh"]
        return {"quality": store.alerts(), "freshness": freshness}

    @app.post("/api/alerts/{alert_id}/acknowledge", tags=["Operations"])
    def acknowledge(alert_id: int, request: Action):
        return Store(root).acknowledge(alert_id, request.actor)

    @app.get("/api/products/{product_id}/changes", tags=["Governance"])
    def changes(product_id: str):
        require_product(product_id)
        return Store(root).changes(product_id)

    @app.post("/api/products/{product_id}/changes", status_code=201, tags=["Governance"])
    def propose(product_id: str, request: Proposal):
        require_product(product_id)
        return Store(root).propose(product_id, request.actor, request.action, request.rationale)

    @app.post("/api/changes/{change_id}/decision", tags=["Governance"])
    def decide(change_id: int, request: Decision):
        return Store(root).decide(change_id, request.actor, request.decision, request.note)

    return app


app = create_app()
