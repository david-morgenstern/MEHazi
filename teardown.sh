#!/usr/bin/env bash
#
# Stop every stack and delete everything it created.
#
#   ./teardown.sh            stop the containers, drop the volumes
#   ./teardown.sh --images   the above, and delete the built images too
#
# Dropping the volumes discards the fetched market data, the generated sensor
# rows, both databases and Superset's dashboards. All of it is reproducible:
# ./build-all.sh puts it back from nothing.
set -euo pipefail

cd "$(dirname "$0")"

IMAGES=""
case "${1:-}" in
    --images) IMAGES="--rmi local" ;;
    "")       ;;
    *)        echo "usage: $0 [--images]" >&2; exit 2 ;;
esac

# Reverse dependency order: task3 reads task2's network, so it goes first.
for task in task3 task2 task1; do
    echo "==> $task"
    # --remove-orphans also clears the one-shot run containers compose leaves
    # behind from `docker compose run`.
    (cd "$task" && docker compose down -v --remove-orphans $IMAGES) 2>&1 | sed 's/^/    /'
done

echo
echo "remaining mehazi volumes:   $(docker volume ls -q | grep -c -i mehazi || true)"
echo "remaining mehazi containers: $(docker ps -aq --filter name=mehazi | wc -l)"
