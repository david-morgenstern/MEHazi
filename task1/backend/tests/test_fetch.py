"""Tests for the download retry in pipeline.fetch.

Yahoo is free, unauthenticated and rate-limited, so the interesting behaviour
here is what happens when a request does *not* work. None of these tests touch
the network: `yf.Ticker` is replaced with a stub that fails on cue, and the
backoff sleep is stubbed out so the suite stays instant.
"""

import pandas as pd
import pytest

from pipeline import fetch


class FakeTicker:
    """Stands in for `yf.Ticker`, failing a set number of times first.

    Records every call so a test can assert how many attempts were made.
    """

    calls = 0

    def __init__(self, ticker: str, failures: int = 0, empty: bool = False):
        self.failures = failures
        self.empty = empty

    def history(self, period: str, interval: str) -> pd.DataFrame:
        type(self).calls += 1
        if type(self).calls <= self.failures:
            raise ConnectionError("connection reset by peer")
        if self.empty:
            return pd.DataFrame()
        return pd.DataFrame({"Close": [10.0]}, index=pd.to_datetime(["2024-01-01"]))


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    """Backoff is real seconds in production and wasted ones in a test."""
    monkeypatch.setattr(fetch.time, "sleep", lambda seconds: None)
    FakeTicker.calls = 0


def use(monkeypatch, **kwargs):
    monkeypatch.setattr(fetch.yf, "Ticker", lambda ticker: FakeTicker(ticker, **kwargs))


def test_a_download_that_works_is_not_retried(monkeypatch):
    use(monkeypatch)

    assert len(fetch.history("TSM")) == 1
    assert FakeTicker.calls == 1


def test_a_failing_download_is_retried_and_can_still_succeed(monkeypatch):
    """The whole point: a hiccup should cost seconds, not the run."""
    use(monkeypatch, failures=2)

    assert len(fetch.history("TSM")) == 1
    assert FakeTicker.calls == 3


def test_an_empty_frame_counts_as_a_failure(monkeypatch):
    """Yahoo reports throttling with an empty frame, not an error.

    Accepting it would load nothing and report success, which is worse than
    failing: the dashboard would quietly go blank.
    """
    use(monkeypatch, empty=True)

    with pytest.raises(ValueError, match="giving up"):
        fetch.history("TSM")

    assert FakeTicker.calls == fetch.DOWNLOAD_ATTEMPTS


def test_it_gives_up_eventually_rather_than_retrying_forever(monkeypatch):
    """Retries are for transient failures; a delisted ticker is not one."""
    use(monkeypatch, failures=99)

    with pytest.raises(ValueError, match="TSM: giving up after 4 attempts"):
        fetch.history("TSM")

    assert FakeTicker.calls == fetch.DOWNLOAD_ATTEMPTS
