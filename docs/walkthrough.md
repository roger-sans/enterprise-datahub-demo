# Product Owner demo and acceptance walkthrough

A 15-minute synthetic walkthrough demonstrates the outcomes delivered to three domains. No named organisational decisions, impact claims or cloud results are real.

1. **Product vision (2 min):** Open Platform Overview. Explain why Operations uses delivery week and Finance uses posting month from the same Dispatch revisions. Point to the owner, first consumer and SLA for each product.
2. **Trusted consumption (3 min):** Open Finance → Freight Spend, filter by region and month, download CSV, and compare the output grain and publication ID. Explain why consumers should use governed contracts rather than independently transforming raw data.
3. **Lineage (2 min):** Compare Freight Spend and Shipment Reliability source digests and Silver row counts. Their output measures intentionally differ while their source reconciliation is shared.
4. **Quality and recovery (3 min):** As the simulated Platform Operator, submit a negative-money Freight batch. Inspect the blocked Silver gate and audit event; the previous Serving pointer and CSV stay unchanged. Acknowledge the alert and replay a healthy batch.
5. **Governed evolution (3 min):** As the simulated Fulfilment Owner, propose an optional annotation; as Steward, approve it. The approved contract changes, but published data remains on the previous version until an accepted refresh. Verify the optional field after a healthy run.
6. **Snowflake target and release decision (2 min):** Show `snowflake/01_bootstrap.sql` and `snowflake/03_native_pipeline.sql`. Explain native RAW→SILVER→GOLD, publishing procedures, secure reader views and suspended Tasks. Demonstrate `python -m hub snowflake-stage freight-spend exports/freight`, which generates an original RAW dataset and a cloud load script. Explain why a real role-denial, parity, recoverability and metering pilot is mandatory before enabling recurring warehouse consumption.

## Optional actual Snowflake reader walkthrough

Only with an approved test account and a named reader-only entry in Snowflake Connector's `connections.toml`:

```bash
python -m pip install -e ".[snowflake]"
export HUB_SNOWFLAKE_CONNECTION=edh-finance-reader
python -m uvicorn hub.api:app --host 127.0.0.1 --port 8000
```

Use the corresponding Windows PowerShell command `$env:HUB_SNOWFLAKE_CONNECTION="edh-finance-reader"` when applicable. Call `GET /api/snowflake/freight-spend/data?dimension=WEST&limit=10`. That route uses the allowlisted secure view and bound parameters, and returns **503 instead of invented local data** if the connection is missing. A Finance reader must not be able to fetch another domain's Snowflake view. Cloud acceptance remains pending until this has been tested.

The normal workspace still runs using the local offline simulator and does not silently switch to cloud.
