# The UI layer.
#
# Stock Superset plus a Postgres driver, this stack's config, and the dashboard
# itself. Config is baked in rather than bind-mounted, so the image needs
# nothing from the host and comes up with the charts already in place.
FROM apache/superset:6.1.0

USER root

# The official image ships with no database driver at all, so out of the box it
# can reach neither its own metadata database nor the analytics database.
RUN uv pip install --no-cache psycopg2-binary

COPY superset_config.py /app/pythonpath/superset_config.py
# The dashboard export, imported by the entrypoint on every start. In the image
# rather than mounted, so `docker run` provisions itself the same as compose.
COPY interesting_metrics.zip /app/dashboards/interesting_metrics.zip
COPY --chmod=755 entrypoint.sh /app/entrypoint.sh

USER superset

EXPOSE 8088
ENTRYPOINT ["/app/entrypoint.sh"]
