# Task 1 — data source, processing steps, cleaning decisions

*The one-page description required by point 8. Everything here is implemented in
`backend/pipeline/`; `README.md` covers how to run it.*

## The data source

**Yahoo Finance**, through the `yfinance` package. It is public, needs no API
key and no registration, and returns a clean daily OHLCV series per instrument.

The brief asks for at least three different points or parameters. The parameter
varied here is the **instrument**: five years of daily bars for five
semiconductor and EV tickers — **TSM, NVDA, MU, ASML, TSLA** — about 6,300 rows
in total. All five are set in `.env`, so the window and the instrument list
change without touching code.

## The processing steps

```
yfinance  →  raw parquet (one per ticker)  →  pandas  →  clean parquet  →  Postgres  →  Superset
```

1. **Fetch** (`fetch.py`) — one download per ticker, saved unmodified as
   `{TICKER}_1d.parquet`. Raw stays raw: nothing is cleaned before it is on disk,
   so the cleaning is always reproducible from what the API actually returned.
2. **Load** (`transform.py`) — each raw parquet is read back with
   `pandas.read_parquet`.
3. **Clean** — normalize, repair, validate, described below.
4. **Save** — all five tickers combined into one tidy long frame indexed by
   `(date, ticker)`, written to `clean/combined_1d.parquet`.
5. **Load to Postgres** (`load.py`) — upserted into `ohlcv` on `(date, ticker)`,
   so re-running the pipeline changes nothing and never breaks the dashboard.
6. **Present** — Superset charts the `ticker_metrics` view over that table.

## The cleaning decisions

**Normalizing** — the parts that are only about shape:

| Step | Decision |
| --- | --- |
| Column names | `Stock Splits` → `stock_splits`: snake_case, so a column name never needs quoting in SQL |
| Timestamps | The exchange timezone is dropped and the time normalized to midnight. A daily bar is a calendar day; keeping the timezone would split one trading day into two when tickers list on different exchanges |
| Index | Named `date` and sorted, because every metric downstream is a window function that assumes chronological order |

**Repairing** — where the real decisions are. Each rule reports what it dropped:

| Problem | Decision | Why |
| --- | --- | --- |
| A date appears twice | Keep the **last** row | A repeated date is a correction, and the later value is the correction |
| `volume`, `dividends`, `stock_splits` missing | Fill with **0** | These are legitimately zero when absent — no dividend was paid, no split happened |
| Any of open/high/low/close missing | **Drop the row** | A price cannot be reconstructed from the others. Forward-filling would invent a trading day that never happened, and every return, drawdown and volatility figure downstream would inherit that invention |
| Price ≤ 0 | **Drop the row** | A share does not trade at or below nothing; such a row is corrupt, not cheap |
| `high` < max(open, close), or `low` > min(open, close) | **Drop the row** | Arithmetically impossible — the bar is corrupt however plausible each number looks alone |

The split between "fill" and "drop" is the whole of it: **a value that is
missing because nothing happened is filled with zero; a value that is missing
because the data is broken is dropped, never guessed.**

**Validating** — after the repairs, `validate()` re-checks every rule and raises
if anything still fails. Repairs alone would let a badly broken download through
as a very small, very clean frame. A run that cannot produce trustworthy data
fails loudly instead of quietly loading a bad chart.

## New columns

`ticker` is added when the five frames are combined — without it the rows lose
the only thing distinguishing them.

The derived columns live in the `ticker_metrics` view (`schema.sql`) rather than
in pandas, because they are pure functions of the stored table and are cheaper to
keep as SQL than to recompute and re-store. Raw closes are not comparable on a
shared axis — ASML trades near 1,000 while MU is in the tens — so the view
derives: `indexed_close` (rebased to 100 on each ticker's first day),
`daily_return_pct`, `drawdown_pct` (distance below the running all-time high) and
`volatility_30d_pct` (30-day realised volatility, annualised).

Those four are what the dashboard charts.
