# Postgres that knows the sensor schema, and carries the integrity checks so
# they can be run without a copy of the repo.
FROM postgres:17-alpine

COPY init/ /docker-entrypoint-initdb.d/
COPY checks.sql /checks.sql
