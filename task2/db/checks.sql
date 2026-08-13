-- Integrity and correctness checks over the loaded data.
--
-- Every query but the last reports a verdict, so the run either reads as six
-- PASSes or points at the one thing that broke. They check two different
-- things: that the load arrived whole, and that the PySpark transformations
-- computed what they claim -- which is why several of them recompute a
-- transformation in SQL and compare, rather than trusting the column.

\echo
\echo '1. the load arrived whole'
SELECT
    count(*)                                              AS readings,
    count(DISTINCT sensor_id)                             AS sensors,
    count(DISTINCT parameter)                             AS parameters,
    count(DISTINCT reading_date)                          AS days,
    min(reading_date)                                     AS first_day,
    max(reading_date)                                     AS last_day,
    CASE
        WHEN count(*) > 0
         AND count(*) FILTER (
                 WHERE sensor_id IS NULL OR reading_date IS NULL
                    OR location IS NULL OR parameter IS NULL
                    OR value IS NULL OR status IS NULL) = 0
         AND count(DISTINCT parameter) = 6
        THEN 'PASS' ELSE 'FAIL'
    END                                                   AS verdict
FROM readings;

\echo
\echo '2. the summary table agrees with the readings it summarises'
-- Recomputing the aggregate transformation in SQL. Spark rounded these columns
-- to three decimals on the way out, so agreement means "within half of the last
-- digit kept" -- 0.0005, no more. The comparisons run in numeric rather than
-- double for that reason: a value that lands exactly on the halfway point is
-- exactly 0.0005 away in decimal, but 0.0005000000001 away in binary floating
-- point, and would fail a comparison it should pass.
WITH recomputed AS (
    SELECT location,
           parameter,
           count(*)                                              AS readings,
           avg(value)                                            AS avg_value,
           min(value)                                            AS min_value,
           max(value)                                            AS max_value,
           100.0 * count(*) FILTER (WHERE status = 'Bad') / count(*) AS bad_pct
    FROM readings
    GROUP BY location, parameter
),
disagreement AS (
    SELECT location, parameter
    FROM location_stats s
    FULL JOIN recomputed r USING (location, parameter)
    WHERE s.location IS NULL                            -- a group only Spark saw
       OR r.location IS NULL                            -- a group only SQL sees
       OR s.readings <> r.readings
       OR abs(s.avg_value::numeric - r.avg_value::numeric) > 0.0005
       OR abs(s.min_value::numeric - r.min_value::numeric) > 0.0005
       OR abs(s.max_value::numeric - r.max_value::numeric) > 0.0005
       OR abs(s.bad_pct::numeric - r.bad_pct::numeric) > 0.0005
)
SELECT (SELECT count(*) FROM location_stats)  AS summary_rows,
       (SELECT count(*) FROM recomputed)      AS recomputed_rows,
       (SELECT count(*) FROM disagreement)    AS disagreements,
       CASE WHEN (SELECT count(*) FROM disagreement) = 0
            THEN 'PASS' ELSE 'FAIL' END       AS verdict;

\echo
\echo '3. the window columns are self-consistent'
WITH tally AS (
    SELECT count(*) FILTER (
               WHERE prev_value IS NOT NULL
                 AND abs(delta::numeric - (value::numeric - prev_value::numeric)) > 0.0005
           )                                                                     AS wrong_delta,
           count(*) FILTER (WHERE reading_no = 1 AND prev_value IS NOT NULL) AS first_has_a_predecessor,
           count(*) FILTER (WHERE reading_no > 1 AND prev_value IS NULL)     AS later_missing_predecessor,
           count(*) FILTER (WHERE bad_so_far > reading_no)                   AS impossible_bad_count
    FROM readings
)
SELECT *,
       CASE WHEN wrong_delta + first_has_a_predecessor
                 + later_missing_predecessor + impossible_bad_count = 0
            THEN 'PASS' ELSE 'FAIL' END AS verdict
FROM tally;

\echo
\echo '4. reading_no runs 1..n with no gaps, once per sensor and parameter'
WITH series AS (
    SELECT sensor_id, parameter,
           count(*)        AS readings,
           min(reading_no) AS lowest,
           max(reading_no) AS highest
    FROM readings
    GROUP BY sensor_id, parameter
)
SELECT count(*)                                                   AS series,
       count(*) FILTER (WHERE lowest <> 1 OR highest <> readings) AS broken_series,
       CASE WHEN count(*) FILTER (WHERE lowest <> 1 OR highest <> readings) = 0
            THEN 'PASS' ELSE 'FAIL' END                           AS verdict
FROM series;

\echo
\echo '5. the 7 day rolling average recomputes to the same number'
-- Postgres running the same window function over the same frame. If Spark's
-- range frame had counted rows instead of days -- the easy mistake, and the one
-- a reading every eleventh day would hide -- this is where it would show.
WITH recomputed AS (
    SELECT rolling_avg_7d,
           avg(value) OVER (
               PARTITION BY sensor_id, parameter
               ORDER BY reading_date
               RANGE BETWEEN INTERVAL '6 days' PRECEDING AND CURRENT ROW
           ) AS expected
    FROM readings
),
compared AS (
    -- Numeric for the same reason as check 2: an average of two readings often
    -- lands exactly halfway, and half a digit is agreement, not a mismatch.
    SELECT abs(rolling_avg_7d::numeric - expected::numeric) AS gap FROM recomputed
)
SELECT count(*)                                  AS rows_checked,
       count(*) FILTER (WHERE gap > 0.0005)      AS mismatched,
       CASE WHEN count(*) FILTER (WHERE gap > 0.0005) = 0
            THEN 'PASS' ELSE 'FAIL' END          AS verdict
FROM compared;

\echo
\echo '6. each sensor reports from exactly one location'
WITH per_sensor AS (
    SELECT sensor_id, count(DISTINCT location) AS locations
    FROM readings
    GROUP BY sensor_id
)
SELECT count(*)                                    AS sensors,
       count(*) FILTER (WHERE locations > 1)       AS sensors_in_two_places,
       CASE WHEN count(*) FILTER (WHERE locations > 1) = 0
            THEN 'PASS' ELSE 'FAIL' END            AS verdict
FROM per_sensor;

\echo
\echo 'and the shape of the data itself, to be read rather than asserted'
SELECT parameter,
       count(*)                                                      AS readings,
       round(avg(value)::numeric, 3)                                 AS mean,
       round(stddev(value)::numeric, 3)                              AS sd,
       round(min(value)::numeric, 2)                                 AS lowest,
       round(max(value)::numeric, 2)                                 AS highest,
       round(100.0 * count(*) FILTER (WHERE status = 'Bad') / count(*), 3) AS bad_pct
FROM readings
GROUP BY parameter
ORDER BY parameter;
