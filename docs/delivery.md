# Delivery roadmap and backlog

The [delivery baseline](../hub/contracts/delivery.json) contains the eight initial stories, enablers and spikes with acceptance and proof. Initialisation creates three GitHub milestones and seeds the corresponding issues. After that, GitHub Issues owns ongoing priority, scope, decisions and acceptance. The app shows the reproducible release baseline and links each item to its issue search.

| Milestone | Product outcome | Exit gate |
| --- | --- | --- |
| 1.0 Trusted local publication | Three domains can hand over clear contracts, accepted aggregates and evidence. | Complete the walkthrough. A negative replay leaves the publication ID unchanged, compatible changes require approval, and previews and downloads reconcile. |
| 1.1 Snowflake sandbox | Make the same datasets available to warehouse consumers with measured cost and scoped access. | Prove the [Snowflake acceptance matrix](snowflake.md) and rehearse restoring the registry and artifacts into a clean environment. |
| 1.2 Federated onboarding | Qualify an independently operated second-region product. | A separate domain provides a signed contract, measured freshness, a recovery run and two adopter acknowledgements. |

## Prioritisation

Value, risk reduction and effort each use a 1–5 scale. Score = (value + risk reduction) / effort. Resolve hard dependencies and a milestone’s release gate before using score to order its ready items. A high-scoring Snowflake spike follows last-good publication and change review because spending or granting warehouse access before those controls are stable would hide risk.

| Incoming request | Decision |
| --- | --- |
| Onboard a third source quickly | Use the separate Returns feed to verify the existing path, and limit further sources until support and recovery are proven. |
| Add another analyst’s custom freight extract | Reuse Freight Spend if the new consumer can work at monthly lane grain. Open a contract proposal if a compatible new field is sufficient. |
| Fix contract and freshness debt | Treat a broken reader or stale product as a reliability/consumer issue. Fund recovery and compatibility work before adding visualisations. |
| Move Serving entirely into Snowflake | Pilot a governed publish-and-compare path first. Preserve stable local evidence and use scoped credits and access tests as the go/no-go. |
| Change a released grain | Plan a parallel major-version rollout, consumer impact review, dual validation, usage-based cutover and explicit retirement. The demo blocks breaking changes within v1. |

## Scrum checkpoints

- **Discovery and refinement.** The Product Owner links a business decision to a measurable outcome. Domain leads agree terminology. Engineers and Architecture identify dependencies and estimate the smallest testable increment.
- **Definition of Ready.** Named owner and first consumers, purpose and grain agreed, classification and permitted use documented, dependencies listed, failure example and acceptance criterion written.
- **Sprint planning.** Select increments within the capacity for build, review and operational validation. Sprint 1 delivers the catalogue and shared dispatch models. Sprint 2 adds governed change, recovery and a separate Returns product. Sprint 3 is the planned Snowflake qualification.
- **Review and acceptance.** A consumer demonstrates a successful filtered download, the operator shows the blocked candidate and later recovery, the steward demonstrates a compatible change. The Product Owner records the decision and links test evidence in the issue.
- **Definition of Done.** Contract and lineage are published, locally tested happy and failure paths, consumer-owned acceptance, docs and CI are current, known limits and recovery evidence reviewed. Live service work adds actual access denials, restore evidence and cost measurements before acceptance.
- **Release and adaptation.** Tag the accepted local increment as `v1.0.0` and attach its checks and walkthrough. Use sprint feedback and pilot adoption to re-score next work. Ask the domain owner to sponsor major contract changes.

Use engineering assistants where they accelerate scaffolding, test cases or documentation. OpenAI Codex supported the synthetic implementation, checks and documentation for this demo. GitHub Copilot or Claude Code can support targeted review in future iterations. Engineers own diffs and test evidence, while the Product Owner and stewards own acceptance and access decisions.
