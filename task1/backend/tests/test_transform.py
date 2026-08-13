"""Tests for the cleaning steps in pipeline.transform.

These functions are the reason the pipeline can be trusted, and they are pure --
a frame in, a frame out, no network, no database, no files. That is what makes
them worth testing and cheap to test: every case below is a handful of rows
written by hand, so a failure points at one rule rather than at "the pipeline".
"""

import pandas as pd
import pytest
from pandas import DataFrame

from pipeline import transform


def bars(**columns) -> DataFrame:
    """A frame shaped like one ticker's download, dated from 2024-01-01.

    Only the columns a test cares about need values; the rest are filled with
    a plausible, consistent bar so nothing else trips the rule under test.
    """
    length = len(next(iter(columns.values())))
    frame = DataFrame(
        {
            "open": [10.0] * length,
            "high": [11.0] * length,
            "low": [9.0] * length,
            "close": [10.5] * length,
            "volume": [1000] * length,
            "dividends": [0.0] * length,
            "stock_splits": [0.0] * length,
            **columns,
        },
        index=pd.date_range("2024-01-01", periods=length, name="date"),
    )
    return frame


# --- the repairs -----------------------------------------------------------

def test_missing_prices_are_dropped_not_filled():
    """A bar without a close cannot be reconstructed, so the row goes.

    The opposite decision -- forward-filling -- would invent a trading day that
    never happened, and every metric downstream would inherit it.
    """
    df = bars(close=[10.5, None, 12.0])

    kept = transform.drop_incomplete_prices(df)

    assert len(kept) == 2
    assert kept["close"].tolist() == [10.5, 12.0]


def test_volume_and_corporate_actions_are_filled_with_zero():
    """Unlike prices, these are legitimately zero when absent."""
    df = bars(volume=[1000, None, 3000], dividends=[0.0, None, 0.0])

    filled = transform.fill_missing_extras(df)

    assert filled["volume"].tolist() == [1000, 0, 3000]
    assert filled["dividends"].tolist() == [0.0, 0.0, 0.0]


def test_the_last_bar_wins_when_a_date_repeats():
    """A repeated date is a correction, and the later one is the correction."""
    df = bars(close=[10.0, 20.0, 30.0])
    df.index = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-02"])

    deduplicated = transform.drop_duplicate_dates(df)

    assert len(deduplicated) == 2
    assert deduplicated["close"].tolist() == [10.0, 30.0]


def test_bars_whose_high_and_low_do_not_bracket_the_body_are_dropped():
    """A high below the close is arithmetically impossible, so it is corrupt."""
    df = bars(high=[11.0, 10.0, 11.0], close=[10.5, 10.5, 10.5])

    kept = transform.drop_inconsistent_bars(df)

    assert len(kept) == 2
    assert kept.index.tolist() == [df.index[0], df.index[2]]


@pytest.mark.parametrize("bad_close", [0.0, -5.0])
def test_zero_and_negative_prices_are_dropped(bad_close):
    """A share does not trade at or below nothing; such a row is corrupt."""
    df = bars(close=[10.5, bad_close, 12.0])

    kept = transform.drop_nonpositive_prices(df)

    assert kept["close"].tolist() == [10.5, 12.0]


# --- validation ------------------------------------------------------------

def test_validate_accepts_a_clean_frame():
    transform.validate(bars(close=[10.5, 10.6, 10.7]), "TEST")


def test_validate_rejects_a_frame_the_repairs_emptied():
    """The guard that turns a bad download into a failed run, not a bad chart."""
    df = bars(close=[10.5]).iloc[:0]

    with pytest.raises(ValueError, match="no rows left"):
        transform.validate(df, "TEST")


def test_validate_rejects_dates_out_of_order():
    """Every window function downstream assumes chronological order."""
    df = bars(close=[10.5, 10.6])
    df.index = pd.to_datetime(["2024-01-02", "2024-01-01"])

    with pytest.raises(ValueError, match="out of order"):
        transform.validate(df, "TEST")


# --- normalizing -----------------------------------------------------------

def test_columns_are_renamed_to_snake_case():
    """yfinance returns 'Stock Splits'; the database column is stock_splits."""
    df = DataFrame({"Open": [1.0], "Stock Splits": [0.0]})

    assert transform.rename_columns(df).columns.tolist() == ["open", "stock_splits"]


def test_the_exchange_timezone_is_dropped_and_the_time_normalized():
    """Daily bars need a calendar date; keeping the timezone splits one day in
    two when tickers trade on different exchanges."""
    df = DataFrame(
        {"close": [10.0]},
        index=pd.to_datetime(["2024-01-01 14:30:00-05:00"]),
    )

    result = transform.drop_timezone(df)

    assert result.index.tz is None
    assert result.index[0] == pd.Timestamp("2024-01-01")
