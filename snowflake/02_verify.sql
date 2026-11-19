-- Run one section at a time using an identity assigned the corresponding reader role.
-- Compare each result with the generated manifest.json for that product.
USE SECONDARY ROLES NONE;
USE WAREHOUSE EDH_DEMO_WH;

USE ROLE EDH_OPERATIONS_READER;
SELECT COUNT(*) AS rows, SUM(shipment_count) AS shipments, SUM(on_time_count) AS on_time
FROM EDH_DEMO.SERVING.SHIPMENT_RELIABILITY_V1;

USE ROLE EDH_FINANCE_READER;
SELECT COUNT(*) AS rows, SUM(shipment_count) AS shipments, SUM(freight_cents) AS freight_cents
FROM EDH_DEMO.SERVING.FREIGHT_SPEND_V1;

USE ROLE EDH_EXPERIENCE_READER;
SELECT COUNT(*) AS rows, SUM(return_count) AS returns, SUM(refund_cents) AS refund_cents
FROM EDH_DEMO.SERVING.RETURNS_PULSE_V1;

-- Run each deliberately denied query individually as a Finance reader.
-- USE ROLE EDH_FINANCE_READER;
-- SELECT * FROM EDH_DEMO.CURATED.FREIGHT_SPEND;
-- SELECT * FROM EDH_DEMO.SERVING.SHIPMENT_RELIABILITY_V1;
-- LIST @EDH_DEMO.LANDING.SYNTHETIC_UPLOAD;
