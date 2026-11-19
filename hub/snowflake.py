"""Build a Snowflake sandbox load from a locally accepted Parquet publication."""

import json
from hashlib import sha256
from pathlib import Path
from shutil import copyfile

from .catalog import BASE_CONTRACTS
from .lakehouse import hash_file, read_publication

TYPE_SQL = {"date": "DATE", "string": "VARCHAR", "integer": "NUMBER(38,0)", "decimal": "NUMBER(18,2)"}
MEASURES = {
    "shipment-reliability": ("shipment_count", "on_time_count"),
    "freight-spend": ("shipment_count", "freight_cents"),
    "returns-pulse": ("return_count", "refund_cents"),
}


def export(store, product_id, directory: Path):
    snapshot = store.current(product_id)
    if snapshot is None:
        raise ValueError("Seed the product before exporting to Snowflake.")
    current = store.artifact(snapshot["id"], "serving")
    digest = hash_file(current)
    if digest != snapshot["metadata"]["snapshot_digest"]:
        raise ValueError("The Serving artifact no longer matches its accepted digest.")
    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    key = sha256(f"{product_id}:{snapshot['version']}:{snapshot['id']}:{digest}:{snapshot['finished_at']}".encode()).hexdigest()
    artifact = directory / f"{product_id}-{key}.parquet"
    copyfile(current, artifact)
    records = read_publication(store, snapshot, None)["rows"]
    expected = {measure: sum(row[measure] for row in records) for measure in MEASURES[product_id]}
    manifest = {
        "product_id": product_id, "contract_version": snapshot["version"], "publication_key": key,
        "local_run": snapshot["id"], "published_at": snapshot["finished_at"],
        "source_sha256": snapshot["metadata"]["source_digest"], "parquet_sha256": digest,
        "rows": len(records), "totals": expected, "file": artifact.name,
    }
    if manifest["rows"] != snapshot["metadata"]["row_count"]:
        raise ValueError("The Serving file fails the recorded row count.")
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (directory / "load.sql").write_text(load_sql(artifact, manifest), encoding="utf-8")
    return directory / "load.sql"


def load_sql(artifact, manifest):
    product = manifest["product_id"]
    c = BASE_CONTRACTS[product]
    table = product.replace("-", "_").upper()
    base_columns = [field["name"].upper() for field in c["fields"]]
    all_columns = ", ".join([*base_columns, "REPORTING_NOTE"])
    ddl = ",\n    ".join(f"{field['name'].upper()} {TYPE_SQL[field['type']]}" for field in c["fields"])
    key_group = ", ".join(key.upper() for key in c["primary_key"])
    nulls = " OR ".join(f"{field['name'].upper()} IS NULL" for field in c["fields"] if field["required"])
    sums = " OR ".join(f"COALESCE(SUM({key.upper()}), -1) <> {value}" for key, value in manifest["totals"].items())
    version = manifest["contract_version"]
    key = manifest["publication_key"]
    uri = ("file://" + artifact.as_posix()).replace("'", "''")
    finished = manifest["published_at"]
    return f"""-- Generated from a validated synthetic Serving snapshot.
USE ROLE EDH_PUBLISHER;
USE SECONDARY ROLES NONE;
USE WAREHOUSE EDH_DEMO_WH;
USE DATABASE EDH_DEMO;
ALTER SESSION SET WEEK_START = 1, QUERY_TAG = 'edh-synthetic-load';

PUT '{uri}' @EDH_DEMO.LANDING.SYNTHETIC_UPLOAD AUTO_COMPRESS = FALSE OVERWRITE = FALSE;

CREATE OR REPLACE TEMPORARY TABLE EDH_DEMO.LANDING.CANDIDATE_{table} (
    {ddl},
    REPORTING_NOTE VARCHAR
);
COPY INTO EDH_DEMO.LANDING.CANDIDATE_{table}
FROM @EDH_DEMO.LANDING.SYNTHETIC_UPLOAD
FILES = ('{artifact.name}')
FILE_FORMAT = (TYPE = PARQUET)
MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
ON_ERROR = ABORT_STATEMENT
FORCE = TRUE;

EXECUTE IMMEDIATE $$
DECLARE
  failures INTEGER;
  rejected EXCEPTION (-20001, 'Snowflake candidate failed its publication gate');
  existing INTEGER;
BEGIN
  BEGIN TRANSACTION;
  SELECT COUNT(*) INTO :failures
    FROM (SELECT COUNT(*) AS CANDIDATE_ROWS FROM EDH_DEMO.LANDING.CANDIDATE_{table}
          HAVING COUNT(*) <> {manifest['rows']} OR {sums}
             OR COUNT_IF({nulls}) > 0
          UNION ALL
          SELECT COUNT(*) AS CANDIDATE_ROWS FROM EDH_DEMO.LANDING.CANDIDATE_{table}
          GROUP BY {key_group} HAVING COUNT(*) > 1);
  IF (failures > 0) THEN
    RAISE rejected;
  END IF;

  SELECT COUNT(*) INTO :existing FROM EDH_DEMO.CURATED.{table} WHERE PUBLICATION_KEY = '{key}';
  IF (existing = 0) THEN
    INSERT INTO EDH_DEMO.CURATED.{table} (PUBLICATION_KEY, {all_columns})
      SELECT '{key}', {all_columns} FROM EDH_DEMO.LANDING.CANDIDATE_{table};
  END IF;
  MERGE INTO EDH_DEMO.CURATED.CURRENT_PUBLICATION t
  USING (SELECT '{product}' AS PRODUCT_ID, '{key}' AS PUBLICATION_KEY,
                '{version}' AS CONTRACT_VERSION, {manifest['local_run']} AS LOCAL_RUN,
                TO_TIMESTAMP_TZ('{finished}') AS ACCEPTED_AT,
                '{manifest['source_sha256']}' AS SOURCE_SHA256,
                '{manifest['parquet_sha256']}' AS PARQUET_SHA256) s
  ON t.PRODUCT_ID = s.PRODUCT_ID
  WHEN MATCHED AND (s.ACCEPTED_AT > t.ACCEPTED_AT OR
     (s.ACCEPTED_AT = t.ACCEPTED_AT AND s.LOCAL_RUN > t.LOCAL_RUN))
    THEN UPDATE SET PUBLICATION_KEY = s.PUBLICATION_KEY, CONTRACT_VERSION = s.CONTRACT_VERSION,
        LOCAL_RUN = s.LOCAL_RUN, ACCEPTED_AT = s.ACCEPTED_AT, SOURCE_SHA256 = s.SOURCE_SHA256,
        PARQUET_SHA256 = s.PARQUET_SHA256
  WHEN NOT MATCHED THEN INSERT (PRODUCT_ID, PUBLICATION_KEY, CONTRACT_VERSION, LOCAL_RUN,
      ACCEPTED_AT, SOURCE_SHA256, PARQUET_SHA256)
    VALUES (s.PRODUCT_ID, s.PUBLICATION_KEY, s.CONTRACT_VERSION, s.LOCAL_RUN,
      s.ACCEPTED_AT, s.SOURCE_SHA256, s.PARQUET_SHA256);
  COMMIT;
EXCEPTION
  WHEN OTHER THEN
    ROLLBACK;
    RAISE;
END;
$$;
"""
