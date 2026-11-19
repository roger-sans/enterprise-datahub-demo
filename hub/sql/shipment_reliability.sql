SELECT CAST(DATE_TRUNC('week', delivered_on) AS DATE) AS period_start,
       region, carrier, COUNT(*) AS shipment_count,
       SUM(CASE WHEN delivered_on <= promised_on THEN 1 ELSE 0 END)::BIGINT AS on_time_count,
       ROUND(100.0 * SUM(CASE WHEN delivered_on <= promised_on THEN 1 ELSE 0 END) / COUNT(*), 2)::DECIMAL(8,2) AS on_time_pct
FROM silver
WHERE delivered_on IS NOT NULL
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3
