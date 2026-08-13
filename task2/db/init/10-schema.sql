-- The tables the loader fills. Created here rather than left to Spark so the
-- types and the constraints are ours: Spark's JDBC writer, told to truncate
-- instead of drop, loads into this schema and never redefines it.
--
-- The constraints are the first integrity check. A load that got the windowing
-- or the column order wrong does not quietly land -- it fails on the way in.

-- One row per reading, with the window transformation's derived columns.
CREATE TABLE readings (
    sensor_id      varchar(7)       NOT NULL,
    reading_date   date             NOT NULL,
    location       text             NOT NULL,
    parameter      text             NOT NULL,
    value          double precision NOT NULL,
    status         text             NOT NULL,
    -- Position of the reading in its sensor's history of that parameter, so
    -- the three together identify a row exactly once.
    reading_no     integer          NOT NULL,
    prev_value     double precision,          -- null on a series' first reading
    delta          double precision,          -- ditto
    rolling_avg_7d double precision NOT NULL,
    bad_so_far     integer          NOT NULL,
    z_score        double precision,          -- null on a single-reading series

    PRIMARY KEY (sensor_id, parameter, reading_no),
    CONSTRAINT readings_status_known CHECK (status IN ('Good', 'Bad')),
    CONSTRAINT readings_no_positive CHECK (reading_no >= 1),
    CONSTRAINT readings_bad_so_far_sane CHECK (bad_so_far BETWEEN 0 AND reading_no),
    -- Either both are present or neither: delta is derived from prev_value.
    CONSTRAINT readings_delta_paired CHECK ((prev_value IS NULL) = (delta IS NULL))
);

-- The queries below group by these, and the fact table is scanned whole often
-- enough that the date index earns its keep.
CREATE INDEX readings_location_parameter_idx ON readings (location, parameter);
CREATE INDEX readings_date_idx ON readings (reading_date);

-- One row per location and parameter, from the aggregate transformation. Kept
-- beside the readings on purpose: holding a summary next to what it summarises
-- is what lets a query check the two against each other.
CREATE TABLE location_stats (
    location      text   NOT NULL,
    parameter     text   NOT NULL,
    readings      bigint NOT NULL,
    sensors       bigint NOT NULL,   -- approximate, from a HyperLogLog sketch
    avg_value     double precision,
    stddev_value  double precision,
    median_value  double precision,
    p95_value     double precision,
    min_value     double precision,
    max_value     double precision,
    bad_pct       double precision,
    first_reading date,
    last_reading  date,

    PRIMARY KEY (location, parameter),
    CONSTRAINT location_stats_readings_positive CHECK (readings > 0),
    CONSTRAINT location_stats_window_ordered CHECK (first_reading <= last_reading)
);
