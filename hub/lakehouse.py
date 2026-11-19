"""Materialise immutable demo objects and evaluate publication gates."""

from datetime import date, datetime
from decimal import Decimal
from hashlib import file_digest
import json

import duckdb

from .catalog import PRODUCTS, SOURCE_COLUMNS, sql_for


def hash_file(path) -> str:
    with path.open("rb") as source:
        return file_digest(source, "sha256").hexdigest()


def bronze(store, run_id, rows):
    path = store.artifact(run_id, "bronze")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        for ordinal, row in enumerate(rows, 1):
            handle.write(json.dumps({**row, "source_row": ordinal}, separators=(",", ":")) + "\n")
    return {"rows": len(rows), "sha256": hash_file(path), "bytes": path.stat().st_size}


def silver(store, run_id, source):
    source_path = store.artifact(run_id, "bronze")
    target = store.artifact(run_id, "silver")
    with duckdb.connect(config={"threads": "2"}) as db:
        db.read_json(str(source_path), format="newline_delimited").create_view("bronze")
        db.sql(sql_for("dispatch-silver" if source == "Dispatch events" else "returns-silver")).write_parquet(str(target))
        received, distinct = db.execute("SELECT COUNT(*), COUNT(DISTINCT ref) FROM bronze").fetchall()[0]
        count = db.read_parquet(str(target)).count("*").fetchall()[0][0]
    return {"rows": count, "revisions_collapsed": received - count, "expected_rows": distinct,
            "columns": SOURCE_COLUMNS[source]}


def check_result(name, observed, expected, passed):
    return {"name": name, "observed": observed, "expected": expected, "passed": passed}


def silver_checks(store, run_id, product, counts):
    returns = product["source"] == "Return events"
    with duckdb.connect(config={"threads": "2"}) as db:
        db.read_parquet(str(store.artifact(run_id, "silver"))).create_view("silver")
        if returns:
            invalid_money, invalid_domain = db.execute("""
                SELECT COUNT(*) FILTER (WHERE refund_cents IS NULL OR refund_cents < 0),
                       COUNT(*) FILTER (WHERE opened_on IS NULL OR channel IS NULL OR reason IS NULL
                             OR channel NOT IN ('web','store','partner')
                             OR reason NOT IN ('Damaged','Wrong item','Unwanted','Late arrival'))
                FROM silver
            """).fetchall()[0]
        else:
            invalid_money, invalid_domain = db.execute("""
                SELECT COUNT(*) FILTER (WHERE freight_cents IS NULL OR freight_cents < 0),
                       COUNT(*) FILTER (WHERE sent_on IS NULL OR promised_on IS NULL
                             OR region IS NULL OR carrier IS NULL OR carrier = ''
                             OR region NOT IN ('NORTH','WEST','CENTRAL','COASTAL')
                             OR promised_on < sent_on OR delivered_on < sent_on)
                FROM silver
            """).fetchall()[0]
    return [
        check_result("Non-empty source", counts["rows"], "> 0", counts["rows"] > 0),
        check_result("One row per source reference", counts["rows"], counts["expected_rows"],
                     counts["rows"] == counts["expected_rows"]),
        check_result("Non-negative monetary amount", invalid_money, 0, invalid_money == 0),
        check_result("Valid business attributes", invalid_domain, 0, invalid_domain == 0),
    ]


def gold(store, run_id, product_id, contract):
    source_path = store.artifact(run_id, "silver")
    target = store.artifact(run_id, "gold")
    with duckdb.connect(config={"threads": "2"}) as db:
        db.read_parquet(str(source_path)).create_view("silver")
        model = db.sql(sql_for(product_id))
        if any(field["name"] == "reporting_note" for field in contract["fields"]):
            model = model.project("*, CAST(NULL AS VARCHAR) AS reporting_note")
        model.write_parquet(str(target))
    return {"sha256": hash_file(target)}


def normalise(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def gold_checks(store, run_id, product_id, contract):
    expected_fields = [field["name"] for field in contract["fields"]]
    required = [field["name"] for field in contract["fields"] if field["required"]]
    key = ", ".join(contract["primary_key"])
    predicate = " OR ".join(f"{field} IS NULL" for field in required)
    sql_types = {"date": "DATE", "string": "VARCHAR", "integer": "BIGINT", "decimal": "DECIMAL"}
    rules = {
        "shipment-reliability": ("COUNT(delivered_on)",
                                 "COUNT(*) FILTER (WHERE delivered_on <= promised_on)",
                                 "SUM(shipment_count)", "SUM(on_time_count)",
                                 "on_time_count > shipment_count OR on_time_pct NOT BETWEEN 0 AND 100"),
        "freight-spend": ("COUNT(*)", "SUM(freight_cents)", "SUM(shipment_count)", "SUM(freight_cents)",
                          "avg_cost_eur < 0 OR shipment_count < 1"),
        "returns-pulse": ("COUNT(*)", "SUM(refund_cents)", "SUM(return_count)", "SUM(refund_cents)",
                          "return_count < 1 OR refund_cents < 0"),
    }
    source_count, source_measure, gold_count, gold_measure, domain_rule = rules[product_id]
    with duckdb.connect(config={"threads": "2"}) as db:
        db.read_parquet(str(store.artifact(run_id, "silver"))).create_view("silver")
        db.read_parquet(str(store.artifact(run_id, "gold"))).create_view("gold")
        cols = db.sql("DESCRIBE gold").fetchall()
        fields = [col[0] for col in cols]
        types = [col[1].split("(")[0] for col in cols]
        expected_types = [sql_types[field["type"]] for field in contract["fields"]]
        checks = [check_result("Published field order", fields, expected_fields, fields == expected_fields),
                  check_result("Published value types", types, expected_types, types == expected_types)]
        if fields != expected_fields or types != expected_types:
            return checks, 0
        rows, keys, nulls, invalid, entries, measure = db.execute(f"""
            SELECT COUNT(*), COUNT(DISTINCT ({key})), COUNT(*) FILTER (WHERE {predicate}),
                   COUNT(*) FILTER (WHERE {domain_rule}), {gold_count}, {gold_measure}
            FROM gold
        """).fetchall()[0]
        expected_count, expected_measure = db.execute(f"SELECT {source_count}, {source_measure} FROM silver").fetchall()[0]
    checks.extend([
        check_result("Non-empty publication", rows, "> 0", rows > 0),
        check_result("Unique contract grain", keys, rows, rows == keys),
        check_result("Required fields populated", nulls, 0, nulls == 0),
        check_result("Valid aggregate ranges", invalid, 0, invalid == 0),
        check_result("Reconcile event counts", entries, expected_count, entries == expected_count),
        check_result("Reconcile measure with Silver", measure, expected_measure, measure == expected_measure),
    ])
    return checks, rows


def read_publication(store, snapshot, limit=50, dimension=None, period=None):
    product_id = snapshot["product_id"]
    contract = store.contract(product_id, snapshot["version"])
    columns = [field["name"] for field in contract["fields"]]
    dimension_col = contract["primary_key"][1]
    path = store.artifact(snapshot["id"], "serving")
    with duckdb.connect(config={"threads": "2"}) as db:
        db.read_parquet(str(path)).create_view("published")
        clauses, params = [], []
        if dimension is not None:
            clauses.append(f"{dimension_col} = ?")
            params.append(dimension)
        if period is not None:
            clauses.append("period_start = ?")
            params.append(period)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        total = db.execute(f"SELECT COUNT(*) FROM published{where}", params).fetchall()[0][0]
        statement = f"SELECT * FROM published{where} ORDER BY " + ", ".join(contract["primary_key"])
        if limit is not None:
            statement += " LIMIT ?"
            params.append(limit)
        rows = db.execute(statement, params).fetchall()
        dimensions = db.sql(f"SELECT DISTINCT {dimension_col} FROM published ORDER BY 1").fetchall()
        periods = db.sql("SELECT DISTINCT period_start FROM published ORDER BY 1 DESC").fetchall()
    return {"columns": columns, "rows": [dict(zip(columns, map(normalise, row), strict=True)) for row in rows],
            "total": total, "filters": {"dimension": dimension_col, "values": [r[0] for r in dimensions],
                                       "periods": [normalise(r[0]) for r in periods]}}


def trend(store, snapshot):
    path = store.artifact(snapshot["id"], "serving")
    measure = {
        "shipment-reliability": "ROUND(100.0 * SUM(on_time_count) / NULLIF(SUM(shipment_count), 0), 1)",
        "freight-spend": "ROUND(SUM(freight_cents) / 100.0, 2)",
        "returns-pulse": "SUM(return_count)",
    }[snapshot["product_id"]]
    with duckdb.connect(config={"threads": "2"}) as db:
        db.read_parquet(str(path)).create_view("published")
        values = db.sql(f"SELECT period_start, {measure} FROM published GROUP BY 1 ORDER BY 1").fetchall()
    return [{"period": normalise(period), "value": normalise(value)} for period, value in values]
