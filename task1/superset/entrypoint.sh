#!/usr/bin/env bash
# Bring Superset up to a usable state, then hand over to the server.
#
# Every step is safe to repeat, which is what lets this run on every start
# instead of living in a separate one-shot container. It stops at a Superset
# you can log into with the dashboard already imported and connected.
set -euo pipefail

DASHBOARD=/app/dashboards/interesting_metrics.zip

python - <<'PY'
import os
import sys
import time

import psycopg2

for attempt in range(1, 31):
    try:
        psycopg2.connect(dbname=os.environ["SUPERSET_DB"])
        break
    except psycopg2.OperationalError:
        print(f"superset: waiting for {os.environ['PGHOST']} ({attempt}/30)", flush=True)
        time.sleep(2)
else:
    sys.exit(f"superset: {os.environ['PGHOST']} never accepted a connection")
PY

# Brings the metadata database to this version's schema; a no-op once current.
superset db upgrade

# Fails harmlessly on every start after the first, when the account exists.
superset fab create-admin \
    --username "${SUPERSET_ADMIN_USERNAME}" \
    --firstname Admin --lastname User \
    --email "${SUPERSET_ADMIN_EMAIL}" \
    --password "${SUPERSET_ADMIN_PASSWORD}" \
    || echo "superset: admin already exists, leaving it alone"

# Syncs roles and permissions.
superset init

# Import the dashboard, so a fresh `docker compose up` lands on working charts
# instead of an empty Superset and a manual upload.
#
# Superset strips the password out of an export: the connection inside the zip
# carries the literal placeholder XXXXXXXXXX. The UI's import dialog is what
# normally asks for the real one, and `superset import-dashboards` has no flag
# for it -- it just refuses the file with "Must provide a password for the
# database". So the password goes back into the copy being imported, read from
# the environment compose already passes in.
#
# Re-importing is harmless: objects are matched on uuid and updated in place,
# so a restart neither duplicates a chart nor discards an edit to one.
if [ -f "$DASHBOARD" ]; then
    IMPORTABLE=/tmp/dashboard-with-password.zip

    python - "$DASHBOARD" "$IMPORTABLE" <<'PY'
"""Copy the export, putting the real password back into its connection."""
import os
import sys
import zipfile

source, target = sys.argv[1], sys.argv[2]
password = os.environ["ANALYTICS_PASSWORD"].encode()

with zipfile.ZipFile(source) as original, zipfile.ZipFile(target, "w") as patched:
    for entry in original.infolist():
        content = original.read(entry.filename)
        # Only the database yaml holds a connection string to repair.
        if "/databases/" in entry.filename:
            content = content.replace(b"XXXXXXXXXX", password)
        patched.writestr(entry, content)
PY

    # set-database-uri afterwards is not redundant: the import above fixes a
    # first install, this repairs a Superset whose connection was already
    # created with the wrong password and which the uuid match would otherwise
    # skip right past.
    if superset import-dashboards -p "$IMPORTABLE" -u "${SUPERSET_ADMIN_USERNAME}"; then
        superset set-database-uri \
            -d analytics_db \
            -u "postgresql+psycopg2://${ANALYTICS_USER}:${ANALYTICS_PASSWORD}@db:5432/${ANALYTICS_DB}"
        echo "superset: dashboard imported and connected"
    else
        echo "superset: dashboard import failed, carrying on with an empty Superset"
    fi

    rm -f "$IMPORTABLE"
else
    echo "superset: no dashboard baked in, starting empty"
fi

exec /app/docker/entrypoints/run-server.sh
