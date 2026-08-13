"""Settings, read from the environment.

The variable names are libpq's own, so the same environment that would let
`psql` connect lets the API connect, and compose passes them once.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    pghost: str = "db"
    pgport: int = 5432
    pgdatabase: str = "sensors"
    pguser: str = "sensors"
    pgpassword: str = "sensors"

    # Small on purpose: the queries are short and the database is shared with
    # whatever else task2 is doing.
    pool_min_size: int = Field(1, ge=0)
    pool_max_size: int = Field(8, ge=1)

    # How long a request waits for a free connection before giving up with a
    # 503 rather than hanging on to the client.
    pool_timeout: float = Field(5.0, gt=0)

    @property
    def conninfo(self) -> str:
        return (
            f"host={self.pghost} port={self.pgport} dbname={self.pgdatabase} "
            f"user={self.pguser} password={self.pgpassword} "
            "application_name=task3-api"
        )


settings = Settings()
