#!/bin/sh
# Container entrypoint for the API image.
# docker compose runs GigSim as its own service (START_GIGSIM=0).
# Single-container hosts (Render, Railway, HF Spaces) set START_GIGSIM=1 so GigSim runs here too.
set -e

if [ "${START_GIGSIM:-0}" = "1" ]; then
  uvicorn gigsim.app:app --host 127.0.0.1 --port 8001 &
  export GIGSIM_URL="http://127.0.0.1:8001"
  # wait until GigSim answers before the API opens its MCP sessions
  python -c "
import time, urllib.request
for _ in range(60):
    try:
        urllib.request.urlopen('http://127.0.0.1:8001/docs', timeout=1); break
    except Exception:
        time.sleep(0.5)
"
fi

exec python -m apps.api.main
