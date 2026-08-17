# MEHazi — Data Engineering assignment

Three tasks, three self-contained folders. Each one has its own compose stack,
its own README and no build step outside Docker.

| | | |
| --- | --- | --- |
| **[task1](task1/)** | Data collection and preparation | yfinance → pandas → Postgres → Superset dashboard |
| **[task2](task2/)** | PySpark | 1M generated rows → 5 Spark transformations → parquet → Postgres → SQL checks |
| **[task3](task3/)** | Frontend and backend | FastAPI over task2's database + a Svelte page |

## The pipeline

Task 1 is a standalone pipeline on real market data. Tasks 2 and 3 are one
pipeline: **task 2 produces the data and task 3 serves it.**

```
task1   ┌──────────────────────────────────────────────────────────────────┐
        │  collect          yfinance, 5 tickers × 5 years of daily bars    │
        │     ↓             raw parquet, one file per ticker               │
        │  process          pandas: normalize → repair → validate          │
        │     ↓             clean parquet, one tidy frame                  │
        │  load             upsert into Postgres on (date, ticker)         │
        │     ↓                                                            │
        │  present          Superset dashboard over the ticker_metrics view│
        └──────────────────────────────────────────────────────────────────┘

task2   ┌──────────────────────────────────────────────────────────────────┐
        │  generate         PySpark, 1,000,000 synthetic sensor readings   │
        │     ↓                                                            │
        │  process          window · groupBy+agg · pivot · unpivot · dates │
        │     ↓             parquet, one directory per transformation      │
        │  load             Spark → JDBC → Postgres (readings,             │
        │     ↓                                      location_stats)       │
        │  verify           6 SQL integrity checks, each PASS or FAIL      │
        └───────────────────────────────┬──────────────────────────────────┘
                                        │ task3 joins task2's network
task3   ┌───────────────────────────────▼──────────────────────────────────┐
        │  API              FastAPI + pydantic, 5 endpoints                │
        │     ↓                                                            │
        │  frontend         sensor picker, summary, sortable table         │
        └──────────────────────────────────────────────────────────────────┘
```

## Running everything

Docker is the only prerequisite. There is nothing to configure first: the `.env`
files are committed with working defaults.

```bash
git clone https://github.com/david-morgenstern/MEHazi.git
cd MEHazi
./build-all.sh      # build and start all three, in order
./teardown.sh       # stop everything and delete the data
```

Whether this machine reaches the internet directly or through a corporate proxy
is something `build-all.sh` works out for itself, so the same checkout builds on
either network with nothing to edit for one or the other.

It waits for each stage to *finish* rather than merely start — the
pipeline to exit 0, Superset to report healthy, all six of task 2's integrity
checks to pass — and fails loudly, naming the log to read,
if any of them does not. Running it again over a live stack is a harmless
re-verification. `--no-cache` rebuilds every image from scratch; `teardown.sh
--images` also deletes them.

About four minutes cold, most of it Superset's first migration and task 2's
million rows.

```
==> task1 — fetch, clean, load, and the dashboard
    backend: completed in 10s
    superset: healthy after 65s
    load: 7529 inserted, 0 updated, 0 unchanged -> ohlcv holds 7529 rows

==> task2 — generate, transform, load, verify
    checks: completed in 10s
    integrity checks: 6/6 PASS

==> task3 — API and web page
    api: healthy after 10s
    {"status":"ok","readings":1000000,"summaries":36}
```

### Or one task at a time

Task 1 is independent; task 3 needs task 2 up and loaded first, because it joins
task 2's network and reads its database.

```bash
# Task 1 — dashboard at http://localhost:8088  (admin / admin), charts included
cd task1
cp .env.example .env
sed -i "s|^SUPERSET_SECRET_KEY=.*|SUPERSET_SECRET_KEY=$(openssl rand -base64 42)|" .env
docker compose up -d --build

# Task 2 — generates, transforms, loads and checks, then exits
cd ../task2
docker compose up -d --build
docker compose logs -f checks        # six PASS lines

# Task 3 — web page at http://localhost:8000, API docs at /docs
cd ../task3
docker compose up -d --build
```

Ports: Superset **8088**, task 1's Postgres **5432**, task 2's Postgres **5433**,
task 3's API and page **8000**.

Each task's README covers running it manually, without compose.

## Where each requirement is answered

**Task 1 — data collection and preparation**

| | |
| --- | --- |
| Public API | `task1/backend/pipeline/fetch.py` — Yahoo Finance via `yfinance` |
| ≥ 3 parameters | 5 tickers, set in `.env` |
| Raw saved | one parquet per ticker |
| Loaded with pandas | `transform.py`, `pd.read_parquet` |
| ≥ 3–4 cleaning steps | 5 repairs + 3 normalizations, each a named function |
| Clean output saved | `clean/combined_1d.parquet` |
| Interactive dashboard | `task1/superset/interesting_metrics.zip` — 6 charts, 5 chart types, 2 filters, cross-filtering; imported automatically on start |
| One-page description | **[`task1/WRITEUP.md`](task1/WRITEUP.md)** |
| *Optional:* logging | `logging` throughout the pipeline, INFO per stage and WARNING per dropped row |
| *Optional:* unit tests | `task1/backend/tests/` — 15 tests: one per cleaning decision, plus the download retry |

**Task 2 — PySpark**

| | |
| --- | --- |
| 100k–1M rows generated | `task2/main.py`, `generate_sensor_data` — 1,000,000 rows, all six required columns |
| ≥ 3 complex transformations | 5: window functions, groupBy + multi-field aggregation, pivot, unpivot, date manipulation |
| Saved as parquet | one directory per transformation, types matching the DataFrame |
| Database + table | `task2/db/init/10-schema.sql`, Postgres in Docker |
| Spark → database loader | `task2/load.py`, over JDBC |
| ≥ 3 SQL integrity queries | `task2/db/checks.sql` — 6, each reporting PASS or FAIL |

**Task 3 — frontend and backend**

| | |
| --- | --- |
| Python REST API | FastAPI, `task3/app/` |
| ≥ 2–3 endpoints | 5, including the sensor id list and one sensor's summary |
| pydantic validation | `task3/app/models.py`, request and response both |
| Error and status handling | 404 / 422 / 503 / 500, one error shape — `app/main.py` |
| HTML + CSS + JavaScript | `task3/web/` — Svelte compiles to exactly that, [reasoning in the README](task3/README.md#why-svelte-rather-than-hand-written-javascript) |
| Dropdown + sortable/filterable table | `SensorPicker.svelte`, `ReadingsTable.svelte` (sorted and filtered by the database) |
| README with pipeline and run steps | this file, plus one per task |

**Across all three**

| | |
| --- | --- |
| Modular scripts | one module per stage, no script longer than 350 lines |
| Docstrings / type hints | every module and public function |
