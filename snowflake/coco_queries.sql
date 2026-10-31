-- FreshLink Multan — Snowflake queries (drafted with Snowflake Cortex Code / CoCo)
-- Goal: predict which weekday each store neighbourhood faces the highest fresh-food deficit.
-- Output of Q2 is exported to data/deficit_by_day.csv and consumed by matcher.py.
--
-- Source: any free census / consumer-spend dataset from Snowflake Marketplace.
-- Replace <DB>.<SCHEMA>.<TABLE> with the dataset you mount (names differ per listing).

-- Q1: staging table of store-area purchase events
CREATE OR REPLACE TABLE FRESHLINK.PUBLIC.AREA_PURCHASES AS
SELECT
    area_name                         AS area,
    DAYNAME(purchase_date)            AS weekday,
    SUM(fresh_produce_spend)          AS fresh_spend,
    SUM(total_grocery_spend)          AS total_spend,
    COUNT(DISTINCT household_id)      AS households
FROM <DB>.<SCHEMA>.<CONSUMER_SPEND_TABLE>
WHERE city = 'Multan'
GROUP BY 1, 2;

-- Q2: deficit index = 1 - (fresh share / city-wide fresh share), clipped 0..1, pivoted by weekday
WITH shares AS (
    SELECT area, weekday,
           fresh_spend / NULLIF(total_spend, 0) AS fresh_share
    FROM FRESHLINK.PUBLIC.AREA_PURCHASES
), city AS (
    SELECT AVG(fresh_share) AS city_share FROM shares
)
SELECT *
FROM (
    SELECT s.area, s.weekday,
           LEAST(1, GREATEST(0, 1 - s.fresh_share / c.city_share)) AS deficit
    FROM shares s CROSS JOIN city c
)
PIVOT (AVG(deficit) FOR weekday IN ('Mon','Tue','Wed','Thu','Fri','Sat','Sun'))
ORDER BY area;

-- Q3: worst day per area (what the app shows as "highest-deficit day")
SELECT area, weekday AS worst_day, deficit
FROM (
    SELECT s.area, s.weekday,
           1 - s.fresh_spend / NULLIF(s.total_spend, 0) AS deficit,
           ROW_NUMBER() OVER (PARTITION BY s.area ORDER BY deficit DESC) AS rn
    FROM FRESHLINK.PUBLIC.AREA_PURCHASES s
)
WHERE rn = 1;
