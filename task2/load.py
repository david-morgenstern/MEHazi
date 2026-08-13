"""Load the processed parquet into PostgreSQL.

The second half of the pipeline: `main.py` generates and transforms, this reads
what it wrote and pushes it over JDBC into the tables `db/init/10-schema.sql`
created. Spark writes directly from the executors, so the rows never pass
through the driver on their way to the database.
"""

from __future__ import annotations

import logging
import os
import sys
import time

from pyspark.sql import DataFrame, SparkSession

log = logging.getLogger("load")

# Which parquet output lands in which table.
TABLES = {
    "window": "readings",
    "aggregate": "location_stats",
}

# One JDBC connection per partition, so this is a cap on concurrent writers
# rather than a target -- eight is plenty for a database with one disk.
WRITE_PARTITIONS = 8

# Rows per round trip. The driver option below rewrites each batch as a single
# multi-row INSERT, which is where most of the throughput comes from.
BATCH_SIZE = 10_000


def _table_column(name: str) -> str:
    """The parquet's column name as the table spells it."""
    # Everything else is already underscored, so lowercasing is enough.
    return {"Date": "reading_date"}.get(name, name.lower())


def jdbc_options() -> dict[str, str]:
    """Connection settings, read from the environment Postgres itself uses."""
    host = os.environ.get("PGHOST", "db")
    port = os.environ.get("PGPORT", "5432")
    database = os.environ.get("PGDATABASE", "sensors")

    return {
        # reWriteBatchedInserts collapses a batch of INSERTs into one statement
        # with many rows; on a load this size it is worth several times the
        # throughput, and it costs nothing but the flag.
        "url": f"jdbc:postgresql://{host}:{port}/{database}?reWriteBatchedInserts=true",
        "driver": "org.postgresql.Driver",
        "user": os.environ.get("PGUSER", "sensors"),
        "password": os.environ.get("PGPASSWORD", "sensors"),
    }


def load_table(frame: DataFrame, table: str, options: dict[str, str]) -> int:
    """Replace `table`'s contents with `frame`, and return the rows now in it."""
    renamed = frame.toDF(*[_table_column(column) for column in frame.columns])
    log.info("%-15s <- %s", table, ", ".join(renamed.columns))

    start = time.perf_counter()
    (
        # coalesce, not repartition: capping the writers costs nothing, while
        # reshuffling a million rows to reach the same number would.
        renamed.coalesce(WRITE_PARTITIONS)
        .write.format("jdbc")
        .options(**options, dbtable=table, batchsize=BATCH_SIZE)
        # Overwrite would otherwise drop the table and let Spark invent its own
        # DDL; truncate keeps the schema, its types and its constraints.
        .option("truncate", "true")
        .mode("overwrite")
        .save()
    )
    elapsed = time.perf_counter() - start

    # Asking the database rather than the frame: this counts what actually
    # committed, which is the only number worth logging here.
    landed = (
        frame.sparkSession.read.format("jdbc")
        .options(**options, query=f"SELECT count(*) AS n FROM {table}")
        .load()
        .first()["n"]
    )
    log.info("%-15s %9s rows in %5.1fs", table, f"{landed:,}", elapsed)
    return landed


def main() -> int:
    input_dir = os.environ.get("OUTPUT_DIR", "output").rstrip("/")
    options = jdbc_options()

    spark = SparkSession.builder.appName("sensor-load").getOrCreate()
    spark.sparkContext.setLogLevel("WARN")

    failed = []
    try:
        for source, table in TABLES.items():
            path = f"{input_dir}/{source}"
            try:
                load_table(spark.read.parquet(path), table, options)
            except Exception:  # a failed table should not hide the next one
                log.exception("%-15s failed to load from %s", table, path)
                failed.append(table)
    finally:
        spark.stop()

    if failed:
        log.error("%d of %d tables did not load: %s", len(failed), len(TABLES), ", ".join(failed))
        return 1

    log.info("%d tables loaded", len(TABLES))
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    sys.exit(main())
