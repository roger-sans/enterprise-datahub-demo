SELECT
    ref,
    CAST(sent_on AS DATE) AS sent_on,
    CAST(promised_on AS DATE) AS promised_on,
    CAST(delivered_on AS DATE) AS delivered_on,
    UPPER(TRIM(region)) AS region,
    TRIM(carrier) AS carrier,
    CAST(freight_cents AS BIGINT) AS freight_cents,
    CAST(revision AS INTEGER) AS revision
FROM bronze
QUALIFY ROW_NUMBER() OVER (PARTITION BY ref ORDER BY revision DESC, source_row DESC) = 1
