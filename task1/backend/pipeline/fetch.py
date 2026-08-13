"""Download one parquet per ticker, skipping the ones already in hand.

The period is relative, so "5y of daily bars" means a different window today
than it did yesterday. A cached file is therefore only current if it was
fetched today, for the same period and interval.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import yfinance as yf
from pandas import DataFrame

from pipeline import manifest
from pipeline.config import (
    DATA_DIR,
    INTERVAL,
    MAX_WORKERS,
    PERIOD,
    RAW_MANIFEST_PATH,
)

log = logging.getLogger(__name__)

# Yahoo is free, unauthenticated and rate-limited, and there may be a corporate
# proxy in the way. Any one request can fail for reasons that have nothing to do
# with this code and are gone a few seconds later.
DOWNLOAD_ATTEMPTS = 4
DOWNLOAD_BACKOFF_SECONDS = 4


def raw_path(ticker: str) -> Path:
    return DATA_DIR / f"{ticker}_{INTERVAL}.parquet"


def is_current(ticker: str, entry: dict | None) -> bool:
    """True if this ticker's file was fetched today for the window we want."""
    if entry is None or not raw_path(ticker).exists():
        return False

    return (
        entry.get("fetched_on") == date.today().isoformat()
        and entry.get("period") == PERIOD
        and entry.get("interval") == INTERVAL
    )


def history(ticker: str) -> DataFrame:
    """One ticker's bars, retried, because one bad response is not an outage.

    Rate limiting is the common case and it is reported as an *empty frame*
    rather than an error, so an empty result has to count as a failure here —
    otherwise a throttled run loads nothing and calls it success.

    Retries are what makes the difference between a pipeline that fails when the
    network hiccups and one that fails when the data is actually unavailable.
    """
    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        try:
            df = yf.Ticker(ticker).history(period=PERIOD, interval=INTERVAL)
            if df.empty:
                raise ValueError("no data returned")
            return df
        except Exception as exc:
            if attempt == DOWNLOAD_ATTEMPTS:
                raise ValueError(f"{ticker}: giving up after {attempt} attempts ({exc})") from exc

            # Backing off further each time: if this is throttling, asking again
            # immediately is what caused it.
            delay = DOWNLOAD_BACKOFF_SECONDS * attempt
            log.warning(
                "%s: %s (attempt %d/%d), retrying in %ds",
                ticker, exc, attempt, DOWNLOAD_ATTEMPTS, delay,
            )
            time.sleep(delay)

    raise AssertionError("unreachable")


def download(ticker: str) -> dict:
    """Download one ticker, save it, and return its manifest entry."""
    df = history(ticker)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(raw_path(ticker))
    log.info("%s: downloaded %d rows -> %s", ticker, len(df), raw_path(ticker))

    return {
        "fetched_on": date.today().isoformat(),
        "period": PERIOD,
        "interval": INTERVAL,
        "rows": len(df),
        "hash": manifest.frame_hash(df),
    }


def download_all(tickers: list[str], force: bool = False) -> dict:
    """Fetch every ticker whose file is missing or out of date."""
    entries = manifest.read(RAW_MANIFEST_PATH)
    stale = [t for t in tickers if force or not is_current(t, entries.get(t))]

    if stale:
        with ThreadPoolExecutor(max_workers=min(len(stale), MAX_WORKERS)) as pool:
            entries.update(zip(stale, pool.map(download, stale)))
        manifest.write(RAW_MANIFEST_PATH, entries)

    log.info("raw: %d cached, %d downloaded", len(tickers) - len(stale), len(stale))
    return entries
