# Architecture and Product Ownership decisions

## Data platform product boundary

Enterprise Data Hub is a governed internal data product platform. Domain owners decide **meaning, grain, permitted use and freshness**; the platform provides a common SQL data plane, contracts, quality gates, publication, audit and consumer access. This separation is a federated governance pattern, not a claim of a production Data Mesh rollout.

## Snowflake-native target

| Layer | Native implementation | Contract / guarantee |
| --- | --- | --- |
| RAW | Internal JSON stage, `RAW.EVENTS` with `VARIANT`, source and batch identifiers | Source records retained, no downstream guessing by description |
| SILVER | Typed views with per-batch last-revision deduplication | Stable reference, dates, cleaned controlled dimensions, money in integer cents |
| GOLD | Business-grain SQL aggregation views | Weekly delivery performance, monthly posted freight, weekly returns |
| Quality | `GOVERNANCE.PUBLISH_PRODUCT` checks source domains and Gold reconciliation | No invalid monetary amount or inconsistent aggregate becomes current |
| CURATED | Typed product tables with immutable accepted publication keys | Accepted batches are preserved; previous reader views remain stable |
| Governance | Publication pointer, append-oriented outcome audit and stored procedures | Only a passed publication moves the current pointer |
| SERVING | Product-scoped **secure views** and separate reader roles | No direct RAW/CURATED access for a domain reader |
| Execution | Three staggered Snowflake **Tasks**, suspended by default | Opt-in schedules after cost/security and release approval |
| Consumption | Versioned output contracts, controlled SQL read access | Consumers receive a consistent agreed grain and published version |

Deployment scripts are [01_bootstrap.sql](../snowflake/01_bootstrap.sql) and [03_native_pipeline.sql](../snowflake/03_native_pipeline.sql). [02_verify.sql](../snowflake/02_verify.sql) contains audit, parity and role probes.

## Offline execution adapter

The web workspace remains runnable without a Snowflake subscription. `hub.refresh` calls the original semantic models through DuckDB and records immutable local Bronze JSONL, Silver/Gold Parquet, contract evidence and a SQLite publication pointer.

This is explicitly a **simulation of the acceptance workflow**, not an implicit Snowflake connection. `hub.snowflake.export_source` packages actual RAW event fixtures for Snowflake to transform; it does not transfer a precomputed Serving result. Cloud production access and warehouse costs are outside local tests.

## Architecture decisions

| ADR | Choice | Rationale and limits |
| --- | --- | --- |
| ADR-01 | Snowflake is the target data authority | Put native RAW, standardisation, product aggregation and scoped serving in one managed SQL environment. A local adapter exists only for portability. |
| ADR-02 | Two quality gates precede a current-pointer change | Source correctness and consumer-grain reconciliation are different responsibilities. Rejected batches retain the prior accepted product. |
| ADR-03 | Source observations and master contracts have different authorities | Products own business meaning. Operational/financial facts are observed and reconciled, not edited as catalogue attributes. |
| ADR-04 | SQL procedures and Snowflake Tasks replace the earlier orchestrator | Less independent infrastructure for this scoped Snowflake workload. Tasks are disabled until cost, credentials and recovery are approved. |
| ADR-05 | Independent contract approval | A breaking field removal is rejected; a compatible nullable addition requires steward approval, a new version and healthy publication. |
| ADR-06 | Secure views and least-privilege readers | Finance can read Freight Spend but not Operations/Experience or the underlying raw source in an isolated reader role. |

## Operational controls

- **Failure:** Snowflake publication returns `BLOCKED_*` and writes an outcome record without moving the accepted pointer. The local demonstration records an equivalent alert and can acknowledge/recover it.
- **Replay:** each generated JSONL is assigned a unique source batch. Stored procedures identify the latest staged batch and prevent manual publication of a stale batch. The published pointer is idempotent for an already current batch.
- **Scheduling:** three separate Snowflake Tasks are initially suspended. A producer must stage new raw batches; these Tasks do not perform automatic source ingestion.
- **Schema evolution:** the remote V1 contract remains stable; the local v1.1 annotation demonstrates approval but is not a claim that v1.1 is available in the remote sandbox.
- **Concurrency:** the current SQL path assumes serialized publication per product. The explicit cutover checklist requires a concurrency exercise; standalone accounts should not run competing publishers unchecked.
- **Lineage:** each raw batch has an export manifest and hash; Snowflake records source file/row, batch, Silver grain and accepted CURATED publication key.
- **Cost:** an XSMALL auto-suspending demonstration warehouse is defined, but actual metering and role setup must be approved in a Snowflake account before tasks are enabled.
- **Security:** browser roles are simulated, not SSO. Live deployments need corporate identity, data policies, secrets handling, retention, audit transport and restore tests.

For sequencing, migration and rollback, see [Snowflake acceptance](snowflake.md), [delivery](delivery.md) and [product strategy](product.md).
