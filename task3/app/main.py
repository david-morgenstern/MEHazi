"""The application: a pool, five endpoints, and the built front end.

Errors all leave through the handlers below, so every failure -- a bad query
parameter, an unknown sensor, a database that is not there, a bug -- reaches the
browser as the same small JSON object with a sentence in it. The front end can
then show what went wrong without knowing which of those it was.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import create_pool
from .models import ErrorResponse
from .routes import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(name)s  %(message)s")
log = logging.getLogger("api")

# Where the Dockerfile puts the compiled front end.
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Hold one pool for the process, not one connection per request."""
    app.state.pool = create_pool(settings)
    # Not awaiting the first connection: if task2's database is still starting,
    # the API should come up and say 503 rather than fail to start at all.
    await app.state.pool.open(wait=False)
    log.info("pool open against %s:%s/%s", settings.pghost, settings.pgport, settings.pgdatabase)
    try:
        yield
    finally:
        await app.state.pool.close()


app = FastAPI(
    title="MEHazi sensor API",
    version="1.0.0",
    summary="Aggregated views of the sensor data task2 generated, processed and loaded.",
    lifespan=lifespan,
    # Every endpoint can fail this way, so it belongs in the schema once.
    responses={500: {"model": ErrorResponse, "description": "Unhandled server error"}},
)


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
    """422s in the same shape as every other error, and readable.

    FastAPI's default is a list of pydantic error dicts, which is precise and
    unpleasant to display. This keeps the location of the problem but says it
    in one line.
    """
    problems = "; ".join(
        f"{'.'.join(str(part) for part in error['loc'][1:]) or 'request'}: {error['msg']}"
        for error in exc.errors()
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": problems or "The request could not be understood."},
    )


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
    # headers carried through: 405 and 401 are only useful with the Allow and
    # WWW-Authenticate they come with.
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers,
    )


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    """A bug. Logged in full, reported without the internals."""
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "The API hit an unexpected error. Check its logs."},
    )


app.include_router(router)

# Last, so it claims only the paths the API did not: /api/* and /docs stay put,
# everything else is the front end. html=True serves index.html at /.
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="web")
else:  # running the API alone, without the front end built
    log.warning("no front end at %s; serving the API only", STATIC_DIR)
