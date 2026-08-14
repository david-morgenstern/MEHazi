"""The endpoints.

Five of them: a health probe, the sensor list, one sensor's summary, one
sensor's readings, and task2's location table. The SQL lives here beside the
route that runs it -- there is not enough of it to be worth hiding, and reading
the query next to the response model is how you check one against the other.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from psycopg import sql
from psycopg_pool import AsyncConnectionPool

from .db import fetch_all, fetch_one, get_pool
from .models import (
    ErrorResponse,
    Health,
    LocationStats,
    ParameterStats,
    Reading,
    ReadingPage,
    ReadingQuery,
    SENSOR_ID_PATTERN,
    SensorList,
    SensorQuery,
    SensorSummary,
)

router = APIRouter(prefix="/api")

Pool = Annotated[AsyncConnectionPool, Depends(get_pool)]
SensorId = Annotated[
    str,
    Path(
        pattern=SENSOR_ID_PATTERN,
        description="Seven lowercase base-36 characters, as task2 generates them.",
        examples=["a323frt"],
    ),
]

UNAVAILABLE = {503: {"model": ErrorResponse, "description": "The database cannot be reached"}}
NOT_FOUND = {404: {"model": ErrorResponse, "description": "No such sensor"}}


# Walking the primary key from one distinct sensor to the next, rather than
# reading a million rows to throw all but five thousand away. Postgres has no
# skip scan of its own, so the recursion is how you ask for one: 75ms against
# 300ms for SELECT DISTINCT, on an index the schema already has.
SENSOR_IDS = """
WITH RECURSIVE walk AS (
        (SELECT sensor_id FROM readings ORDER BY sensor_id LIMIT 1)
    UNION ALL
        SELECT (SELECT r.sensor_id
                FROM readings r
                WHERE r.sensor_id > w.sensor_id
                ORDER BY r.sensor_id
                LIMIT 1)
        FROM walk w
        WHERE w.sensor_id IS NOT NULL
),
ids AS (SELECT sensor_id FROM walk WHERE sensor_id IS NOT NULL)
SELECT sensor_id,
       -- The window runs before LIMIT, so this is how many matched, not how
       -- many are being returned.
       count(*) OVER () AS total
FROM ids
WHERE (%(fragment)s::text IS NULL OR sensor_id LIKE %(fragment)s)
ORDER BY sensor_id
LIMIT %(limit)s
"""

# No GROUP BY: an ungrouped aggregate returns exactly one row whether the
# sensor has a million readings or none, so "no such sensor" is readings = 0
# rather than an absent row. Grouping by location instead would return one row
# per location and quietly summarise only the first of them -- task2 guarantees
# a sensor reports from one place, but that is its invariant to keep, not a
# thing this query should depend on.
SENSOR_SUMMARY = """
SELECT min(location)                                             AS location,
       count(*)                                                  AS readings,
       min(reading_date)                                         AS first_reading,
       max(reading_date)                                         AS last_reading,
       count(*) FILTER (WHERE status = 'Bad')                    AS bad_readings,
       -- nullif, because the no-such-sensor row divides by zero otherwise.
       round(100.0 * count(*) FILTER (WHERE status = 'Bad') / nullif(count(*), 0), 3) AS bad_pct
FROM readings
WHERE sensor_id = %(sensor_id)s
"""

SENSOR_PARAMETERS = """
SELECT parameter,
       count(*)                                                  AS readings,
       round(avg(value)::numeric, 3)                             AS avg_value,
       round(min(value)::numeric, 3)                             AS min_value,
       round(max(value)::numeric, 3)                             AS max_value,
       round(stddev(value)::numeric, 3)                          AS stddev_value,
       count(*) FILTER (WHERE status = 'Bad')                    AS bad_readings,
       round(100.0 * count(*) FILTER (WHERE status = 'Bad') / count(*), 3) AS bad_pct,
       min(reading_date)                                         AS first_reading,
       max(reading_date)                                         AS last_reading
FROM readings
WHERE sensor_id = %(sensor_id)s
GROUP BY parameter
ORDER BY parameter
"""

# One text for every combination of filters: a null filter matches everything,
# so the planner sees the same query whichever boxes the client ticked.
READING_FILTER = """
FROM readings
WHERE sensor_id = %(sensor_id)s
  AND (%(parameter)s::text IS NULL OR parameter = %(parameter)s)
  AND (%(status)s::text IS NULL OR status = %(status)s)
"""


@router.get(
    "/health",
    response_model=Health,
    summary="Is the API able to see the data",
    responses=UNAVAILABLE,
)
async def health(pool: Pool) -> Health:
    row = await fetch_one(
        pool,
        "SELECT (SELECT count(*) FROM readings)       AS readings,"
        "       (SELECT count(*) FROM location_stats) AS summaries",
    )
    # task2's image creates the schema when its database first starts, so the
    # tables exist long before the pipeline fills them. Reachable but empty is
    # a real state, and saying "ok" to it would be a lie the front end repeats.
    return Health(status="ok" if row["readings"] else "empty", **row)


@router.get(
    "/sensors",
    response_model=SensorList,
    summary="Every sensor id, optionally filtered",
    responses=UNAVAILABLE,
)
async def list_sensors(pool: Pool, query: Annotated[SensorQuery, Query()]) -> SensorList:
    rows = await fetch_all(
        pool,
        SENSOR_IDS,
        {
            "fragment": f"%{query.q}%" if query.q else None,
            "limit": query.limit,
        },
    )
    # No rows means nothing matched, which is a total of zero rather than an
    # unknown one -- there is no paging here for it to be ambiguous with.
    total = rows[0]["total"] if rows else 0
    return SensorList(
        items=[row["sensor_id"] for row in rows],
        total=total,
        limit=query.limit,
        truncated=total > len(rows),
    )


@router.get(
    "/sensors/{sensor_id}",
    response_model=SensorSummary,
    summary="One sensor, summarised overall and per parameter",
    responses={**NOT_FOUND, **UNAVAILABLE},
)
async def sensor_summary(pool: Pool, sensor_id: SensorId) -> SensorSummary:
    overall = await fetch_one(pool, SENSOR_SUMMARY, {"sensor_id": sensor_id})
    if not overall["readings"]:
        # A well-formed id that nothing was ever recorded against. 404 rather
        # than an empty summary: the caller asked about something that is not
        # there, and should be able to tell that from a slow day.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sensor '{sensor_id}' has no readings.",
        )

    parameters = await fetch_all(pool, SENSOR_PARAMETERS, {"sensor_id": sensor_id})
    return SensorSummary(
        sensor_id=sensor_id,
        parameters=[ParameterStats(**row) for row in parameters],
        **overall,
    )


@router.get(
    "/sensors/{sensor_id}/readings",
    response_model=ReadingPage,
    summary="One sensor's processed readings, filtered, sorted and paged",
    responses={**NOT_FOUND, **UNAVAILABLE},
)
async def sensor_readings(
    pool: Pool,
    sensor_id: SensorId,
    query: Annotated[ReadingQuery, Query()],
) -> ReadingPage:
    params = {
        "sensor_id": sensor_id,
        "parameter": query.parameter.value if query.parameter else None,
        "status": query.status.value if query.status else None,
        "limit": query.limit,
        "offset": query.offset,
    }

    total_row = await fetch_one(pool, f"SELECT count(*) AS total {READING_FILTER}", params)
    total = total_row["total"]
    if total == 0:
        # Distinguish "this sensor has nothing to show" from "your filter
        # excluded everything", because only one of the two is a 404.
        exists = await fetch_one(
            pool,
            "SELECT 1 FROM readings WHERE sensor_id = %(sensor_id)s LIMIT 1",
            {"sensor_id": sensor_id},
        )
        if exists is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Sensor '{sensor_id}' has no readings.",
            )

    page = sql.SQL(
        """
        SELECT sensor_id, reading_date, location, parameter, value, status,
               reading_no, prev_value, delta, rolling_avg_7d, bad_so_far, z_score
        {filter}
        -- The sort column is an identifier, which cannot be bound as a value.
        -- It is safe to compose here only because SortField validated it
        -- against a fixed set of columns before we got this far.
        --
        -- (parameter, reading_no) is the tie-break, not reading_no alone:
        -- reading_no counts within a sensor's history of one parameter, so a
        -- sensor has six rows numbered 1 and ties on it. Together with the
        -- sensor_id already fixed by the filter, those two are the primary
        -- key, which makes this a total order -- without it, two rows sharing
        -- a sort value can swap between pages, showing one twice and hiding
        -- the other.
        ORDER BY {column} {direction}, parameter, reading_no
        LIMIT %(limit)s OFFSET %(offset)s
        """
    ).format(
        filter=sql.SQL(READING_FILTER),
        column=sql.Identifier(query.sort.value),
        direction=sql.SQL(query.order.value.upper()),
    )

    rows = await fetch_all(pool, page, params)
    return ReadingPage(
        items=[Reading(**row) for row in rows],
        total=total,
        limit=query.limit,
        offset=query.offset,
        sort=query.sort,
        order=query.order,
    )


@router.get(
    "/locations",
    response_model=list[LocationStats],
    summary="Task2's aggregate table, one row per location and parameter",
    responses=UNAVAILABLE,
)
async def locations(pool: Pool) -> list[LocationStats]:
    rows = await fetch_all(
        pool, "SELECT * FROM location_stats ORDER BY location, parameter"
    )
    return [LocationStats(**row) for row in rows]
