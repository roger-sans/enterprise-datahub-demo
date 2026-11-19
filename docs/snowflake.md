# Snowflake-native migration and acceptance

**Status:** SQL-native target architecture implemented in the public synthetic repository. The offline adapter and tests run without a Snowflake account. **Cloud execution, SQL procedure validation on a real account, permissions and metering are not yet verified.**

## What changed from the earlier Dagster-based release

| Concern | Former design | Snowflake-first design |
| --- | --- | --- |
| Orchestration | Dagster asset graph and daily schedules | Snowflake SQL procedures and three native Tasks (suspended initially) |
| Bronze/raw | Local JSONL objects orchestrated by Dagster | Raw JSONL copied into `EDH_DEMO.RAW.EVENTS` as VARIANT with batch and source lineage |
| Silver | DuckDB materialises typed local Parquet | `SILVER.DISPATCH_EVENTS` and `SILVER.RETURN_EVENTS`: typed, revision-deduplicated Snowflake views |
| Gold | DuckDB writes product-grain Parquet | Three SQL `GOLD` aggregation views with separate business grains |
| Quality | Blocking Dagster asset checks | SQL quality and reconciliation gates in `GOVERNANCE.PUBLISH_PRODUCT` |
| Serving | Local Parquet pointer, optional export to Snowflake | Governed immutable `CURATED` batches, transactional `CURRENT_PUBLICATION` pointer, product-specific secure views |
| Observability | Dagster run events and SQLite alert journal | `GOVERNANCE.PUBLICATION_AUDIT` and Snowflake Task history in the cloud; local audit/alerts remain in the offline demo |
| Local preview | FastAPI over accepted Parquet | **Unchanged offline demonstration**; this API is not represented as connected to Snowflake |

The goal is a domain-owned **Snowflake platform product** with secure, reproducible serving contracts. Dagster is no longer a runtime or optional dependency.

## Run the SQL-native path in a separate Snowflake sandbox

The remote path requires a real Snowflake test account and Snowflake CLI (`snow`). Set up an approved account role, warehouse credit budget/resource monitor, and separate publisher and reader identities. Do not use corporate credentials or production data.

Run the setup with a sandbox administrator:

```bash
snow sql --connection edh-sandbox -f snowflake/01_bootstrap.sql
snow sql --connection edh-sandbox -f snowflake/03_native_pipeline.sql
```

The first script creates RAW, SILVER, GOLD, CURATED, GOVERNANCE and SERVING scopes, a tiny auto-suspending warehouse, an internal JSON stage, three source-specific reader roles and a publisher role. The second defines typed transforms, reconciliation, the governed publication procedures and three scheduled tasks. **Tasks are left suspended.**

Generate and load only original fictional source events:

```bash
python -m hub snowflake-stage shipment-reliability exports/shipment
python -m hub snowflake-stage freight-spend exports/freight
python -m hub snowflake-stage returns-pulse exports/returns

snow sql --connection edh-sandbox -f exports/shipment/load.sql
snow sql --connection edh-sandbox -f exports/freight/load.sql
snow sql --connection edh-sandbox -f exports/returns/load.sql
```

Each directory holds its JSONL source, manifest with row count and SHA-256, and `load.sql`. The file is loaded through `PUT` + `COPY INTO RAW.EVENTS`; Snowflake (not the local engine) performs the downstream Silver/Gold transformations and calls `GOVERNANCE.PUBLISH_PRODUCT`. The result `PUBLISHED` means the procedure's current quality and reconciliation checks passed; `BLOCKED_*` is **not** acceptance.

An identical source fixture can be restaged with a new unique batch ID to model recovery. The same accepted batch is idempotent at the publication pointer, subject to one publisher per product. A negative-money batch must not advance `CURRENT_PUBLICATION`.

Use separate role-scoped reader identities when running verification sections:

```bash
snow sql --connection edh-sandbox -f snowflake/02_verify.sql
```

## Actual migration and cutover gates

1. **Inventory and freeze:** capture previous local accepted snapshot IDs, consumer contracts, source digests, data-quality outcomes and existing sandbox grants. Do not destroy the former state.
2. **Independent schema:** install RAW and GOVERNANCE structures without truncation. The bootstrap's additive `BATCH_ID` changes permit old optional sandbox curated tables to coexist; the new publication pointer is separate.
3. **Source parity:** stage both synthetic source types. Compare raw count, unique source reference count, latest revisions and money totals against the local baseline.
4. **Contract parity:** compare all three product grains, sorted keys, nullability and count-weighted or sum-weighted measures. Confirm the original V1 consumer projection has not changed.
5. **Fail closed:** stage a negative monetary amount. Confirm `PUBLICATION_AUDIT` records BLOCKED and the pointer and secure-view bytes remain unchanged. Replay a healthy batch and confirm recovery.
6. **Least privilege:** with secondary roles disabled, show that Finance cannot read RAW, CURATED or another product's view; likewise check Operations and Experience. Grant no cross-domain access by default.
7. **Idempotence and recoverability:** repeat a batch; test a concurrent-publisher scenario or enforce serial task execution; record a restore from a clean test database and stable published row counts.
8. **Cost and operations:** review warehouse sizing, task scheduling, query history, credit consumption and autosuspend. Obtain a Finance-approved cap before enabling scheduled tasks.
9. **Business decision:** Product Owner, Domain Owners, Governance, Security and Platform Engineering approve a measured Go/No-Go. Record the rollback path and consumer cutover.
10. **Opt-in schedule:** only after sign-off, use the commented `ALTER TASK ... RESUME` statements in `03_native_pipeline.sql`.

**Rollback:** `ALTER TASK <name> SUSPEND` first. Keep the former local snapshots available. Do not drop Snowflake data on a failed cutover; re-point consumers only after their original contract and access have been verified. Snowflake's prior accepted immutable batches should be retained for explicit recovery, not silently overwritten.

## Business and technical boundaries

- Source event references and all role names in the example are fictional; no real ERP adapter is included.
- Simulated web actors and permissions are local training aids, not Snowflake SSO.
- `CURRENT_PUBLICATION` contains one logical row per product. For a production upgrade, serialize publishers per product and verify concurrency/idempotence under account-specific transaction semantics.
- The Snowflake cloud baseline exposes the stable **v1** contract. The local demo's independently approved v1.1 optional annotation illustrates the review process; promoting this schema to the cloud requires a separately versioned secure view and acceptance.
- Current tasks are time-scheduled and **suspended**. They do not ingest new source files automatically; producers still stage accepted raw batches. Adding event-triggered ingestion/Streams, retention and enterprise monitoring is a separate scoped increment.
- A local green CI is not evidence of production-grade security, measured Snowflake credits or executed cloud procedures.

**References:** [Snowflake Tasks](https://docs.snowflake.com/en/sql-reference/sql/create-task), [Stored procedures](https://docs.snowflake.com/en/sql-reference/sql/create-procedure), [COPY INTO](https://docs.snowflake.com/en/sql-reference/sql/copy-into-table), [Secure views](https://docs.snowflake.com/en/sql-reference/sql/create-view).
