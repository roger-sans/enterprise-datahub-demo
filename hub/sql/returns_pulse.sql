SELECT CAST(DATE_TRUNC('week', opened_on) AS DATE) AS period_start,
       channel, reason, COUNT(*) AS return_count,
       SUM(refund_cents)::BIGINT AS refund_cents
FROM silver
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3
