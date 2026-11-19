"""Opt-in, read-only Snowflake secure-view consumer.

A named connection is resolved by Snowflake Connector from connections.toml;
no credentials, roles or account identifiers are stored in the repository.
"""
from datetime import date
from decimal import Decimal
import os
from .catalog import BASE_CONTRACTS, PRODUCTS

VIEWS = {
    "shipment-reliability": ("SHIPMENT_RELIABILITY_V1", "REGION"),
    "freight-spend": ("FREIGHT_SPEND_V1", "REGION"),
    "returns-pulse": ("RETURNS_PULSE_V1", "CHANNEL"),
}

class CloudNotConfigured(Exception):
    pass

def read_secure_view(product_id: str, limit: int = 50,
                     dimension: str | None = None, period: date | None = None):
    """Return only the selected product view, never RAW or curated tables."""
    if product_id not in PRODUCTS:
        raise ValueError("Unknown data product.")
    if not 1 <= limit <= 250:
        raise ValueError("Invalid row limit.")
    connection_name = os.getenv("HUB_SNOWFLAKE_CONNECTION")
    if not connection_name:
        raise CloudNotConfigured("Set HUB_SNOWFLAKE_CONNECTION to a named, reader-scoped Snowflake connection.")
    try:
        import snowflake.connector
    except ImportError as exc:
        raise CloudNotConfigured("Install the optional snowflake dependency before cloud reads.") from exc
    view, dimension_key = VIEWS[product_id]
    sql = f"SELECT * FROM EDH_DEMO.SERVING.{view}"
    clauses, params = [], []
    if dimension is not None:
        clauses.append(f"{dimension_key} = %s")
        params.append(dimension)
    if period is not None:
        clauses.append("PERIOD_START = %s")
        params.append(period.isoformat())
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    contract = BASE_CONTRACTS[product_id]
    order = ", ".join(name.upper() for name in contract["primary_key"])
    sql += f" ORDER BY {order} LIMIT %s"
    params.append(limit)
    with snowflake.connector.connect(connection_name=connection_name) as conn:
        with conn.cursor() as cursor:
            cursor.execute("USE SECONDARY ROLES NONE")
            cursor.execute(sql, params)
            fetched = cursor.fetchall()
            returned_columns = [column[0].lower() for column in cursor.description]
    expected_columns = [field["name"] for field in contract["fields"]]
    if returned_columns != expected_columns:
        raise ValueError("Snowflake secure-view columns do not match the v1 product contract.")
    rows = []
    for row in fetched:
        record = {}
        for name, value in zip(returned_columns, row, strict=True):
            if isinstance(value, (date,)):
                value = value.isoformat()
            elif isinstance(value, Decimal):
                value = float(value) if value.as_tuple().exponent < 0 else int(value)
            record[name] = value
        rows.append(record)
    return {"product_id": product_id, "version": "1.0.0", "columns": expected_columns,
            "rows": rows, "returned": len(rows), "limit": limit,
            "source": "Snowflake secure view (reader role)", "filters": {"dimension": dimension, "period": str(period) if period else None}}
