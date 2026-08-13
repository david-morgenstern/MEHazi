"""Turn the raw per-ticker downloads into one tidy frame fit to load.

    normalize -> repair -> validate -> combine

Repairs drop what cannot be trusted and say so; validation then refuses to pass
anything still broken, so a bad download fails the run rather than quietly
becoming a bad chart.
"""

import logging

import pandas as pd
from pandas import DataFrame

from pipeline import manifest
from pipeline.config import (
    CLEAN_MANIFEST_PATH,
    CLEAN_PATH,
    FILLABLE_COLUMNS,
    PRICE_COLUMNS,
)
from pipeline.fetch import raw_path

log = logging.getLogger(__name__)


# --- normalizing -----------------------------------------------------------

def rename_columns(df: DataFrame) -> DataFrame:
    """Give the columns snake_case names."""
    return df.rename(columns=lambda c: c.lower().replace(" ", "_"))


def drop_timezone(df: DataFrame) -> DataFrame:
    """Drop the exchange timezone — daily bars only need a calendar date."""
    index = df.index.tz_localize(None) if df.index.tz else df.index
    return df.set_axis(index.normalize(), axis=0)


def name_index(df: DataFrame) -> DataFrame:
    """Name the index `date` and put it in chronological order."""
    return df.rename_axis("date").sort_index()


# --- repairing -------------------------------------------------------------

def drop_duplicate_dates(df: DataFrame) -> DataFrame:
    """Keep the last bar when a date appears more than once."""
    return df[~df.index.duplicated(keep="last")]


def fill_missing_extras(df: DataFrame) -> DataFrame:
    """Volume and corporate actions are legitimately zero when absent."""
    return df.fillna({column: 0 for column in FILLABLE_COLUMNS if column in df})


def drop_incomplete_prices(df: DataFrame) -> DataFrame:
    """A bar missing any OHLC value cannot be reconstructed, so it goes."""
    return df.dropna(subset=PRICE_COLUMNS)


def drop_nonpositive_prices(df: DataFrame) -> DataFrame:
    """Zero or negative prices are corrupt, not cheap."""
    return df[(df[PRICE_COLUMNS] > 0).all(axis=1)]


def drop_inconsistent_bars(df: DataFrame) -> DataFrame:
    """Drop bars whose high/low do not bracket their open/close."""
    body = df[["open", "close"]]
    return df[(df["high"] >= body.max(axis=1)) & (df["low"] <= body.min(axis=1))]


REPAIRS = (
    drop_duplicate_dates,
    fill_missing_extras,
    drop_incomplete_prices,
    drop_nonpositive_prices,
    drop_inconsistent_bars,
)


def repair(df: DataFrame, ticker: str) -> DataFrame:
    """Run every repair in turn, reporting any rows they had to drop."""
    for step in REPAIRS:
        before = len(df)
        df = step(df)
        if len(df) < before:
            # A warning, not information: every dropped row is data the source
            # gave us and we chose not to trust.
            log.warning("%s: %s dropped %d rows", ticker, step.__name__, before - len(df))
    return df


# --- validating ------------------------------------------------------------

def validate(df: DataFrame, ticker: str) -> None:
    """Raise if a repaired frame is still not fit to use."""
    if df.empty:
        raise ValueError(f"{ticker}: no rows left")

    if df.index.has_duplicates:
        raise ValueError(f"{ticker}: duplicate dates")

    if not df.index.is_monotonic_increasing:
        raise ValueError(f"{ticker}: dates out of order")

    if df[PRICE_COLUMNS].isna().to_numpy().any():
        raise ValueError(f"{ticker}: missing prices")

    if (df[PRICE_COLUMNS] <= 0).to_numpy().any():
        raise ValueError(f"{ticker}: non-positive prices")

    body = df[["open", "close"]]
    if (df["high"] < body.max(axis=1)).any() or (df["low"] > body.min(axis=1)).any():
        raise ValueError(f"{ticker}: high/low do not bracket open/close")


# --- combining -------------------------------------------------------------

def load_one(ticker: str) -> DataFrame:
    """Load one ticker's parquet, normalized, repaired and checked."""
    df = pd.read_parquet(raw_path(ticker))

    df = rename_columns(df)
    df = drop_timezone(df)
    df = name_index(df)
    df = repair(df, ticker)

    validate(df, ticker)
    return df


def combine(tickers: list[str]) -> DataFrame:
    """Load every ticker into one tidy long frame indexed by (date, ticker)."""
    frames = [load_one(t).assign(ticker=t) for t in tickers]
    return pd.concat(frames).set_index("ticker", append=True).sort_index()


def build(tickers: list[str], raw: dict, force: bool = False) -> DataFrame:
    """Return the combined frame, rebuilding it only when the raw data changed.

    The clean manifest holds the hash of every raw frame that went into the
    parquet next to it, so an unchanged download means no work at all.
    """
    missing = [t for t in tickers if t not in raw]
    if missing:
        raise FileNotFoundError(f"not downloaded yet: {', '.join(missing)}")

    wanted = {ticker: raw[ticker]["hash"] for ticker in tickers}
    if not force and CLEAN_PATH.exists() and manifest.read(CLEAN_MANIFEST_PATH) == wanted:
        log.info("clean: cached -> %s", CLEAN_PATH)
        return pd.read_parquet(CLEAN_PATH)

    df = combine(tickers)

    CLEAN_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(CLEAN_PATH)
    manifest.write(CLEAN_MANIFEST_PATH, wanted)
    log.info("clean: rebuilt %d rows -> %s", len(df), CLEAN_PATH)
    return df
