"""The connection pool, and the two helpers every endpoint queries through.

Everything the API does is a short read, so a pool of a few connections handles
far more traffic than a page of charts will ever produce. The point of routing
every query through here is the error translation: a database that is down or
still loading becomes a 503 with a sentence in it, never a stack trace.
"""

from __future__ import annotations

import logging
from typing import Any

import psycopg
from fastapi import HTTPException, Request, status
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool, PoolTimeout

from .config import Settings

log = logging.getLogger("api.db")

Row = dict[str, Any]


def create_pool(settings: Settings) -> AsyncConnectionPool:
    """A pool that is not connected yet.

    Opened without waiting, so the API starts even when Postgres does not
    answer: task2's stack may still be loading, and an API that refuses to boot
    for a minute is harder to diagnose than one that says 503 and why.
    """
    return AsyncConnectionPool(
        conninfo=settings.conninfo,
        min_size=settings.pool_min_size,
        max_size=settings.pool_max_size,
        timeout=settings.pool_timeout,
        kwargs={"row_factory": dict_row},
        open=False,
    )


def get_pool(request: Request) -> AsyncConnectionPool:
    """Dependency: the pool held on the app for the process' lifetime."""
    return request.app.state.pool


async def fetch_all(pool: AsyncConnectionPool, query: Any, params: Any = None) -> list[Row]:
    """Run a query, or turn the reason it could not run into a 503."""
    try:
        async with pool.connection() as conn, conn.cursor() as cursor:
            await cursor.execute(query, params)
            return await cursor.fetchall()
    except (psycopg.OperationalError, PoolTimeout) as exc:
        # Unreachable, still starting, out of connections: all the same to a
        # caller, and none of them the caller's fault.
        log.warning("database unavailable: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The sensor database is not reachable. Is task2's stack up and loaded?",
        ) from exc
    except psycopg.errors.UndefinedTable as exc:
        # The stack is up but task2 never ran, which is worth saying plainly.
        log.warning("missing table: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The database has no sensor tables yet. Run task2's pipeline first.",
        ) from exc


async def fetch_one(pool: AsyncConnectionPool, query: Any, params: Any = None) -> Row | None:
    """The first row, or None if the query matched nothing."""
    rows = await fetch_all(pool, query, params)
    return rows[0] if rows else None
