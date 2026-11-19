# Snowflake sandbox acceptance

The local platform is self-contained. This optional sandbox path transfers only an accepted synthetic Serving snapshot. The export checks the artifact digest and produces Parquet, the row-and-total manifest and a Snowflake load script with an exact staged file. The bootstrap creates an independent database, a warehouse, an internal stage, role-scoped secure views and a curated publication registry.

## Run the sandbox

Use a sandbox identity entitled to `SECURITYADMIN` and `SYSADMIN` for initial creation. An administrator needs to assign the applicable `EDH_PUBLISHER` or reader role to the actual Snowflake user(s). Select an existing named connection with Snowflake CLI. Specify an account separate from operational workloads.

```bash
python -m hub seed
snow sql --connection edh-sandbox -f snowflake/01_bootstrap.sql
python -m hub snowflake-export shipment-reliability exports/shipment-reliability
python -m hub snowflake-export freight-spend exports/freight-spend
python -m hub snowflake-export returns-pulse exports/returns-pulse
snow sql --connection edh-sandbox -f exports/shipment-reliability/load.sql
snow sql --connection edh-sandbox -f exports/freight-spend/load.sql
snow sql --connection edh-sandbox -f exports/returns-pulse/load.sql
```

The generated script uses a local path for `PUT`. Generate it on the machine from which Snowflake CLI will run. Use separate reader connections for the queries in [02_verify.sql](../snowflake/02_verify.sql). Bootstrap creates the reader roles through `SECURITYADMIN`. Validate reader denials on users with only the role under test and use `USE SECONDARY ROLES NONE`.

A typed temporary table receives the Parquet projection. The SQL gate checks required values, primary-key grain, row count and reconciled totals before an explicit transaction inserts an immutable curated snapshot and moves the product pointer forward. Serialize one publisher per product for this sandbox. Stable `*_V1` views expose the baseline fields, while `*_V1_1` exposes the optional annotation once that version is loaded. Snowflake stores a copy of Serving. Dagster and DuckDB remain responsible for local Bronze, Silver and Gold.

| Acceptance | How to prove it | Required evidence |
| --- | --- | --- |
| Parity | Compare `manifest.json` with the corresponding reader test. Verify sampled aggregate values and key uniqueness. | Exact rows, totals and sampled keys for all three products. |
| Schema evolution | Approve the optional field locally, refresh and export the accepted v1.1 snapshot. Run both secure view queries. | Stable V1 projection and the additional nullable column in V1_1. |
| Negative access | As Finance, run individually the denial probes in `02_verify.sql`. | Finance can read Freight Spend and cannot read curated data, the stage or another product’s view. |
| Negative load and repeat | In a sandbox copy of `load.sql`, change the expected row count and execute. Then replay a fresh export twice. | The rejected load leaves the prior pointer intact. An identical accepted load is idempotent under the serial-publisher assumption. |
| Cost envelope | Tag the load with `edh-synthetic-load`, confirm auto-suspend and review warehouse metering against a Finance-approved cap. | Observed credits per accepted refresh and approved cap. Use a resource monitor before a scheduled pilot. |
| Recovery | Re-export an accepted snapshot from a verified local artifact, upload, compare parity and repeat access probes. | Validated restoration procedure and elapsed recovery time. |

**Verification status:** Python tests validate local export, checksums and the shared transformations’ Snowflake SQL parsing. Cloud bootstrap, load execution, role enforcement and credit consumption still require validation in an actual account.

References: [COPY INTO](https://docs.snowflake.com/en/sql-reference/sql/copy-into-table) · [PUT](https://docs.snowflake.com/en/sql-reference/sql/put) · [CREATE SECURE VIEW](https://docs.snowflake.com/en/sql-reference/sql/create-view) · [Warehouse management](https://docs.snowflake.com/en/user-guide/warehouses-tasks).
