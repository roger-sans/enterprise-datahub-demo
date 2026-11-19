"""Generate reproducible synthetic RAW events for a native Snowflake pipeline.

Snowflake owns Silver, Gold and Serving in the cloud path. This module never
asserts that a cloud account has been used or that a task has been activated.
"""
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4
from .catalog import PRODUCTS
from .synthetic import source_rows

def export_source(product_id: str, directory: Path, scenario: str = "healthy") -> Path:
    if product_id not in PRODUCTS:
        raise ValueError("Unknown data product.")
    if scenario not in ("healthy", "negative-money"):
        raise ValueError("Unknown source scenario.")
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    source = PRODUCTS[product_id]["source"]
    rows = source_rows(source, scenario)
    # Every staging attempt has a unique batch identity; fixture content is stable.
    batch_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f") + "_" + uuid4().hex[:8]
    slug = "dispatch" if source == "Dispatch events" else "returns"
    artifact = directory / f"{slug}-{batch_id}.jsonl"
    lines = [
        json.dumps({
            "source_id": source, "batch_id": batch_id,
            "payload": {**row, "source_row": index},
        }, separators=(",", ":"), sort_keys=True)
        for index, row in enumerate(rows, 1)
    ]
    artifact.write_text("\n".join(lines) + "\n", encoding="utf-8")
    payload_hash = sha256(artifact.read_bytes()).hexdigest()
    manifest = {
        "product_id": product_id, "source_id": source, "scenario": scenario,
        "batch_id": batch_id, "rows": len(rows),
        "source_file": artifact.name, "sha256": payload_hash,
        "origin": "fully-synthetic-local-generator",
        "snowflake_execution": "not_executed",
    }
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    source_path = ("file://" + artifact.as_posix()).replace("'", "''")
    script = f"""-- Generated for a dedicated Snowflake sandbox; never run against enterprise accounts.
-- Execute snowflake/01_bootstrap.sql and snowflake/03_native_pipeline.sql first.
USE ROLE EDH_PUBLISHER;
USE SECONDARY ROLES NONE;
USE WAREHOUSE EDH_DEMO_WH;
USE DATABASE EDH_DEMO;
ALTER SESSION SET QUERY_TAG = 'edh-synthetic-raw-ingest';
PUT '{source_path}' @EDH_DEMO.RAW.SYNTHETIC_EVENTS AUTO_COMPRESS = FALSE OVERWRITE = FALSE;
COPY INTO EDH_DEMO.RAW.EVENTS (SOURCE_ID, BATCH_ID, PAYLOAD, SOURCE_FILE, SOURCE_ROW)
FROM (
    SELECT $1:source_id::VARCHAR, $1:batch_id::VARCHAR, $1:payload,
           METADATA$FILENAME, METADATA$FILE_ROW_NUMBER
    FROM @EDH_DEMO.RAW.SYNTHETIC_EVENTS/{artifact.name}
)
FILE_FORMAT = (FORMAT_NAME = EDH_DEMO.RAW.JSON_LINES)
ON_ERROR = ABORT_STATEMENT;
CALL EDH_DEMO.GOVERNANCE.PUBLISH_PRODUCT('{product_id}', '{batch_id}');
-- A BLOCKED result is not acceptance; inspect EDH_DEMO.GOVERNANCE.PUBLICATION_AUDIT.
"""
    sql_path = directory / "load.sql"
    sql_path.write_text(script, encoding="utf-8")
    return sql_path
