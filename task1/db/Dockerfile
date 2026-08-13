# The database layer.
#
# Stock Postgres plus this stack's bootstrap. The init script is baked into the
# image rather than bind-mounted, so the image is self-contained: `docker run`
# it anywhere with the right environment and you get the same two databases.
FROM postgres:17-alpine

COPY init/ /docker-entrypoint-initdb.d/
