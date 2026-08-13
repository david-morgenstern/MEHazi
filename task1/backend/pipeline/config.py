"""Everything tunable, read from the environment.

Nothing here needs the image rebuilt to change: point the stack at different
tickers or a longer window by editing .env and re-running the container.
"""

import os
from pathlib import Path

# --- what to fetch ---------------------------------------------------------

TICKERS = [t.strip().upper() for t in os.environ.get("TICKERS", "TSM,NVDA,MU,ASML,TSLA").split(",") if t.strip()]
PERIOD = os.environ.get("PERIOD", "5y")
INTERVAL = os.environ.get("INTERVAL", "1d")
MAX_WORKERS = int(os.environ.get("MAX_WORKERS", "8"))

# --- where the cache lives -------------------------------------------------

# A named volume, so a rerun does not refetch what it already has, and so the
# container itself stays disposable.
DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
RAW_MANIFEST_PATH = DATA_DIR / "raw_manifest.json"
CLEAN_PATH = DATA_DIR / "clean" / f"combined_{INTERVAL}.parquet"
CLEAN_MANIFEST_PATH = CLEAN_PATH.with_suffix(".json")

# --- skipping the cache ----------------------------------------------------

# Both stages are cached, so the normal run is cheap. Set either to redo that
# stage anyway: docker compose run --rm -e FORCE_FETCH=1 backend
FORCE_FETCH = os.environ.get("FORCE_FETCH", "").lower() in {"1", "true", "yes"}
FORCE_REBUILD = os.environ.get("FORCE_REBUILD", "").lower() in {"1", "true", "yes"}

# --- the frame's shape -----------------------------------------------------

PRICE_COLUMNS = ["open", "high", "low", "close"]
FILLABLE_COLUMNS = ["volume", "dividends", "stock_splits"]
