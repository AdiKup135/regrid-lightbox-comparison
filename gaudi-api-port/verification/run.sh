#!/usr/bin/env bash
# Differential check: run the reference TypeScript engine and this Python port
# over identical fixtures and diff every field of every edge.
#
# Requires: node, python3 with shapely, and the site repo's esbuild.
# Not part of the gaudi-api drop-in — delete this directory on integration.
set -euo pipefail
cd "$(dirname "$0")"

TS_SRC="${TS_SRC:-/Users/adi/Documents/formX/site/edge-labeling/edge-labeling.ts}"
ESBUILD="${ESBUILD:-/Users/adi/Documents/formX/site/node_modules/.bin/esbuild}"

"$ESBUILD" "$TS_SRC" --bundle --format=esm --outfile=engine.mjs --log-level=warning
python3 gen_cases.py
node run_ts.mjs
python3 run_py.py
python3 compare.py
