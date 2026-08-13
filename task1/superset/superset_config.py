"""Superset configuration, picked up from PYTHONPATH=/app/pythonpath.

Only what must differ from the defaults: where Superset keeps its own state,
and the key it signs sessions with.
"""

import os

SECRET_KEY = os.environ["SUPERSET_SECRET_KEY"]

# Superset's own dashboards, charts and users. Without this it falls back to a
# sqlite file inside the container, which dies with the container.
SQLALCHEMY_DATABASE_URI = (
    f"postgresql+psycopg2://{os.environ['SUPERSET_DB_USER']}"
    f":{os.environ['SUPERSET_DB_PASSWORD']}"
    f"@{os.environ['PGHOST']}:5432/{os.environ['SUPERSET_DB']}"
)
