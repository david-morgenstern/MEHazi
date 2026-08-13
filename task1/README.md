# Task 1 — data collection and preparation

Five years of daily bars for five semiconductor and EV tickers: fetched from a
public API, cleaned with pandas, loaded into Postgres and charted on an
interactive dashboard.

**The one-page description the brief asks for (point 8) is [`WRITEUP.md`](WRITEUP.md)** —
data source, processing steps and every cleaning decision with its reasoning.

## Why Superset instead of Tableau or Spotfire

The brief suggests Tableau or Spotfire "with a trial version". This uses
**Apache Superset** instead, and that is a deliberate choice:

- **The deliverable stays runnable.** A Tableau or Spotfire workbook is only
  reviewable by someone who has installed that product and started their own
  trial clock. Superset comes up with `docker compose up` and the dashboard is
  in this repository as an importable file — no account, no download, no
  fourteen-day limit.
- **It is version-controllable.** `superset/interesting_metrics.zip` is a folder
  of YAML: the charts, the dataset and the connection are all readable text that
  diffs like code. A `.twbx` is an opaque binary blob in a git repository.
- **It fits the rest of the stack.** The data is already in Postgres in a
  container; Superset is one more container on the same network reading the same
  view. Nothing is exported, copied or re-uploaded to make the dashboard work.
- **It is the same skill.** Everything the point asks for is here: a saved,
  cleaned table as the source, six charts across five visualization types, and
  interactivity through native filters and cross-filtering.

If a Tableau workbook is required for the evaluation, say so — the cleaned
output is a plain parquet/CSV table and would connect to it directly.

## Architecture

Three containers on one network, one image each:

```
                      ┌──────────────────────────────────────┐
   yfinance ─────────▶│ backend    fetch → clean → load      │
                      │            python, runs once, exits  │
                      └──────────────┬───────────────────────┘
                                     │ upsert on (date, ticker)
                                     ▼
                      ┌──────────────────────────────────────┐
                      │ db         analytics   ohlcv         │
                      │                        ticker_metrics│
                      │            superset    dashboards    │
                      └──────────────┬───────────────────────┘
                                     │ reads
                                     ▼
                      ┌──────────────────────────────────────┐
   you, colleagues ──▶│ superset   :8088                     │
                      │            imports its dashboard on  │
                      │            start, then serves it     │
                      └──────────────────────────────────────┘
```

Each layer owns one thing:

- **db** owns the two databases and who may write to them. They are separate on
  purpose: resetting Superset never touches the data, reloading the data never
  disturbs the dashboards.
- **backend** owns the analytics schema and the data in it — the `ohlcv` table,
  the `ticker_metrics` view, and the pipeline that fills them.
- **superset** owns the presentation, including the dashboard itself: the
  export is in the image and imported on start.

Nothing is bind-mounted. Config and SQL are baked into the images, so any one of
the three runs on its own with `docker run` given the same environment.

## Run

```bash
cd task1
docker compose up -d --build
```

`.env` is committed with working defaults, so there is nothing to fill in first.

Superset takes about a minute on first start; watch `docker compose ps` until it
reports `healthy`. `mehazi-backend` showing `Exited (0)` is correct — it is a
batch job, not a service.

Then open **<http://localhost:8088>** and log in with `admin` / `admin`. The
dashboard is already there.

### How the dashboard gets there

`superset/interesting_metrics.zip` is baked into the image, and the entrypoint
imports it on every start. Nothing is uploaded by hand and there is no setup
wizard: a fresh volume comes up with the charts already drawn.

Re-importing on each start is safe — objects are matched on uuid and updated in
place, so a restart neither duplicates a chart nor discards an edit to one. The
dashboard also survives a restart on its own merits: Superset keeps its state in
Postgres, in the same volume as the data. Only `docker compose down -v` discards
it, and the next start puts it back.

> **The password dance, if you ever re-export.** Superset *strips passwords out
> of an export* — the connection inside the zip carries the literal placeholder
> `XXXXXXXXXX`. The UI's import dialog is what normally asks you for the real
> one; `superset import-dashboards` has no such flag and simply refuses the file
> with *"Must provide a password for the database"*. So `entrypoint.sh` writes
> the password back into a copy of the zip before importing it, reading it from
> the environment compose already passes in.
>
> Two related traps, both worth knowing:
>
> - On import the connection is matched on **uuid, never on name**. If the uuid
>   is already known, the zip's connection details are ignored entirely — so
>   **re-importing never repairs a broken connection.** That is why the
>   entrypoint also runs `superset set-database-uri` afterwards, which does
>   repair it. If you ever see *"password authentication failed for user
>   analytics"* under a chart, that is the failure this fixes; restarting the
>   container is enough.
> - An export remembers the **hostname** it was made against. This one says
>   `db`, which is what Postgres is called on this stack. An export made
>   elsewhere may say something else and will fail on a fresh volume with
>   `could not translate host name`.

### If a chart says "DB engine Error"

Superset keeps the **charts** and the **connection to the data** as two separate
things, and only the connection holds a password. Charts can therefore import
perfectly and still fail the moment they run a query. The first line of the
error says which of three problems it is:

| The error says | What it means | Fix |
| --- | --- | --- |
| `password authentication failed for user "analytics"` | the connection has the wrong password, or still has the export's `XXXXXXXXXX` placeholder | `docker compose restart superset` |
| `could not translate host name` | the export was made against a stack where Postgres had another name | edit the connection's host to `db` |
| `relation "ohlcv" does not exist` | the connection is fine, the data is not there | `docker compose run --rm backend` |

The first one is the common one, and restarting fixes it because the entrypoint
re-applies the password on every start. Two other ways, if you would rather not
restart:

- **In the UI** — Settings → Database Connections → the pencil on `analytics_db`
  → Basic → type the password → **Test connection** → Finish. The password is
  `ANALYTICS_PASSWORD` in `.env`, `analytics` by default.
- **In one command:**

  ```bash
  docker compose exec superset superset set-database-uri \
    -d analytics_db -u "postgresql+psycopg2://analytics:analytics@db:5432/analytics"
  ```

What will *not* work is importing the zip again: connections are matched on
uuid, so Superset sees one it already knows and ignores the file's copy
entirely. Re-importing never repairs a connection, however carefully you fill in
the dialog.

### Changing the dashboard

Edit the charts in the UI, then export and replace the file:

1. Dashboards → the ⋯ menu on **Interesting metrics** → **Export**.
2. Replace `superset/interesting_metrics.zip` with the downloaded file, keeping
   the name.
3. `docker compose up -d --build superset`.

The new export will have its password stripped like every other one — that is
fine, the entrypoint puts it back.

## The dashboard

**Interesting metrics** — six charts over `ticker_metrics`, five visualization
types:

| Chart | Type | Shows |
| --- | --- | --- |
| Relative Performance | line | every ticker rebased to 100 on its first day, so they are comparable on one axis |
| Percentage Change | bar | daily returns |
| Drawdown | area | how far each ticker sits below its own running all-time high |
| Volatility regimes | line | 30-day realised volatility, annualised |
| Return distributions | box plot | the spread and tails of daily returns per ticker |
| Scoreboard | table | the numbers behind the charts |

It is interactive in three ways: a **ticker filter** and a **time-range filter**
apply to every chart at once, and **cross-filtering** is on — clicking a series
in one chart filters the others.

## Refreshing the data

```bash
docker compose run --rm backend
```

Every stage is cached or idempotent, so this is cheap and safe to repeat. A
second run in the same day reports what it did:

```
raw: 5 cached, 0 downloaded
clean: cached -> /data/clean/combined_1d.parquet
load: 0 inserted, 0 updated, 6275 unchanged -> ohlcv holds 6275 rows
```

Three things make that true:

- **Fetch** skips any ticker already downloaded today for the same window. "5y"
  is relative, so a file fetched yesterday covers a window that has since moved —
  the manifest records what each file was fetched *for*, not just that it exists.
  A download that fails is retried four times with a widening backoff, because
  Yahoo is unauthenticated and rate-limited: a hiccup should cost seconds, not
  the run.
- **Clean** rebuilds only when a raw frame's hash changed.
- **Load** upserts on `(date, ticker)` and skips rows whose values are already
  identical.

To redo a stage anyway:

```bash
docker compose run --rm -e FORCE_FETCH=1 backend    # ignore the download cache
docker compose run --rm -e FORCE_REBUILD=1 backend  # ignore the parquet cache
```

## Tests

The cleaning functions are pure — a frame in, a frame out — which is what makes
them worth testing and cheap to test:

```bash
cd task1/backend
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest
```

```
tests/test_fetch.py ....                                [ 26%]
tests/test_transform.py ...........                     [100%]
15 passed
```

`test_transform.py` pins one cleaning decision each from `WRITEUP.md`: that a
missing price is dropped rather than filled, that a missing volume is filled
rather than dropped, that the later row wins on a duplicated date, and that
validation refuses a frame the repairs emptied.

`test_fetch.py` covers the download retry without touching the network —
`yf.Ticker` is replaced with a stub that fails on cue. The case worth knowing is
that **an empty frame counts as a failure**: Yahoo reports rate limiting with an
empty result rather than an error, so accepting it would load nothing and call
the run a success.

## The data

`ohlcv` is one row per ticker per trading day, straight from the pipeline. Rows
survive a reload, so the table accumulates history as the 5-year window rolls
forward.

`ticker_metrics` is a view over it, and is what the dashboard charts:

| Column | Meaning |
| --- | --- |
| `indexed_close` | close rebased to 100 on the ticker's first day |
| `daily_return_pct` | one day's move, in percent |
| `drawdown_pct` | distance below the running all-time high; always ≤ 0 |
| `volatility_30d_pct` | 30-day realised volatility, annualised |

It is a database view rather than a saved query, so the SQL is versioned with the
pipeline and Superset only ever sees a plain table.

```bash
docker compose exec db psql -U analytics -d analytics -c 'select * from ticker_metrics limit 5'
```

## Configuration

Everything tunable lives in `.env`. Changing the tickers or the window needs no
rebuild:

```bash
TICKERS=AMD,INTC,QCOM
PERIOD=10y
```

```bash
docker compose run --rm backend
```

`PROXY` is only needed behind a corporate proxy. Docker injects the host's proxy
settings into containers, but those point at `127.0.0.1`, which inside a
container is the container itself — so set `PROXY` to the same proxy reached
through `host.docker.internal`.

## Layout

```
compose.yaml            the three services, one network, three volumes
.env.example            every credential and setting, documented
WRITEUP.md              the one-page description: source, steps, decisions

db/
  Dockerfile            postgres + the bootstrap below
  init/10-bootstrap.sh  creates the analytics and superset databases

backend/
  Dockerfile            two-stage build, runs unprivileged
  requirements.txt      pinned
  requirements-dev.txt  the above, plus pytest
  pytest.ini            so `pytest` finds the package without an install
  pipeline/
    __main__.py         fetch → transform → load, then exit
    config.py           everything read from the environment
    fetch.py            yfinance, one parquet per ticker, cached
    transform.py        normalize → repair → validate → combine
    load.py             upsert into postgres
    schema.sql          the ohlcv table and the ticker_metrics view
    manifest.py         the JSON side-files that make the cache skippable
  tests/
    test_fetch.py       the download retry, with the network stubbed out
    test_transform.py   one test per cleaning decision

superset/
  Dockerfile                 superset + a postgres driver + the dashboard
  entrypoint.sh              wait for db, migrate, create admin, import, serve
  superset_config.py         where Superset keeps its own state
  interesting_metrics.zip    the dashboard, baked into the image
```

## Resetting

```bash
docker compose down          # stop, keep the data
docker compose down -v       # stop and drop everything: data, cache, dashboards
```
