"""The API's contract, as pydantic models.

They do three jobs at once. They validate what comes in, so a malformed sensor
id is a 422 that never reaches the database. They shape what goes out, so a
column added in task2 cannot silently change a response. And they are what the
schema at /docs is generated from -- the documentation cannot drift from the
code because it is the code.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Sensor ids are seven lowercase base-36 characters, as task2 generates them.
# Spelling that out here is what makes a bad id a 422 instead of an empty page.
SENSOR_ID_PATTERN = r"^[0-9a-z]{7}$"


class Parameter(str, Enum):
    """The quantities a sensor reports, mirroring task2's PARAMETERS."""

    offset = "Offset"
    noise = "Noise"
    temperature = "Temperature"
    pressure = "Pressure"
    humidity = "Humidity"
    voltage = "Voltage"


class Status(str, Enum):
    good = "Good"
    bad = "Bad"


class SortField(str, Enum):
    """Sortable columns.

    This enum is also the SQL whitelist. A column name cannot be parameterised
    the way a value can, so the only safe way to accept one from a client is to
    check it against a fixed set first -- which is exactly what pydantic does
    with this type before the request reaches the query.
    """

    reading_date = "reading_date"
    parameter = "parameter"
    value = "value"
    status = "status"
    reading_no = "reading_no"
    delta = "delta"
    rolling_avg_7d = "rolling_avg_7d"
    z_score = "z_score"


class SortOrder(str, Enum):
    asc = "asc"
    desc = "desc"


class SensorQuery(BaseModel):
    """Query parameters for the sensor list."""

    # forbid, so a misspelled parameter is an error rather than silence: ?serch=
    # should not quietly return everything.
    model_config = ConfigDict(extra="forbid")

    q: str | None = Field(
        None,
        max_length=7,
        pattern=r"^[0-9a-z]*$",
        description="Return only ids containing this fragment.",
        examples=["a3"],
    )
    limit: int = Field(1000, ge=1, le=5000, description="Cap on ids returned.")


class ReadingQuery(BaseModel):
    """Query parameters for one sensor's readings: filter, sort, paginate."""

    model_config = ConfigDict(extra="forbid")

    parameter: Parameter | None = Field(None, description="Keep only this parameter.")
    status: Status | None = Field(None, description="Keep only Good or only Bad readings.")
    sort: SortField = Field(SortField.reading_date, description="Column to order by.")
    order: SortOrder = Field(SortOrder.asc, description="Ascending or descending.")
    limit: int = Field(50, ge=1, le=500, description="Rows per page.")
    offset: int = Field(0, ge=0, description="Rows to skip.")


class SensorList(BaseModel):
    """The sensor ids, and how many matched before the cap was applied."""

    items: list[str]
    total: int = Field(description="Ids matching the filter, ignoring `limit`.")
    limit: int
    truncated: bool = Field(description="True when `total` exceeded `limit`.")


class ParameterStats(BaseModel):
    """One sensor's readings of one parameter, summarised."""

    parameter: Parameter
    readings: int
    avg_value: float
    min_value: float
    max_value: float
    # Null for a parameter with a single reading: no spread to speak of.
    stddev_value: float | None = None
    bad_readings: int
    bad_pct: float
    first_reading: date
    last_reading: date


class SensorSummary(BaseModel):
    """Everything worth knowing about one sensor at a glance."""

    sensor_id: str = Field(pattern=SENSOR_ID_PATTERN, examples=["a323frt"])
    location: str
    readings: int
    first_reading: date
    last_reading: date
    bad_readings: int
    bad_pct: float
    parameters: list[ParameterStats]


class Reading(BaseModel):
    """One processed reading: the row as task2's window transformation left it."""

    sensor_id: str
    reading_date: date
    location: str
    parameter: Parameter
    value: float
    status: Status
    reading_no: int
    prev_value: float | None = None
    delta: float | None = None
    rolling_avg_7d: float
    bad_so_far: int
    z_score: float | None = None


class ReadingPage(BaseModel):
    """A page of readings, and enough context to ask for the next one."""

    items: list[Reading]
    total: int = Field(description="Rows matching the filter, ignoring paging.")
    limit: int
    offset: int
    sort: SortField
    order: SortOrder


class LocationStats(BaseModel):
    """A row of task2's aggregate table: one location, one parameter."""

    location: str
    parameter: Parameter
    readings: int
    sensors: int
    avg_value: float | None = None
    stddev_value: float | None = None
    median_value: float | None = None
    p95_value: float | None = None
    min_value: float | None = None
    max_value: float | None = None
    bad_pct: float | None = None
    first_reading: date | None = None
    last_reading: date | None = None


class Health(BaseModel):
    """Whether the API can see the data, and how much of it there is."""

    status: Literal["ok", "empty"] = Field(
        description="'empty' when the tables are reachable but task2 has not filled them.",
        examples=["ok"],
    )
    readings: int
    summaries: int


class ErrorResponse(BaseModel):
    """The body of every error this API returns, whatever went wrong."""

    detail: str = Field(examples=["Sensor 'zzzzzzz' has no readings."])
