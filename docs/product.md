# Product strategy and operating model

## Vision

Domain teams can publish an agreed dataset once, while consumer teams can discover, interpret and reuse it without asking Platform Engineering to recreate a feed. Enterprise Data Hub provides a paved path for domain-owned products, with common publication, review and recovery controls.

The wedge is a freight decision shared by Operations and Finance. An Operations analyst wants the delivery outcome in the correct week. Finance needs every booked dispatch cost in its posting month. Both need the same source identity and revision rules. The release collapses duplicate integration work while giving each owner control over the meaning of its own product.

## Stakeholders and discovery agreements

These are fictional workshop outcomes for a distributed organisation.

| Stakeholder and person represented | Request or tension | Agreement and evidence |
| --- | --- | --- |
| Operations EMEA · Fulfilment lead | Track exceptions by delivery week, including carrier. | Shipment Reliability excludes pending shipments from its denominator and shows a 95% illustrative performance target. |
| Finance Planning · Analyst | Reconcile posted cost by month, including pending dispatches. | Freight Spend uses dispatch month and integer EUR cents. The owner accepts the reconciliation between Silver cost and Gold cost. |
| Business Improvement · Continuous improvement lead | Compare carriers across regions and investigate last week’s shifts. | Same region codes in Silver, stable lane keys, and an export with the exact same filters as preview. |
| Product Management · Product manager | Identify delivery issues and return reasons for a product review. | Separate contracts for shipping and returns. Keep the business terms explicit in the catalogue. |
| Marketing · Campaign analyst | Ask for a return-rate indicator on a campaign cohort. | Launch Returns Pulse as counts with no sales denominator. Sponsor a denominator spike only if both consumer teams use the first product. |
| Customer Experience · Operations analyst | Split refunds by channel and reason without exposing individual case details. | Only categorical aggregates are served. Domain owns the grouping, the steward reviews contract changes. |
| Architecture, Governance and Security · Council | Adopt common controls across teams while limiting cross-domain and raw access. | Mandatory owner, schema, grain, classification, freshness and separate review. Role-scoped Snowflake acceptance required before a real sandbox handoff. |
| Platform Engineering and SRE · Maintainers | Prevent a bad refresh from affecting decisions and protect support capacity. | First increment invests in blocking checks, last-good Serving, explicit retries and alerts ahead of adding more feeds or engines. |

Record disputed terms in the relevant issue. The Product Owner runs a joint decision review once per sprint with regional delegates and asynchronous notes for time-zone coverage. The domain owner approves metric meaning. Governance resolves policy exceptions through the council and records the expiry date. New scope that changes the milestone requires a revised acceptance gate and an explicit trade-off in the backlog.

## Ownership and federated governance

A = accountable, R = responsible, C = consulted, I = informed.

| Decision or task | Product Owner | Domain owner | Platform Eng/SRE | Governance steward | Consumer lead |
| --- | --- | --- | --- | --- | --- |
| Portfolio priorities and sequencing | A/R | C | C | C | C |
| Grain, allowed use and metric definition | C | A/R | C | C | C |
| Register a change and notify consumers | C | A/R | I | C | C |
| Approve a compatible contract revision | I | R | C | A | C |
| Run, alert and recover the pipeline | I | C | A/R | I | I |
| Accept business fitness for a release | R | A | C | C | R |
| Baseline classification and access policy | C | R | C | A | I |

The domains own definitions and change proposals. The platform supplies execution and the consumer interfaces. Governance sets the minimum contract and reviews independently. Consumers verify semantics and increment acceptance. The local selector simulates this responsibility split. Production requires authenticated identities and separate storage, execution and consumption permissions. Platform data should meet the same product standards as any domain data.

## Adoption and value

| Measure | Baseline for the demo | Proposed product target and measurement |
| --- | --- | --- |
| Freshness | Actual time since the last accepted publication is shown per product. | At least 99% of daily SLA observations fresh over 30 days. Sample state per product hourly in the production pilot. |
| Quality | The Silver and Gold checks, alerts and recovery are executable. | No blocked candidate becomes current. Audit run and snapshot records during each pilot review. |
| Reuse | Two products use one dispatch specification and one standardisation query. | At least two consumer teams use each pilot product monthly. Verify through owner interviews and, after access telemetry is implemented, distinct consuming teams. |
| Time to first data | A new demo consumer can find and download an accepted aggregate in the walkthrough. | Median below one business day from approved access to first documented use. Time each second-region onboarding. |
| Support cost | Warehouse budget and actual operational load remain to be measured. | Finance agrees budget before sandbox acceptance. Review credits per accepted delivery and recovery time monthly. |

For onboarding, name the first consuming decision and two champions, document permitted use and contract, add automated validation, rehearse recovery, and walk through preview and CSV with both teams. Obtain owner and consumer acceptance before a supported release. Keep labelled adoption targets separate from measured results.
