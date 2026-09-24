#!/usr/bin/env bash
# Render start command: runs the Express server and, beside it in the same
# instance, the Flask opendata provider (gaudi-api-port/app_poc.py).
#
#   Express  :$PORT (Render assigns it)   public; proxies /api/opendata/* to OPENDATA_URL
#   Flask    127.0.0.1:3004               private to the instance
#
# OPENDATA_URL is the seam. When it points at 127.0.0.1/localhost (the default)
# this script starts Flask on that port. Point it anywhere else (a separate
# Render service) and Flask is not started here.
#
# If either process exits, the script stops the other and exits non-zero so
# Render restarts the instance instead of serving a half-working site.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

DEPS="$ROOT/.pydeps"
PY="python3"
if [ -f "$DEPS/.python-bin" ] && [ -x "$(cat "$DEPS/.python-bin")" ]; then
  PY="$(cat "$DEPS/.python-bin")"
elif [ -d "$DEPS" ]; then
  echo "render-start: WARNING interpreter recorded at build time is missing; falling back to python3" >&2
fi
export PYTHON_BIN="$PY"                                   # read by zoneomics-backend's engine spawn
export PYTHONPATH="$DEPS${PYTHONPATH:+:$PYTHONPATH}"
export OPENDATA_URL="${OPENDATA_URL:-http://127.0.0.1:3004}"

FLASK_PID=""
case "$OPENDATA_URL" in
  http://127.0.0.1:*|http://localhost:*)
    OPENDATA_PORT="${OPENDATA_URL##*:}"
    OPENDATA_PORT="${OPENDATA_PORT%%/*}"
    echo "render-start: starting opendata provider on 127.0.0.1:$OPENDATA_PORT ($PY)"
    (cd gaudi-api-port && PORT="$OPENDATA_PORT" HOST=127.0.0.1 exec "$PY" app_poc.py) &
    FLASK_PID=$!
    ;;
  *)
    echo "render-start: OPENDATA_URL=$OPENDATA_URL is remote; not starting a local provider"
    ;;
esac

node server.js &
NODE_PID=$!

stop_all() {
  kill -TERM $NODE_PID $FLASK_PID 2>/dev/null
  wait 2>/dev/null
}
trap 'stop_all; exit 143' TERM INT

# Portable stand-in for `wait -n` (bash >= 4.3): poll both children.
while kill -0 "$NODE_PID" 2>/dev/null && { [ -z "$FLASK_PID" ] || kill -0 "$FLASK_PID" 2>/dev/null; }; do
  sleep 2 &
  wait $! 2>/dev/null
done

echo "render-start: a child process exited; stopping so Render restarts the instance" >&2
stop_all
exit 1
