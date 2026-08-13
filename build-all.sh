#!/usr/bin/env bash
#
# Build and start all three stacks, in order, and wait until each one has
# actually done its job rather than merely started.
#
#   ./build-all.sh              build (using the layer cache) and start
#   ./build-all.sh --no-cache   rebuild every image from scratch first
#
# Safe to run on a machine that has never seen this project: the .env files are
# committed with working defaults, and are recreated from the examples if they
# are missing. Every stage is idempotent, so running it over a stack that is
# already up is a no-op that re-verifies everything.
set -euo pipefail

cd "$(dirname "$0")"

BUILD_ARGS=""
case "${1:-}" in
    --no-cache) BUILD_ARGS="--no-cache" ;;
    "")         ;;
    *)          echo "usage: $0 [--no-cache]" >&2; exit 2 ;;
esac

# --- helpers ---------------------------------------------------------------

step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
info() { printf '    %s\n' "$*"; }
die()  { printf '\n\033[31mFAILED: %s\033[0m\n' "$*" >&2; exit 1; }

# The container id for a service, so nothing here depends on a container name.
cid() { (cd "$1" && docker compose ps -aq "$2"); }

# Compose in a task directory, with its chatter indented under the step it
# belongs to. `pipefail` is what keeps a failed build a failed script.
compose() { local task=$1; shift; (cd "$task" && docker compose "$@") 2>&1 | sed 's/^/    | /'; }

# Wait for a service's healthcheck to pass.
wait_healthy() {
    local task=$1 service=$2 limit=${3:-300} waited=0 id status
    while [ "$waited" -lt "$limit" ]; do
        id=$(cid "$task" "$service")
        if [ -n "$id" ]; then
            status=$(docker inspect -f '{{.State.Health.Status}}' "$id" 2>/dev/null || echo starting)
            [ "$status" = healthy ] && { info "$service: healthy after ${waited}s"; return 0; }
        fi
        sleep 5
        waited=$((waited + 5))
    done
    die "$task/$service never became healthy (${limit}s)"
}

# Wait for a one-shot service to finish, and insist it finished cleanly.
wait_exit() {
    local task=$1 service=$2 limit=${3:-600} waited=0 id state code
    while [ "$waited" -lt "$limit" ]; do
        id=$(cid "$task" "$service")
        if [ -n "$id" ]; then
            state=$(docker inspect -f '{{.State.Status}}' "$id")
            if [ "$state" = exited ]; then
                code=$(docker inspect -f '{{.State.ExitCode}}' "$id")
                if [ "$code" != 0 ]; then
                    # Print the log here rather than name it. Starting the stack
                    # again replaces this container and takes its log with it,
                    # so "see: docker compose logs" is advice that expires the
                    # moment you act on it.
                    printf '\n\033[31m--- last 30 lines of %s/%s ---\033[0m\n' "$task" "$service" >&2
                    (cd "$task" && docker compose logs --tail 30 --no-log-prefix "$service") >&2
                    printf '\033[31m--- end of log ---\033[0m\n' >&2
                    die "$task/$service exited $code"
                fi
                info "$service: completed in ${waited}s"
                return 0
            fi
        fi
        sleep 5
        waited=$((waited + 5))
    done
    die "$task/$service never finished (${limit}s)"
}

# --- configuration ---------------------------------------------------------

step "configuration"

if [ ! -f task1/.env ]; then
    cp task1/.env.example task1/.env
    # Superset refuses to start on the default key, so give it a real one.
    key=$(openssl rand -base64 42 2>/dev/null || head -c 32 /dev/urandom | base64)
    # -i with an explicit suffix, then remove it: the one spelling that works on
    # both GNU and BSD sed.
    sed -i.bak "s|^SUPERSET_SECRET_KEY=.*|SUPERSET_SECRET_KEY=${key}|" task1/.env && rm -f task1/.env.bak
    info "task1/.env created from the example, with a generated secret key"
else
    info "task1/.env exists, left alone"
fi

if [ ! -f task3/.env ]; then
    cp task3/.env.example task3/.env
    info "task3/.env created from the example"
else
    info "task3/.env exists, left alone"
fi

# --- task1 -----------------------------------------------------------------

step "task1 — fetch, clean, load, and the dashboard"

compose task1 build $BUILD_ARGS
compose task1 up -d
# The pipeline is a batch job: compose starts it and moves on, so its success
# is something to wait for rather than assume.
wait_exit    task1 backend 900
wait_healthy task1 superset 600
info "$( (cd task1 && docker compose logs backend 2>/dev/null) | grep -oE 'load: .*' | tail -1)"

# --- task2 -----------------------------------------------------------------

step "task2 — generate, transform, load, verify"

compose task2 build $BUILD_ARGS
compose task2 up -d
wait_exit task2 pipeline 900
wait_exit task2 loader   900
wait_exit task2 checks   600

passes=$( (cd task2 && docker compose logs checks 2>/dev/null) | grep -c 'PASS' || true)
[ "$passes" -eq 6 ] || die "task2: expected 6 PASS verdicts, got $passes — cd task2 && docker compose logs checks"
info "integrity checks: $passes/6 PASS"

# --- task3 -----------------------------------------------------------------

step "task3 — API and web page"

compose task3 build $BUILD_ARGS
compose task3 up -d
wait_healthy task3 api 300
info "$(curl -s localhost:8000/api/health)"

# --- done ------------------------------------------------------------------

port=$(grep -E '^SUPERSET_HOST_PORT=' task1/.env | cut -d= -f2)
user=$(grep -E '^SUPERSET_ADMIN_USERNAME=' task1/.env | cut -d= -f2)
pass=$(grep -E '^SUPERSET_ADMIN_PASSWORD=' task1/.env | cut -d= -f2)

printf '\n\033[1;32mall three stacks are up\033[0m\n\n'
printf '    task1  dashboard   http://localhost:%s   (%s / %s)\n' "$port" "$user" "$pass"
printf '    task2  database    localhost:5433        (psql -U sensors -d sensors)\n'
printf '    task3  web page    http://localhost:8000\n'
printf '    task3  API docs    http://localhost:8000/docs\n\n'
