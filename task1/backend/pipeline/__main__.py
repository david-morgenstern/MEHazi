"""Run the pipeline once, end to end, then exit.

    yfinance -> raw parquet -> clean parquet -> postgres

Every stage is cached or idempotent, so this is safe to run as often as you
like: nothing is refetched, rebuilt or rewritten unless it actually changed.
"""

import logging
import sys

from pipeline import fetch, load, transform
from pipeline.config import FORCE_FETCH, FORCE_REBUILD, INTERVAL, PERIOD, TICKERS

log = logging.getLogger("pipeline")


def main() -> int:
    log.info("start: %d tickers | %s of %s bars -> %s", len(TICKERS), PERIOD, INTERVAL, load.target())

    raw = fetch.download_all(TICKERS, force=FORCE_FETCH)
    df = transform.build(TICKERS, raw, force=FORCE_REBUILD)
    load.load(df)

    dates = df.index.get_level_values("date")
    log.info("done: %d rows | %s -> %s", len(df), dates.min().date(), dates.max().date())
    return 0


if __name__ == "__main__":
    # Configured once, here, because this is the only entry point. Importing
    # any other module leaves logging alone, which is what a library should do.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    # yfinance chats at INFO about a timezone cache it does not need — and once
    # per thread, so six tickers means six copies. Anything it has to say that
    # actually matters is a warning.
    logging.getLogger("yfinance").setLevel(logging.WARNING)

    sys.exit(main())
