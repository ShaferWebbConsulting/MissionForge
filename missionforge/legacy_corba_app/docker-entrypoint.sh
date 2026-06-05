#!/usr/bin/env sh
# docker-entrypoint.sh
# Starts the legacy CORBA telemetry server and pipes its stdout through
# the telemetry_client bridge which forwards JSON to the MissionForge adapter.
set -e

echo "[ENTRYPOINT] Starting legacy CORBA telemetry server (mock mode)"
echo "[ENTRYPOINT] Adapter: ${ADAPTER_HOST:-missionforge-adapter}:${ADAPTER_PORT:-8000}"

# Pipe server → client (bridge)
exec /app/telemetry_server 2>&1 | /app/telemetry_client
