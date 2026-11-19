SELECT CAST(DATE_TRUNC('month', sent_on) AS DATE) AS period_start,
       region, carrier, COUNT(*) AS shipment_count,
       SUM(freight_cents)::BIGINT AS freight_cents,
       ROUND(SUM(freight_cents) / (100.0 * COUNT(*)), 2)::DECIMAL(12,2) AS avg_cost_eur
FROM silver
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3
