# Delivery roadmap and Product Owner backlog

The [delivery baseline](../hub/contracts/delivery.json) contains eight scoped stories, enablers and spikes, with named accepting roles, risk/value/effort scores and evidence. GitHub Issues and milestone decisions are the ongoing Product Backlog; this JSON is an independent reproducible demo baseline.

| Increment | Delivered product capability | Acceptance status |
| --- | --- | --- |
| **1.0 · Trusted local publication** | Three owned products, versioned contracts, quality gates and last-good Serving in the offline simulator | Implemented and covered by local/API/browser tests |
| **2.0 · Snowflake-native migration** | RAW ingestion bundle, Silver/Gold SQL, Snowflake publication procedure, secure views and suspended native Tasks; Dagster removed from the runtime | Implemented as reviewed repository artifacts; real Snowflake parity, permissions, credits and recovery **still require a sandbox acceptance** |
| **2.1 · Federated onboarding** | An independently owned new region/product with monitoring and support model | Backlog / not implemented |

## Prioritisation

Value, risk reduction and effort use a 1–5 scale; a ready item's illustrative score is `(value + risk reduction) / effort`. Explicit dependencies, security and release gates take precedence over scores. Finance and Security must approve actual warehouse credits and grants before any Snowflake Task is activated.

| Business request | Product decision |
| --- | --- |
| Build a dashboard quickly | Reuse a published product and its accepted grain before developing a duplicate metric. |
| Finance and Operations disagree on the same Dispatch feed | Publish two separate grains over common source revision logic; make both definitions discoverable. |
| A faulty feed arrives | Block the new batch, preserve the last-good publication and record the failure for recovery. |
| Remove an old measure | Treat as a breaking contract, require consumer impact review and a versioned major rollout. |
| Migrate to Snowflake | Make the data plane and execution genuinely Snowflake-native rather than simply exporting local Parquet. |
| Enable schedules | Require a measured sandbox pilot, role-denial checks, rollback and a credit cap before RESUME. |

## Increment 2.0 acceptance scenarios

**Story EDH-05 — As a platform Product Owner, I want a Snowflake-native delivery path so domain teams can adopt a common governed platform without relying on a second orchestrator.**

- A raw batch is exported from synthetic source events with a manifest, expected row count and checksum.
- Snowflake SQL defines source-specific typed Silver, domain-owned Gold and a publication procedure that rejects malformed money and reconciliation failure.
- Reader roles are restricted to their own secure serving view.
- The local executable demonstration retains the ability to seed, refresh, block and recover.
- No Dagster dependency, launch path or scheduling service remains in executable code.
- Snowflake Tasks start suspended and are never silently activated by the migration.

**Story EDH-06 — As SRE, I want verified recovery, cost and access evidence before enabling scheduled cloud refreshes.** This requires an account-side test: schema and data parity, negative publication, least-privilege denial, idempotency under realistic concurrency, backup/restore and observed warehouse credits. It remains open until those are demonstrated.

**Story EDH-07 — As a new Domain Owner, I want a governed onboarding contract.** The new owner must agree semantic definitions, quality tests, freshness, consumers and acceptance before publication to a new market.

## Scrum operating rhythm

- **Discovery:** Product Owner resolves customer decision, value and terms with domain owners.
- **Refinement:** Engineers scope smallest independently testable contract, SQL model and error case.
- **Ready:** Named owner, consumer, grain, source authority, restricted use, dependency and acceptance scenario.
- **Review:** Show both healthy publication and deliberate block; demonstrate business meaning and contract version.
- **Done:** Source and product contracts versioned; code reviewed; CI green; rollback documented; business acceptance recorded. Cloud readiness additionally requires account-side controls and cost metrics.
- **Adaptation:** Reprioritise only after stakeholders review the outcome and technical debt.

OpenAI Codex and GitHub help accelerate implementation and review, but do not substitute for independent business validation. The synthetic portfolio does not claim enterprise deployment or measured external adoption.
