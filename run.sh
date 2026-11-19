#!/usr/bin/env bash
# Start the API. Extra arguments go to uvicorn, e.g. ./run.sh --reload
set -euo pipefail
cd "$(dirname "$0")"

args=("$@")
# With --reload, watch only the app code (not .venv), so installing packages doesn't restart the server.
for a in "$@"; do
    if [[ "$a" == "--reload" ]]; then args+=(--reload-dir app); break; fi
done

exec uv run uvicorn app.main:app --host "${HOST:-127.0.0.1}" --port "${PORT:-8000}" ${args[@]+"${args[@]}"}
