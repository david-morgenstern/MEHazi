# The backend layer: fetch, clean, load. Runs to completion and exits.
#
# Two stages so the runtime image carries the installed packages but none of
# the build tooling or wheel caches.
FROM python:3.13-slim AS build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_ROOT_USER_ACTION=ignore

COPY requirements.txt .
RUN python -m venv /venv && /venv/bin/pip install -r requirements.txt


FROM python:3.13-slim

ENV PATH=/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/data

COPY --from=build /venv /venv

RUN useradd --create-home --uid 1000 pipeline \
 && install -d -o pipeline -g pipeline /data

WORKDIR /app
COPY pipeline/ pipeline/

USER pipeline
VOLUME /data

ENTRYPOINT ["python", "-m", "pipeline"]
