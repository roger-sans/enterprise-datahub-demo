# Architecture, decisions and operational boundaries

## Physical and business contracts

| Layer | Durable output | Rule |
| --- | --- | --- |
| Bronze | A run-specific JSONL object with SHA-256, row count and bytes | Preserve source attribute values and stable input ordinals. Writes use a new run directory. |
| Silver | Typed Parquet deduplicated by synthetic event reference | Take the latest revision per event, retaining nullable dispatch completion. Validate allowed domains, non-negative amounts and reference counts. |
| Gold | Typed Parquet at the product’s agreed grain | Define keys and aggregation in SQL. Check schema, types, nulls, unique grain, measure ranges and count-and-amount reconciliation with Silver. |
| Serving | Immutable Parquet snapshot plus a transactional current pointer | Copy Gold only after both gates pass. Persist source and output digests, contract version, checks and counts with the pointer. |
| Consumption | Versioned contract JSON, current preview and CSV | Expose authorised aggregates through the interface. Preview and download identify the immutable publication via response metadata. |

No extra persisted canonical table is necessary for these two feeds. Dispatch standardisation gives both owners the same revision logic. Independent Dagster replays for Operations and Finance write separate paths and agree on the same input digest. A dedicated shared physical Silver publication only becomes worthwhile if independent producers or refresh windows require it.

## Decision records

| Decision | Context and trade-off | Validation |
| --- | --- | --- |
| ADR-01 · Parquet objects and a small transactional registry | Parquet and SQL let a reviewer reproduce a layered workload with a single Python service. Local directories model objects, while DuckDB reads the files in-process. SQLite keeps approvals and the current pointer in one transaction without another service. | Inspect run objects and query the API. Object-store retries, IAM, retention automation, Iceberg cataloguing and concurrent multi-host access are future engineering decisions. |
| ADR-02 · Commit only after two blocking checks | A revision pass at source and a second contract gate protect different boundaries. Validated content is written before advancing the publication pointer. A failed run preserves the previous pointer, even when a publication is stale. | Inject a bad amount, compare exported bytes, replay and confirm recovery. The transaction also rejects completion from a superseded run or changed approved contract. |
| ADR-03 · Separate contract approval and materialisation | Producers and reviewers can agree on future shape while current reads remain stable. Additive changes append nullable fields so the original CSV prefix survives. | Approve v1.1.0, confirm v1.0.0 is still current, then refresh and inspect the new column. A breaking proposal stays in the audit trail. |
| ADR-04 · Snowflake as an optional managed Serving path | One verified reference implementation constrains migration scope. Governed Parquet export moves the data boundary without introducing a second local engine. Separate roles, secure views and an auto-suspending warehouse get reviewed in the sandbox. | Run the parity, denial, replay and cost checklist. See [Snowflake](snowflake.md). |

## Operating model

- **Dagster.** A single reusable asset graph supports the three product inputs using run config. Start from the browser or CLI, or enable the independent daily schedules at 06:00, 06:20 and 06:40 UTC. Run tags/IDs and events tie a materialisation back to its snapshot. The freshness clock starts at accepted publication, while the observation dates are fixed synthetic fixture dates.
- **Alert and recovery.** A blocked run records a quality or execution alert with the product and gate. The operator checks run evidence, acknowledges the alert and replays a corrected input. A later accepted refresh resolves earlier alerts. Missing and stale snapshots show separately in the freshness watch.
- **Crash handling.** A process killed during work can leave an unreferenced directory and a running journal entry. The previous committed pointer survives. For the demo, rerun the product and retain the evidence. A lease-based reconciler and an end-to-end restore test are part of the next release.
- **Retention and privacy.** The demo keeps its local snapshots for inspection. Each product documents its proposed retention. Never use real data. Future policy separates producer access to source storage, governed aggregate reads and platform custody of the registry.
- **Deployment boundary.** The API listens on loopback by default. Roles are selected by the user and serve to exercise workflow constraints. A shared deployment needs authentication, actual identity mapping, audited access, backup and external alert routing.
- **Target platform.** PostgreSQL is the next option for independently deployed metadata and Dagster state if multiple workers are admitted. Managed object storage or Iceberg can be considered when retention, concurrent writers and external table interoperability justify the operational cost.
