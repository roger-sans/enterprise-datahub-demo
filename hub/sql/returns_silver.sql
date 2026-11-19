SELECT
    ref,
    CAST(opened_on AS DATE) AS opened_on,
    LOWER(TRIM(channel)) AS channel,
    TRIM(reason) AS reason,
    CAST(refund_cents AS BIGINT) AS refund_cents,
    CAST(revision AS INTEGER) AS revision
FROM bronze
QUALIFY ROW_NUMBER() OVER (PARTITION BY ref ORDER BY revision DESC, source_row DESC) = 1
