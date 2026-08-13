# Three stages: node compiles the front end, pip builds a venv, and the runtime
# image carries neither toolchain -- just the venv, the app, and the bundle.
#
# Node appears only here. Nobody needs it installed to build or run this.
FROM node:22-alpine AS web

WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build


FROM python:3.13-slim AS build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_ROOT_USER_ACTION=ignore

COPY requirements.txt .
RUN python -m venv /venv && /venv/bin/pip install -r requirements.txt


FROM python:3.13-slim

ENV PATH=/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY --from=build /venv /venv

RUN useradd --create-home --uid 1000 api

WORKDIR /srv
COPY app/ app/
# Where app.main expects to find the front end. Svelte compiled it to plain
# JavaScript, so serving it needs nothing but a static file handler.
COPY --from=web /web/dist static/

USER api
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
