# MEHazi — task 2

A million rows of synthetic sensor data, generated in Spark, transformed in
Spark, loaded into Postgres, and checked with SQL. Four containers, one command.

## Architecture

```
        ┌────────────────────────────────────────────────┐
        │ pipeline   generate → transform → parquet      │
        │            spark, runs once, exits             │
        └───────────────────────┬────────────────────────┘
                                │ /data volume
                                ▼
        ┌────────────────────────────────────────────────┐
        │ loader     parquet → jdbc → postgres           │
        │            spark, runs once, exits             │
        └───────────────────────┬────────────────────────┘
                                │ readings, location_stats
                                ▼
        ┌────────────────────────────────────────────────┐
        │ db         postgres 17, :5433 on the host      │
        └───────────────────────┬────────────────────────┘
                                │ reads
                                ▼
        ┌────────────────────────────────────────────────┐
        │ checks     six SQL queries, PASS or FAIL       │
        │            psql, runs once, exits              │
        └────────────────────────────────────────────────┘
```

Each stage runs once and exits, and each depends on the previous one having
exited *successfully* — so `docker compose up` walks the whole chain and stops
at the first thing that breaks. Only the database stays up.

The two Spark stages share one image: the code, the JDBC driver and Spark are
baked in, nothing is bind-mounted, and which script runs is just the command.

**The database answers on host port 5433**, not 5432 — that one belongs to
task1. Inside the compose network it is `db:5432` as usual.

## Run

```bash
cd task2
docker compose up -d --build
docker compose logs -f checks
```

The whole chain takes about a minute from cold: a few seconds of generation,
fifteen of transforms, ten to load a million rows over JDBC, and a few for the
checks.

Note `up -d` rather than `up`: with `--abort-on-container-exit`, the pipeline
finishing normally would tear down the stack before the loader had started.

To watch a stage as it happens:

```bash
docker compose logs -f pipeline    # generation and the five transformations
docker compose logs -f loader      # the two tables going in
```

To re-run one stage on its own:

```bash
docker compose run --rm --no-deps loader
docker compose run --rm --no-deps checks
```

## The data

`main.py` generates the readings and applies five transformations, each written
to its own parquet directory under `/data/output`:

| Output | Rows | What it is |
| --- | --- | --- |
| `window` | 1,000,000 | every reading, plus its position, previous value, delta, 7-day rolling average, running Bad count and z-score within its own series |
| `aggregate` | 36 | one row per location and parameter: counts, mean, σ, median, p95, range, Bad % |
| `pivot` | 769,810 | one row per sensor per day, one column per parameter |
| `unpivot` | 955,594 | the pivot melted back to one row per reading |
| `date_parts` | 1,000,000 | the date exploded into year, quarter, month, week, weekday, month bounds |

Nothing is generated on the driver. `spark.range` produces the rows and every
column is a native Spark expression over the row id, so generation is spread
across the executors and a bigger `NUM_ROWS` costs only time. The values come
from `hash(id, seed)` rather than `rand()`, which makes the whole frame
reproducible: the same row id yields the same sensor, date and reading no matter
how the range is partitioned.

Two of the five are loaded into Postgres — `window` as `readings`, `aggregate`
as `location_stats`. Keeping a summary next to what it summarises is what lets
check 2 hold the two against each other.

## The checks

`db/checks.sql`, run by the `checks` container. Six queries, each reporting PASS
or FAIL, and a seventh that just prints the shape of the data:

| # | Question | How it answers |
| --- | --- | --- |
| 1 | did the load arrive whole? | counts, date range, and no nulls in any required column |
| 2 | does the summary match the readings? | recomputes the aggregate transformation in SQL and diffs all 36 rows |
| 3 | are the window columns self-consistent? | `delta` must equal `value - prev_value`; a series' first reading must have no predecessor and every later one must |
| 4 | is `reading_no` sound? | 1..n with no gaps in each of the 30,000 sensor-parameter series |
| 5 | is the rolling average right? | Postgres recomputes the same 7-day window and compares row by row |
| 6 | is each sensor in one place? | a sensor that reported from two locations would mean the join keys drifted |

The schema is the first check and runs before any of them: `db/init/10-schema.sql`
declares the primary key `(sensor_id, parameter, reading_no)`, `status IN
('Good','Bad')`, `bad_so_far <= reading_no`, and that `prev_value` and `delta`
are null together. A load that got the windowing or the column order wrong does
not land quietly — it fails on the way in.

Run them by hand against the running database:

```bash
docker compose exec db psql -U sensors -d sensors -f /checks.sql
docker compose exec db psql -U sensors -d sensors -c 'SELECT * FROM location_stats LIMIT 5'
```

### A note on comparing rounded numbers

The transformations round to three decimals, so a check that recomputes a value
must accept half of the last digit kept. That tolerance is 0.0005 — and it has
to be tested in `numeric`, not `double precision`. An average of two readings
lands exactly on the halfway point often enough to matter, and in binary
floating point that distance comes out as 0.0005000000001: a hair over a
threshold it should sit exactly on. Written in floats, check 5 fails on 67,194
of a million perfectly correct rows.

## Configuration

Everything is defaulted in `compose.yaml`, so the stack runs with no `.env` at
all. To change something:

```bash
cp .env.example .env
```

| | |
| --- | --- |
| `NUM_ROWS` | how many readings to generate (default 1,000,000) |
| `DB_PORT` | host port for Postgres (default 5433) |
| `POSTGRES_DB` / `_USER` / `_PASSWORD` | the database and its credentials |

## Running it without compose

`main.py` is an ordinary PySpark script and needs no database:

```bash
docker run --rm -v "$PWD":/app -w /app --user root \
  apache/spark:4.0.1 /opt/spark/bin/spark-submit --master 'local[4]' main.py
```

It writes to `./output` unless `OUTPUT_DIR` says otherwise.

## Layout

```
compose.yaml              the four services, two volumes
Dockerfile                spark + the postgres jdbc driver + the two scripts
.env.example              every setting, documented

main.py                   generate_sensor_data, the five transformations,
                          do_transformations to run and save them
load.py                   parquet -> postgres over jdbc

db/
  Dockerfile              postgres + the schema and the checks
  init/10-schema.sql      readings, location_stats, and their constraints
  checks.sql              the six integrity queries
```

## Resetting

```bash
docker compose down          # stop, keep the data
docker compose down -v       # drop the database and the parquet too
```
