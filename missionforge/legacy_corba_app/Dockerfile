# Legacy CORBA Telemetry Server — Dockerfile
#
# Builds the C++ telemetry server in mock mode (no TAO ORB dependency).
# The binary streams JSON telemetry to stdout every 1 second.
# The Python bridge reads that stdout and forwards to the adapter.
#
# To build with real TAO ORB: install libtao-dev and set -DUSE_TAO_ORB=ON.

FROM debian:bookworm-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy source files
COPY CMakeLists.txt .
COPY idl/ ./idl/
COPY src/ ./src/

# Build in mock mode (no TAO ORB required)
RUN cmake -B build -DUSE_TAO_ORB=OFF -DCMAKE_BUILD_TYPE=Release && \
    cmake --build build --parallel $(nproc)

# -------------------------------------------------------------------------
# Runtime image — minimal
# -------------------------------------------------------------------------
FROM debian:bookworm-slim

WORKDIR /app

COPY --from=builder /build/build/telemetry_server ./telemetry_server
COPY --from=builder /build/build/telemetry_client ./telemetry_client

# Startup script: run server and pipe stdout through the bridge
# (bridge forwards JSON lines to missionforge-adapter via HTTP)
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

ENTRYPOINT ["/app/docker-entrypoint.sh"]
