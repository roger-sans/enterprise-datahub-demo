# Enterprise Data Hub
**Snowflake-first Data Enablement | Data Products | Federated Governance | Product Ownership**

A standalone **synthetic enterprise data platform** for Operations, Finance and Customer Experience. It turns conflicting source definitions into governed, reusable data products with agreed grain, owner, contract, lineage, quality gates and explicit publication decisions.

> **Scope:** Snowflake-native SQL, procedures, secure views and suspended Tasks are provided for a sandbox deployment. The self-contained web demonstration uses an offline DuckDB/SQLite adapter with the same business gates; it does **not** pretend a live Snowflake account was used.

![Enterprise Data Hub overview](assets/01-overview.png)

## Three business-owned data products

| Product | Accountable owner | Consumer decision | Contract grain |
| --- | --- | --- | --- |
| **Shipment Reliability** | Fulfilment | Which carrier and region merits a service review? | Delivery week × region × carrier |
| **Freight Spend** | Finance | What drives monthly transport costs? | Dispatch month × region × carrier |
| **Returns Pulse** | Customer Experience | Which return reasons need investigation? | Request week × channel × reason |

Shipment Reliability and Freight Spend deliberately share one Dispatch source and revision logic but have **different business definitions**. Consumers can inspect owner, purpose, SLAs, contract version, quality evidence and publication lineage; the latest accepted snapshot remains available when a new batch fails.

## Snowflake-native architecture

~~~mermaid
flowchart LR
    A[Reproducible fictional source events] --> B[Snowflake RAW · VARIANT and stage]
    B --> C[Snowflake SILVER · typed deduplicated views]
    C --> D[Snowflake GOLD · governed business aggregates]
    D --> E[Quality and reconciliation gates]
    E --> F[CURATED · immutable accepted batches]
    F --> G[Publication pointer and secure SERVING views]
    G --> H[Operations / Finance / Experience consumers]
    T[Snowflake Tasks · suspended by default] --> E
    C1[Owner + contract steward] --> E
~~~

**Snowflake is the target data-processing and publication authority**, not an optional copy of locally computed Serving. Native Snowflake SQL performs standardisation, deduplication, aggregation and reconciliation. A stored procedure governs accepted publication and returns explicit blocked statuses. Three warehouse-backed Snowflake Tasks can call the latest-batch publisher on staggered schedules; they are **not enabled by default**.

A self-contained local simulator keeps the portfolio executable without paid cloud infrastructure. It uses synthetic JSONL/Parquet, DuckDB for SQL transformation and SQLite for the local approval and audit journal. This is a documented execution-mode distinction, not a claim of cloud parity.

## Run the local demonstration

Requirements: Python 3.11+.

~~~bash
git clone https://github.com/roger-sans/enterprise-datahub-demo.git
cd enterprise-datahub-demo
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m hub seed --with-incident
python -m uvicorn hub.api:app --host 127.0.0.1 --port 8000
~~~

Open **http://127.0.0.1:8000** (workspace) or **http://127.0.0.1:8000/docs** (OpenAPI). Or run **docker compose up --build** to start the self-contained environment.

The intentional incident creates a blocked synthetic Freight Spend refresh. It proves that the previous accepted publication and CSV remain untouched. Omit `--with-incident` for a clean workspace.

~~~bash
python -m pytest -q
python -m playwright install chromium
python scripts/browser_smoke.py
~~~

The API, business contracts, last-good publication, additive changes, concurrent refreshes and ingestion-bundle generation are regression-tested in CI.

## Run the native Snowflake path in a separate sandbox

This requires **your own Snowflake sandbox, Snowflake CLI, an approved warehouse credit limit and roles**. Do not paste secrets into the repository.

~~~bash
# 1. Review security and cost gates. Initial setup requires an administrator.
snow sql --connection edh-sandbox -f snowflake/01_bootstrap.sql
snow sql --connection edh-sandbox -f snowflake/03_native_pipeline.sql

# 2. Generate synthetic RAW files locally. Each command creates manifest + load.sql.
python -m hub snowflake-stage shipment-reliability exports/shipment
python -m hub snowflake-stage freight-spend exports/freight
python -m hub snowflake-stage returns-pulse exports/returns

# 3. Upload RAW event batches; Snowflake computes Silver/Gold and runs the
#    governed publisher, not the local DuckDB transformation.
snow sql --connection edh-sandbox -f exports/shipment/load.sql
snow sql --connection edh-sandbox -f exports/freight/load.sql
snow sql --connection edh-sandbox -f exports/returns/load.sql

# 4. Use dedicated reader identities for the access probes.
snow sql --connection edh-sandbox -f snowflake/02_verify.sql
~~~

Tasks are created suspended, and must only be resumed after credential isolation, negative-access probes, cost controls, rollback and stakeholder approval. The [migration and acceptance guide](docs/snowflake.md) explains how to cut over from the earlier Dagster-centric demonstration and what still requires a real Snowflake validation. **Cloud execution has not been verified in this portfolio.**

## Optional direct Snowflake secure-view API

For an approved sandbox reader account, install the optional connector and configure a named profile in your local Snowflake `connections.toml` (never in Git):

~~~bash
python -m pip install -e ".[snowflake]"
# Set HUB_SNOWFLAKE_CONNECTION to a reader-scoped named profile.
# Example on Windows: $env:HUB_SNOWFLAKE_CONNECTION="edh-finance-reader"
~~~

The **GET /api/snowflake/{product_id}/data** endpoint queries only the selected, allowlisted `SERVING.*_V1` secure view with parameterised filters. It returns 503 when not configured, rather than silently substituting offline data. The default dashboard uses its local demo dataset; cloud reads are explicit, separate and not validated without a Snowflake account. See [consumer verification](docs/walkthrough.md).

## Product Ownership and governance

The case demonstrates a Product Owner who treats data as an internal product: cross-functional discovery, value/risk prioritisation, federated responsibility, consumer contracts, data quality, incident recovery and Snowflake platform adoption.

| Explore | Evidence |
| --- | --- |
| Business discovery and stakeholder ownership | [Product strategy](docs/product.md) |
| Contracts, immutable snapshots and observability | [Architecture and decisions](docs/architecture.md) |
| Backlog, dependencies and definition of done | [Delivery roadmap](docs/delivery.md) · [Delivery baseline](hub/contracts/delivery.json) |
| Snowflake target and migration gates | [Snowflake implementation](docs/snowflake.md) |
| Business walkthrough | [Hands-on acceptance](docs/walkthrough.md) |

The implementation uses original code and entirely fictional events, teams and measures. Simulated web roles do not constitute authentication, and local API/database state is not intended for public hosting. Production SSO, monitored task costs, access policies and disaster recovery are separate acceptance gates.

**License:** MIT.
