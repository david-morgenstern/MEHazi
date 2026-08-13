"""Write the combined frame into the analytics database.

The load is an upsert keyed on (date, ticker), which is what makes running the
pipeline twice harmless: the second run finds every row already present and
identical, changes nothing, and reports as much. Charts built on the table
survive a reload too, which dropping and recreating it would not allow.
"""

import io
import logging
import os
import time
from pathlib import Path

import pandas as pd
import psycopg2
from pandas import DataFrame

log = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

TABLE = "ohlcv"
KEY = ("date", "ticker")
VALUES = ("open", "high", "low", "close", "volume", "dividends", "stock_splits")
COLUMNS = KEY + VALUES

CONNECT_ATTEMPTS = 30
CONNECT_BACKOFF_SECONDS = 2


def connect():
    """Connect to Postgres, waiting for it to accept connections.

    Compose already holds the backend back until the database reports healthy,
    but the wait means the container also works started on its own, in any
    order, against a database that is still coming up.

    No connection arguments: libpq reads PGHOST/PGUSER/... from the environment.
    """
    for attempt in range(1, CONNECT_ATTEMPTS + 1):
        try:
            return psycopg2.connect()
        except psycopg2.OperationalError:
            if attempt == CONNECT_ATTEMPTS:
                raise
            log.warning("db: not ready, retrying (%d/%d)", attempt, CONNECT_ATTEMPTS)
            time.sleep(CONNECT_BACKOFF_SECONDS)

    raise AssertionError("unreachable")


def to_rows(df: DataFrame) -> DataFrame:
    """Flatten the (date, ticker) index into columns, in the table's order."""
    flat = df.reset_index()

    missing = [c for c in COLUMNS if c not in flat.columns]
    if missing:
        raise ValueError(f"combined frame is missing columns: {', '.join(missing)}")

    flat["date"] = pd.to_datetime(flat["date"]).dt.date
    return flat[list(COLUMNS)]


def to_csv_buffer(rows: DataFrame) -> io.StringIO:
    """Serialise for COPY, which is far faster than row-by-row inserts."""
    buffer = io.StringIO()
    rows.to_csv(buffer, index=False, header=False)
    buffer.seek(0)
    return buffer


def upsert_statement() -> str:
    """INSERT ... ON CONFLICT, skipping rows that would not actually change.

    The WHERE on the DO UPDATE is what separates "already loaded" from "loaded
    again": without it every rerun rewrites every row and reports thousands of
    updates, which looks like work but is not.
    """
    columns = ", ".join(COLUMNS)
    assignments = ", ".join(f"{c} = EXCLUDED.{c}" for c in VALUES)
    current = ", ".join(f"{TABLE}.{c}" for c in VALUES)
    incoming = ", ".join(f"EXCLUDED.{c}" for c in VALUES)

    return f"""
        WITH changed AS (
            INSERT INTO {TABLE} ({columns})
            SELECT {columns} FROM incoming
            ON CONFLICT ({", ".join(KEY)}) DO UPDATE SET {assignments}
            WHERE ({current}) IS DISTINCT FROM ({incoming})
            -- a row Postgres had to insert has no previous version to lock
            RETURNING xmax = 0 AS inserted
        )
        SELECT
            count(*) FILTER (WHERE inserted)     AS inserted,
            count(*) FILTER (WHERE NOT inserted) AS updated
        FROM changed
    """


def load(df: DataFrame) -> None:
    """Apply the schema, then upsert the frame in a single transaction."""
    rows = to_rows(df)

    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(SCHEMA_PATH.read_text())

        # Staged first so the COPY and the upsert are one atomic step: readers
        # see the old table until the whole batch is in.
        cursor.execute(f"CREATE TEMP TABLE incoming (LIKE {TABLE}) ON COMMIT DROP")
        cursor.copy_expert(
            f"COPY incoming ({', '.join(COLUMNS)}) FROM STDIN WITH (FORMAT csv)",
            to_csv_buffer(rows),
        )

        cursor.execute(upsert_statement())
        inserted, updated = cursor.fetchone()

        cursor.execute(f"SELECT count(*), min(date), max(date) FROM {TABLE}")
        total, first, last = cursor.fetchone()

    unchanged = len(rows) - inserted - updated
    log.info(
        "load: %d inserted, %d updated, %d unchanged -> %s holds %d rows | %s -> %s",
        inserted, updated, unchanged, TABLE, total, first, last,
    )


def target() -> str:
    """Where this run is pointed, for the log line."""
    host = os.environ.get("PGHOST", "localhost")
    database = os.environ.get("PGDATABASE", os.environ.get("PGUSER", "postgres"))
    return f"{host}/{database}"
