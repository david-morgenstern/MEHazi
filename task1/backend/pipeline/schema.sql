-- The analytics schema: one table the pipeline writes, one view Superset reads.
--
-- Applied on every run, and written so that costs nothing when it is already
-- in place. Owning its own target schema is the backend's job — that is what
-- lets `docker compose up` work against an empty database with no manual step
-- in between, and what lets a schema change ship as a code change.

CREATE TABLE IF NOT EXISTS ohlcv (
    date          date             NOT NULL,
    ticker        text             NOT NULL,
    open          double precision NOT NULL,
    high          double precision NOT NULL,
    low           double precision NOT NULL,
    close         double precision NOT NULL,
    volume        bigint           NOT NULL,
    dividends     double precision NOT NULL,
    stock_splits  double precision NOT NULL,
    PRIMARY KEY (date, ticker)
);

-- The primary key is the wrong way round for "one ticker over time", which is
-- what every chart on the dashboard asks for.
CREATE INDEX IF NOT EXISTS ohlcv_ticker_date_idx ON ohlcv (ticker, date);


-- Raw closing prices are useless on a shared axis: ASML trades near 1000 while
-- MU is in the tens, so the cheaper tickers flatten into the floor. Everything
-- below is derived to be comparable across tickers instead.
CREATE OR REPLACE VIEW ticker_metrics AS
WITH returns AS (
    SELECT
        date, ticker, open, high, low, close, volume,
        -- NULLIF guards the first row, where LAG has nothing to divide into
        close / NULLIF(LAG(close) OVER (PARTITION BY ticker ORDER BY date), 0) - 1
            AS ret,
        FIRST_VALUE(close) OVER (PARTITION BY ticker ORDER BY date)
            AS first_close,
        MAX(close) OVER (PARTITION BY ticker ORDER BY date ROWS UNBOUNDED PRECEDING)
            AS peak_close
    FROM ohlcv
)
SELECT
    date,
    ticker,
    open, high, low, close, volume,

    -- every ticker starts at 100: 250 means it has 2.5x'd since the first day
    100.0 * close / first_close                      AS indexed_close,

    -- one day's move, in percent
    100.0 * ret                                      AS daily_return_pct,

    -- distance below the running all-time high; always <= 0
    100.0 * (close / peak_close - 1)                 AS drawdown_pct,

    -- 30-day realised volatility, annualised (252 trading days a year)
    100.0 * SQRT(252) * STDDEV_SAMP(ret) OVER (
        PARTITION BY ticker ORDER BY date
        ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
    )                                                AS volatility_30d_pct

FROM returns;
