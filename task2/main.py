"""Sensor data generator built out of Spark expressions.

Nothing is generated on the driver: the rows come from ``spark.range`` and every
column is a native Spark expression over the row id, so the work is split across
the cluster and no Python objects are ever serialised. A million rows costs
about as much as reading them would.

Every value is derived from ``hash(key, seed)`` rather than ``rand()``, which
makes the frame reproducible from the seed alone -- the same row id yields the
same sensor, date and reading no matter how many partitions the range is cut
into, or how often Spark recomputes the plan.
"""

from __future__ import annotations

import logging
import math
import os
import time
from datetime import date

from pyspark import StorageLevel
from pyspark.sql import Column, DataFrame, SparkSession, Window
from pyspark.sql import functions as F

log = logging.getLogger(__name__)

# Where do_transformations puts its parquet, and how much data to make. Both
# come from the environment so the container needs no arguments.
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "output")
NUM_ROWS = int(os.environ.get("NUM_ROWS", 1_000_000))

# A sensor sits in one place, so Location follows the sensor, not the row.
LOCATIONS = ["Hungary", "Germany", "Austria", "Slovakia", "Romania", "Poland"]

# Parameter -> (mean, standard deviation) of the readings it produces.
PARAMETERS = {
    "Offset": (0.0, 0.5),
    "Noise": (0.0, 1.0),
    "Temperature": (22.0, 5.0),
    "Pressure": (1013.0, 12.0),
    "Humidity": (45.0, 8.0),
    "Voltage": (3.3, 0.15),
}

# Distinct salts, so the columns do not correlate with one another.
_SEED_SENSOR = 11
_SEED_LOCATION = 23
_SEED_PARAM = 37
_SEED_DATE = 41
_SEED_VALUE_A = 53
_SEED_VALUE_B = 67
_SEED_FAULT = 71
_SEED_ID_HEAD = 83
_SEED_ID_TAIL = 97

# A reading this far from the mean is reported as Bad, plus a flat failure rate
# on top for faults that a plausible value hides.
_OUTLIER_SIGMA = 3.0
_FAULT_RATE = 0.005

_INT32_MAX = 2147483647

# Day zero for turning a date into the integer a range frame can offset from.
_EPOCH = date(1970, 1, 1)


def _uniform(key: Column, seed: int) -> Column:
    """A uniform draw in (0, 1), determined by `key` and `seed`."""
    return (F.pmod(F.hash(key, F.lit(seed)), F.lit(_INT32_MAX)) + 1) / (_INT32_MAX + 1.0)


def _gauss(key: Column, seed_a: int, seed_b: int) -> Column:
    """A standard normal draw, Box-Muller over two uniforms."""
    u1 = _uniform(key, seed_a)
    u2 = _uniform(key, seed_b)
    return F.sqrt(-2.0 * F.log(u1)) * F.cos(2.0 * math.pi * u2)


def _index(key: Column, seed: int, n: int) -> Column:
    """An integer in [0, n)."""
    return F.pmod(F.hash(key, F.lit(seed)), F.lit(n))


def _pick(index: Column, values: list) -> Column:
    """`values[index]`, as a lookup into an array literal."""
    return F.element_at(F.array(*[F.lit(v) for v in values]), index + 1)


def _sensor_id(sensor: Column) -> Column:
    """A 7 character alphanumeric id, e.g. 'a323frt'.

    Base 36 over two hashes rather than one: Spark's hash is 32 bit and tops out
    at six base-36 digits.
    """
    head = F.conv(_index(sensor, _SEED_ID_HEAD, 36**4).cast("string"), 10, 36)
    tail = F.conv(_index(sensor, _SEED_ID_TAIL, 36**3).cast("string"), 10, 36)
    return F.lower(F.concat(F.lpad(head, 4, "0"), F.lpad(tail, 3, "0")))


def generate_sensor_data(
    num_rows: int,
    spark: SparkSession | None = None,
    *,
    num_sensors: int = 5_000,
    start_date: date = date(2025, 1, 1),
    num_days: int = 365,
    num_partitions: int | None = None,
) -> DataFrame:
    """Return `num_rows` rows of synthetic sensor readings.

    The frame is lazy and reproducible, so it is recomputed on every action
    instead of being held anywhere -- cheap, but not free. Reading it more than
    once, `.cache()` it or write it to parquet first.

    Args:
        num_rows: How many readings to produce.
        spark: Session to build on; the active or default one if omitted.
        num_sensors: Size of the sensor pool the readings are spread over.
        start_date: First day of the window readings are dated in.
        num_days: Length of that window.
        num_partitions: Range partitioning; defaults to the cluster's
            parallelism, which is what makes the generation itself parallel.
    """
    if num_rows < 0:
        raise ValueError(f"num_rows must not be negative, got {num_rows}")

    spark = spark or SparkSession.builder.getOrCreate()
    df = spark.range(num_rows, numPartitions=num_partitions)

    row = F.col("id")
    sensor = _index(row, _SEED_SENSOR, num_sensors)
    parameter = _index(row, _SEED_PARAM, len(PARAMETERS))
    deviation = _gauss(row, _SEED_VALUE_A, _SEED_VALUE_B)

    means = [mean for mean, _ in PARAMETERS.values()]
    deviations = [sigma for _, sigma in PARAMETERS.values()]
    value = _pick(parameter, means) + _pick(parameter, deviations) * deviation

    return df.select(
        _sensor_id(sensor).alias("Sensor_ID"),
        F.date_add(F.lit(start_date), _index(row, _SEED_DATE, num_days)).alias("Date"),
        _pick(_index(sensor, _SEED_LOCATION, len(LOCATIONS)), LOCATIONS).alias("Location"),
        _pick(parameter, list(PARAMETERS)).alias("Parameter"),
        F.round(value, 3).alias("Value"),
        F.when(
            (F.abs(deviation) > _OUTLIER_SIGMA) | (_uniform(row, _SEED_FAULT) < _FAULT_RATE),
            F.lit("Bad"),
        )
        .otherwise(F.lit("Good"))
        .alias("Status"),
    )


def _transform_window(sensors: DataFrame) -> DataFrame:
    """Put every reading in the context of the ones around it.

    Windows are partitioned by sensor and parameter, never left unpartitioned --
    an unpartitioned window collapses the whole frame into a single task.
    """
    by_sensor = Window.partitionBy("Sensor_ID", "Parameter")
    history = by_sensor.orderBy("Date")
    so_far = history.rowsBetween(Window.unboundedPreceding, Window.currentRow)
    whole = history.rowsBetween(Window.unboundedPreceding, Window.unboundedFollowing)
    # A range frame counts days, not rows, so gaps in a sensor's history do not
    # stretch the week backwards. Its offsets have to match the type the window
    # is ordered by, which is why this one orders by the day number.
    last_week = by_sensor.orderBy(F.datediff("Date", F.lit(_EPOCH))).rangeBetween(
        -6, Window.currentRow
    )

    previous = F.lag("Value").over(history)
    mean = F.avg("Value").over(whole)
    sigma = F.stddev("Value").over(whole)

    return sensors.select(
        "*",
        F.row_number().over(history).alias("Reading_No"),
        previous.alias("Prev_Value"),
        F.round(F.col("Value") - previous, 3).alias("Delta"),
        F.round(F.avg("Value").over(last_week), 3).alias("Rolling_Avg_7d"),
        F.sum((F.col("Status") == "Bad").cast("int")).over(so_far).alias("Bad_So_Far"),
        # Against the sensor's own history rather than the parameter's nominal
        # spread: a sensor that reads consistently high is not an outlier.
        F.round((F.col("Value") - mean) / F.nullif(sigma, F.lit(0.0)), 3).alias("Z_Score"),
    )


def _transform_aggregate(sensors: DataFrame) -> DataFrame:
    """Collapse the readings into one row per location and parameter."""
    is_bad = (F.col("Status") == "Bad").cast("double")

    return sensors.groupBy("Location", "Parameter").agg(
        F.count("*").alias("Readings"),
        # Exact distincts need a second shuffle; the sketch is within ~2% and
        # rides along with the aggregation already happening.
        F.approx_count_distinct("Sensor_ID").alias("Sensors"),
        F.round(F.avg("Value"), 3).alias("Avg_Value"),
        F.round(F.stddev("Value"), 3).alias("Stddev_Value"),
        F.round(F.percentile_approx("Value", 0.5), 3).alias("Median_Value"),
        F.round(F.percentile_approx("Value", 0.95), 3).alias("P95_Value"),
        F.round(F.min("Value"), 3).alias("Min_Value"),
        F.round(F.max("Value"), 3).alias("Max_Value"),
        F.round(100 * F.avg(is_bad), 3).alias("Bad_Pct"),
        F.min("Date").alias("First_Reading"),
        F.max("Date").alias("Last_Reading"),
    )


def _transform_pivot(sensors: DataFrame) -> DataFrame:
    """One row per sensor per day, one column per parameter."""
    return (
        sensors.groupBy("Sensor_ID", "Date")
        # Spelling the values out matters: given no list, Spark runs a whole
        # extra distinct job over the frame just to learn the column names.
        .pivot("Parameter", list(PARAMETERS))
        .agg(F.round(F.avg("Value"), 3))
    )


def _transform_unpivot(wide: DataFrame) -> DataFrame:
    """Melt the pivoted frame back into one row per reading."""
    return wide.unpivot(
        ids=["Sensor_ID", "Date"],
        values=list(PARAMETERS),
        variableColumnName="Parameter",
        valueColumnName="Value",
    ).where(F.col("Value").isNotNull())


def _transform_manipulate_date(sensors: DataFrame) -> DataFrame:
    """Explode the date into the parts a report or a dashboard groups by."""
    day = F.col("Date")

    return sensors.select(
        "Sensor_ID",
        day,
        # The format the brief asks for, kept beside the real date rather than
        # instead of it -- a string does not filter or sort like a date.
        F.date_format(day, "yyyy.MM.dd").alias("Date_Label"),
        F.year(day).alias("Year"),
        F.quarter(day).alias("Quarter"),
        F.month(day).alias("Month"),
        F.weekofyear(day).alias("Week"),
        F.dayofyear(day).alias("Day_Of_Year"),
        F.date_format(day, "EEEE").alias("Weekday"),
        F.dayofweek(day).isin(1, 7).alias("Is_Weekend"),
        F.trunc(day, "month").alias("Month_Start"),
        F.last_day(day).alias("Month_End"),
        F.datediff(day, F.trunc(day, "year")).alias("Days_Into_Year"),
        "Parameter",
        "Value",
        "Status",
    )


def _write(name: str, frame: DataFrame, path: str, *, single_file: bool) -> DataFrame:
    """Write `frame` to parquet and hand back what landed there."""
    log.info("%-13s columns: %s", name, ", ".join(frame.columns))

    start = time.perf_counter()
    (frame.coalesce(1) if single_file else frame).write.mode("overwrite").parquet(path)
    elapsed = time.perf_counter() - start

    # Counting the parquet reads row counts out of the file footers instead of
    # running the transformation a second time.
    written = frame.sparkSession.read.parquet(path)
    log.info("%-13s %9s rows in %5.1fs -> %s", name, f"{written.count():,}", elapsed, path)
    return written


def do_transformations(sensors: DataFrame, output_dir: str = OUTPUT_DIR) -> dict[str, str]:
    """Run every transformation once, log it, and save each result as parquet.

    A failing step is logged and stepped over rather than taking the rest of the
    run down with it, so one pass tells you about every transformation instead
    of only the first broken one.

    Args:
        sensors: The readings to transform, as returned by `generate_sensor_data`.
        output_dir: Directory the parquet outputs are written under. Any path
            Spark can write to -- local, HDFS, S3.

    Returns:
        The paths written, keyed by transformation name.
    """
    output_dir = output_dir.rstrip("/")
    written: dict[str, str] = {}

    def attempt(name: str, build, *, single_file: bool = False) -> DataFrame | None:
        path = f"{output_dir}/{name}"
        try:
            result = _write(name, build(), path, single_file=single_file)
        except Exception:  # one broken transformation, not a broken run
            log.exception("%-13s failed", name)
            return None
        written[name] = path
        return result

    # Four of the five steps read the source, and a generated frame is rebuilt
    # from scratch on every action, so pay for it once here.
    sensors = sensors.persist(StorageLevel.MEMORY_AND_DISK)
    log.info("%-13s %9s rows to transform", "source", f"{sensors.count():,}")

    try:
        attempt("window", lambda: _transform_window(sensors))
        attempt("aggregate", lambda: _transform_aggregate(sensors), single_file=True)
        wide = attempt("pivot", lambda: _transform_pivot(sensors))
        # Unpivot the parquet just written, not the pivot's plan: the wide frame
        # is on disk already, and re-deriving it would repeat the shuffle.
        if wide is not None:
            attempt("unpivot", lambda: _transform_unpivot(wide))
        else:
            log.warning("%-13s skipped, the pivot it reads never landed", "unpivot")
        attempt("date_parts", lambda: _transform_manipulate_date(sensors))
    finally:
        sensors.unpersist()

    log.info("%d transformations written under %s/", len(written), output_dir)
    return written


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(message)s",
        datefmt="%H:%M:%S",
    )

    spark = (
        SparkSession.builder.appName("sensor-data")
        # 200 is the default and far too many for a million rows: most of the
        # shuffle tasks would be empty and the writes would litter tiny files.
        .config("spark.sql.shuffle.partitions", 16)
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    sensors = generate_sensor_data(NUM_ROWS, spark)
    sensors.show(5, truncate=False)
    do_transformations(sensors)

    spark.stop()
