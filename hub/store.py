"""Local catalogue, publication pointer, change approvals and operational journal."""

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from .catalog import ACTORS, BASE_CONTRACTS, OPTIONAL_FIELD, PRODUCTS, compatibility


class Conflict(Exception):
    pass


class Forbidden(Exception):
    pass


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def require_role(actor: str, role: str) -> None:
    if ACTORS.get(actor, {}).get("role") != role:
        raise Forbidden(f"This action requires the simulated {role} role.")


class Store:
    def __init__(self, root: Path | str | None = None):
        self.root = Path(root or os.environ.get("HUB_STATE", ".state")).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connection(self, write: bool = False):
        connection = sqlite3.connect(self.root / "metadata.db", timeout=20)
        connection.row_factory = sqlite3.Row
        try:
            if write:
                connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def init(self):
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS contracts (
                    product_id TEXT, version TEXT, body TEXT,
                    PRIMARY KEY(product_id, version)
                );
                CREATE TABLE IF NOT EXISTS active_contract (
                    product_id TEXT PRIMARY KEY, version TEXT
                );
                CREATE TABLE IF NOT EXISTS changes (
                    id INTEGER PRIMARY KEY, product_id TEXT, base_version TEXT,
                    candidate_version TEXT, body TEXT, findings TEXT,
                    rationale TEXT, status TEXT, author TEXT, reviewer TEXT,
                    decision TEXT, submitted_at TEXT, decided_at TEXT
                );
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, product_id TEXT, version TEXT,
                    scenario TEXT, actor TEXT, dagster_id TEXT, status TEXT,
                    started_at TEXT, finished_at TEXT, metadata TEXT DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY, run_id INTEGER, stage TEXT, status TEXT,
                    occurred_at TEXT, details TEXT
                );
                CREATE TABLE IF NOT EXISTS current_snapshot (
                    product_id TEXT PRIMARY KEY, run_id INTEGER
                );
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY, product_id TEXT, run_id INTEGER,
                    stage TEXT, severity TEXT, status TEXT, raised_at TEXT,
                    acknowledged_by TEXT, resolved_at TEXT
                );
            """)
        with self.connection(write=True) as db:
            for product_id, contract in BASE_CONTRACTS.items():
                db.execute("INSERT OR IGNORE INTO contracts VALUES (?, ?, ?)",
                           (product_id, contract["version"], json.dumps(contract)))
                db.execute("INSERT OR IGNORE INTO active_contract VALUES (?, ?)",
                           (product_id, contract["version"]))

    def active(self, product_id: str, db=None) -> dict:
        if db is None:
            with self.connection() as connection:
                return self.active(product_id, connection)
        row = db.execute("""
            SELECT body FROM contracts JOIN active_contract USING(product_id, version)
            WHERE product_id = ?
        """, (product_id,)).fetchone()
        return json.loads(row["body"])

    def contract(self, product_id: str, version: str) -> dict | None:
        with self.connection() as db:
            row = db.execute("SELECT body FROM contracts WHERE product_id = ? AND version = ?",
                             (product_id, version)).fetchone()
        return json.loads(row["body"]) if row else None

    def start(self, product_id: str, scenario: str, actor: str, dagster_id: str):
        require_role(actor, "operator")
        with self.connection(write=True) as db:
            contract = self.active(product_id, db)
            run_id = db.execute("""
                INSERT INTO runs(product_id, version, scenario, actor, dagster_id, status, started_at)
                VALUES (?, ?, ?, ?, ?, 'running', ?)
            """, (product_id, contract["version"], scenario, actor, dagster_id, now())).lastrowid
        return run_id, contract

    def events(self, run_id: int):
        with self.connection() as db:
            rows = db.execute("SELECT * FROM events WHERE run_id = ? ORDER BY id", (run_id,)).fetchall()
        return [self.decode(row, "details") for row in rows]

    def record(self, run_id: int, stage: str, status: str, details: dict):
        with self.connection(write=True) as db:
            self.insert_event(db, run_id, stage, status, details, now())

    @staticmethod
    def insert_event(db, run_id, stage, status, details, timestamp):
        db.execute("""
            INSERT INTO events(run_id, stage, status, occurred_at, details) VALUES (?, ?, ?, ?, ?)
        """, (run_id, stage, status, timestamp, json.dumps(details)))

    def fail(self, run_id: int, stage: str, details: dict):
        timestamp = now()
        with self.connection(write=True) as db:
            result = db.execute("""
                UPDATE runs SET status = 'blocked', finished_at = ?
                WHERE id = ? AND status = 'running' RETURNING product_id
            """, (timestamp, run_id)).fetchone()
            if result:
                self.insert_event(db, run_id, stage, "failed", details, timestamp)
                db.execute("""
                    INSERT INTO alerts(product_id, run_id, stage, severity, status, raised_at)
                    VALUES (?, ?, ?, 'high', 'open', ?)
                """, (result["product_id"], run_id, stage, timestamp))
                db.execute("""
                    UPDATE alerts SET status = 'resolved', resolved_at = ?
                    WHERE product_id = ? AND run_id < ? AND status != 'resolved'
                      AND EXISTS (SELECT 1 FROM current_snapshot
                                  WHERE product_id = ? AND run_id > ?)
                """, (timestamp, result["product_id"], run_id + 1, result["product_id"], run_id))

    def publish(self, run_id: int, product_id: str, contract_version: str, metadata: dict):
        timestamp = now()
        with self.connection(write=True) as db:
            current = db.execute("SELECT run_id FROM current_snapshot WHERE product_id = ?",
                                 (product_id,)).fetchone()
            if (current and current["run_id"] >= run_id) or self.active(product_id, db)["version"] != contract_version:
                db.execute("UPDATE runs SET status = 'superseded', finished_at = ? WHERE id = ?",
                           (timestamp, run_id))
                self.insert_event(db, run_id, "Serving", "skipped",
                                  {"reason": "A newer run or approved contract took precedence."}, timestamp)
                return
            db.execute("UPDATE runs SET status = 'published', finished_at = ?, metadata = ? WHERE id = ?",
                       (timestamp, json.dumps(metadata), run_id))
            db.execute("""
                INSERT INTO current_snapshot VALUES (?, ?)
                ON CONFLICT(product_id) DO UPDATE SET run_id = excluded.run_id
            """, (product_id, run_id))
            db.execute("""
                UPDATE alerts SET status = 'resolved', resolved_at = ?
                WHERE product_id = ? AND run_id < ? AND status != 'resolved'
            """, (timestamp, product_id, run_id))
            self.insert_event(db, run_id, "Serving", "passed", metadata, timestamp)

    @staticmethod
    def decode(row, *fields):
        data = dict(row)
        for key in fields:
            data[key] = json.loads(data[key])
        return data

    def current(self, product_id: str) -> dict | None:
        with self.connection() as db:
            row = db.execute("""
                SELECT runs.* FROM current_snapshot ptr JOIN runs ON runs.id = ptr.run_id
                WHERE ptr.product_id = ?
            """, (product_id,)).fetchone()
        return self.decode(row, "metadata") if row else None

    def run(self, run_id: int):
        with self.connection() as db:
            row = db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return self.decode(row, "metadata") if row else None

    def run_for_dagster(self, dagster_id: str):
        with self.connection() as db:
            row = db.execute("SELECT * FROM runs WHERE dagster_id = ?", (dagster_id,)).fetchone()
        return self.decode(row, "metadata") if row else None

    def runs(self, limit: int = 60):
        with self.connection() as db:
            rows = db.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [self.decode(row, "metadata") for row in rows]

    def alerts(self):
        with self.connection() as db:
            rows = db.execute("SELECT * FROM alerts ORDER BY id DESC LIMIT 80").fetchall()
        return [dict(row) for row in rows]

    def acknowledge(self, alert_id: int, actor: str):
        require_role(actor, "operator")
        with self.connection(write=True) as db:
            row = db.execute("""
                UPDATE alerts SET status = 'acknowledged', acknowledged_by = ?
                WHERE id = ? AND status = 'open' RETURNING *
            """, (actor, alert_id)).fetchone()
            if row is None:
                raise Conflict("Only an open alert can be acknowledged.")
        return dict(row)

    def changes(self, product_id: str):
        with self.connection() as db:
            rows = db.execute("SELECT * FROM changes WHERE product_id = ? ORDER BY id DESC",
                              (product_id,)).fetchall()
        return [self.decode(row, "body", "findings") for row in rows]

    def propose(self, product_id: str, actor: str, action: str, rationale: str):
        require_role(actor, "owner")
        if PRODUCTS[product_id]["owner_actor"] != actor:
            raise Forbidden("Only the owning domain can propose changes to this product.")
        with self.connection(write=True) as db:
            previous = self.active(product_id, db)
            candidate = json.loads(json.dumps(previous))
            if action == "add-note":
                if OPTIONAL_FIELD["name"] in [f["name"] for f in previous["fields"]]:
                    raise Conflict("This optional field is already in the approved contract.")
                candidate["fields"].append(OPTIONAL_FIELD)
            else:
                candidate["fields"].pop(3)
            major, minor, _ = map(int, previous["version"].split("."))
            candidate["version"] = f"{major}.{minor + 1}.0"
            findings = compatibility(previous, candidate)
            row = db.execute("""
                INSERT INTO changes(product_id, base_version, candidate_version, body, findings,
                                    rationale, status, author, submitted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING *
            """, (product_id, previous["version"], candidate["version"], json.dumps(candidate),
                  json.dumps(findings), rationale, "blocked" if findings else "pending", actor, now())).fetchone()
        return self.decode(row, "body", "findings")

    def decide(self, change_id: int, actor: str, decision: str, note: str):
        require_role(actor, "steward")
        with self.connection(write=True) as db:
            change = db.execute("SELECT * FROM changes WHERE id = ?", (change_id,)).fetchone()
            if not change or change["status"] != "pending" or change["author"] == actor:
                raise Conflict("This proposal is unavailable for independent review.")
            product_id = change["product_id"]
            if decision == "approve":
                previous = self.active(product_id, db)
                candidate = json.loads(change["body"])
                if previous["version"] != change["base_version"] or compatibility(previous, candidate):
                    raise Conflict("The approved contract moved. Reject this proposal and start a new review.")
                db.execute("INSERT INTO contracts VALUES (?, ?, ?)",
                           (product_id, change["candidate_version"], change["body"]))
                db.execute("UPDATE active_contract SET version = ? WHERE product_id = ?",
                           (change["candidate_version"], product_id))
            row = db.execute("""
                UPDATE changes SET reviewer = ?, status = ?, decision = ?, decided_at = ?
                WHERE id = ? RETURNING *
            """, (actor, "approved" if decision == "approve" else "rejected", note, now(), change_id)).fetchone()
        return self.decode(row, "body", "findings")

    def artifact(self, run_id: int, layer: str) -> Path:
        suffix = "jsonl" if layer == "bronze" else "parquet"
        return self.root / "snapshots" / f"{run_id:06d}" / f"{layer}.{suffix}"
