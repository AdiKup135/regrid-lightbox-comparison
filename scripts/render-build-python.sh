#!/usr/bin/env bash
# Render build step for the Python half of the site (run after npm install/build).
#
# Installs gaudi-api-port/requirements.txt into <repo>/.pydeps with `pip --target`.
# Why not a plain `pip install` or a venv:
#   - Render carries only the project directory from the build to the running
#     instance; anything pip puts in system or user site-packages is gone at runtime.
#   - Render's native runtimes are Debian 12, whose system pip refuses global
#     installs (PEP 668 "externally-managed-environment") and whose image has
#     no python3-venv.
# scripts/render-start.sh puts .pydeps on PYTHONPATH for both Python consumers
# (the Flask opendata provider and the engine subprocess spawned by
# zoneomics-backend) and runs them with the interpreter recorded here, so the
# compiled shapely wheel always matches the Python that loads it.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON_BIN:-python3}"
DEPS="$ROOT/.pydeps"

echo "render-build-python: using $("$PY" -c 'import sys; print(sys.executable, sys.version.split()[0])')"
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else "gaudi-api-port needs Python >= 3.10")'

rm -rf "$DEPS"
"$PY" -m pip install --no-cache-dir --disable-pip-version-check --target "$DEPS" \
  -r "$ROOT/gaudi-api-port/requirements.txt"

"$PY" -c 'import sys; print(sys.executable)' > "$DEPS/.python-bin"

# Fail the build (not the first request) if the engine cannot import.
cd "$ROOT/gaudi-api-port"
PYTHONPATH="$DEPS" "$PY" -c '
import shapely, flask, requests  # noqa: F401
import app_poc, services.compute.parcel_edges.cli
print("render-build-python: OK (shapely %s)" % shapely.__version__)
'
