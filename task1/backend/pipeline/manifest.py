"""Small JSON side-files recording what the cache currently holds.

A manifest is what makes each stage skippable: it says which inputs produced
the file sitting next to it, so the stage can tell "already done" from "done,
but for something else".
"""

import hashlib
import json
from pathlib import Path

import pandas as pd
from pandas import DataFrame


def read(path: Path) -> dict:
    """Read a manifest, treating a missing one as empty."""
    return json.loads(path.read_text()) if path.exists() else {}


def write(path: Path, manifest: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True))


def frame_hash(df: DataFrame) -> str:
    """Hash a frame's contents, independent of how parquet happened to store it."""
    rows = pd.util.hash_pandas_object(df, index=True).to_numpy()
    return hashlib.sha256(rows.tobytes()).hexdigest()
