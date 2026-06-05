# MissionForge

> **Computational Upcycling of Legacy Mission Computing Systems**

MissionForge demonstrates a semantic overlay approach for computational upcycling of legacy mission computing systems. The MVP connects to a representative legacy 32-bit CORBA-based telemetry application, extracts mission-system signals, translates them into modern event formats, and applies predictive maintenance/anomaly detection logic without modifying the legacy application.

---

## Why This Matters

Billions of dollars of mission-critical defence and aerospace infrastructure runs on legacy 32-bit systems built with CORBA/TAO ORB in the 1990s–2000s. These systems cannot be replaced quickly — they are certified, deployed, and trusted. Yet they lack modern observability, predictive maintenance, and AI-assisted decision support.

MissionForge solves this by:
- **Observing without touching** — connects externally to a legacy CORBA service
- **Translating semantics** — converts low-level telemetry into meaningful events
- **Adding intelligence** — rule-based and ML-based anomaly detection on top
- **No hardware changes** — runs alongside existing systems on commodity hardware
- **DARPA Low Resource Computing alignment** — demonstrates new capability without new hardware or software replacement

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        LEGACY MISSION COMPUTER                          │
│                                                                         │
│   ┌──────────────────────────────────────────────────────────────────┐  │
│   │  C++ TAO CORBA Telemetry Server  (NEVER MODIFIED)                │  │
│   │                                                                  │  │
│   │  • engine_temp  • vibration  • fuel_flow  • oil_pressure         │  │
│   │  • cpu_usage    • memory_usage  • sensor_status  • timestamp     │  │
│   │                                                                  │  │
│   │  IDL: MissionSystem::TelemetryService::getLatestTelemetry()      │  │
│   └──────────────────────┬───────────────────────────────────────────┘  │
└──────────────────────────┼──────────────────────────────────────────────┘
                           │  CORBA IOR  (TAO mode)
                           │  OR JSON stdout pipe  (mock mode)
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     CORBA BRIDGE  (telemetry_client.cpp)                │
│  Polls legacy CORBA service → serialises to JSON → HTTP POST            │
└──────────────────────────────────┬──────────────────────────────────────┘
                                   │  POST /internal/telemetry
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                   MissionForge Adapter  (FastAPI)                       │
│                                                                         │
│  ┌─────────────────┐  ┌──────────────────────┐  ┌───────────────────┐  │
│  │  TelemetryStore │  │  Semantic Overlay     │  │  REST API         │  │
│  │  (ring buffer)  │→ │  ├ rules.py           │  │  GET /telemetry   │  │
│  │                 │  │  │  Rule engine        │  │  GET /health      │  │
│  │  500 readings   │  │  ├ anomaly_detector.py│  │  GET /alerts      │  │
│  │  in memory      │  │  │  Isolation Forest   │  │  POST /demo/*     │  │
│  └─────────────────┘  │  └ health_score.py    │  └───────────────────┘  │
│                       │     0-100 score        │                         │
│                       └──────────────────────  │                         │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼  HTTP polling
┌─────────────────────────────────────────────────────────────────────────┐
│                      Dashboard  (nginx + HTML/JS)                       │
│                                                                         │
│  • Live telemetry gauges    • Health score gauge                        │
│  • Active alerts feed       • Telemetry history table                   │
│  • Inject Fault button      • Reset button                              │
│                                                                         │
│  http://localhost:8080                                                  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Repository Structure

```
missionforge/
├── README.md
├── docker-compose.yml
├── legacy_corba_app/
│   ├── idl/
│   │   └── Telemetry.idl          # CORBA IDL — legacy interface definition
│   ├── src/
│   │   ├── telemetry_server.cpp   # Legacy CORBA server (mock + TAO modes)
│   │   └── telemetry_client.cpp   # CORBA bridge → JSON → HTTP
│   ├── CMakeLists.txt             # Build with or without TAO ORB
│   ├── Dockerfile                 # Multi-stage C++ build
│   └── docker-entrypoint.sh
├── missionforge_adapter/
│   ├── app/
│   │   ├── main.py                # FastAPI routes
│   │   ├── corba_bridge.py        # TelemetryStore (in-memory)
│   │   └── schemas.py             # Pydantic models
│   ├── Dockerfile
│   └── requirements.txt
├── semantic_overlay/
│   ├── rules.py                   # Rule-based alert engine
│   ├── anomaly_detector.py        # Isolation Forest detector
│   └── health_score.py            # Health score 0-100
├── dashboard/
│   ├── index.html
│   ├── app.js
│   ├── style.css
│   └── Dockerfile                 # nginx static server
└── demo/
    ├── inject_fault.py            # CLI fault injector
    └── run_demo.sh                # End-to-end demo script
```

---

## Quick Start (Mock Demo Mode — No TAO ORB Required)

### Prerequisites

- Docker 24+ and Docker Compose v2
- (Optional) Python 3.10+ for the CLI demo tool

### Start the stack

```bash
cd missionforge
docker compose up --build
```

This builds and starts three containers:

| Container              | Port  | Description                          |
|------------------------|-------|--------------------------------------|
| `legacy-corba-server`  | —     | C++ telemetry server (mock CORBA)    |
| `missionforge-adapter` | 8000  | FastAPI semantic overlay             |
| `missionforge-dashboard` | 8080 | HTML dashboard (nginx)             |

### Open the dashboard

```
http://localhost:8080
```

### Test the API

```bash
# Latest telemetry snapshot from the legacy system
curl http://localhost:8000/telemetry/latest

# System health score (0-100)
curl http://localhost:8000/health

# Active predictive maintenance alerts
curl http://localhost:8000/alerts

# Interactive API docs
open http://localhost:8000/docs
```

---

## Demo: Injecting a Fault

Watch the semantic overlay detect a failure in real time:

### Via the dashboard

1. Open `http://localhost:8080`
2. Click **🔴 Inject Fault**
3. Watch the telemetry panels turn red as engine temp rises, vibration spikes, and oil pressure drops
4. Watch the Alerts section populate with `HIGH_TEMP`, `HIGH_VIBRATION`, `PREDICTIVE_FAILURE`, and `LOW_OIL_PRESSURE` alerts
5. Watch the health score drop from 100 toward 0
6. Click **🟢 Reset System** to restore normal operation

### Via the CLI demo script

```bash
# Run the full automated demo
chmod +x demo/run_demo.sh
./demo/run_demo.sh
```

### Via the Python injector

```bash
# Inject fault and watch alerts for 30 seconds
python3 demo/inject_fault.py --watch

# Reset
python3 demo/inject_fault.py --reset
```

### Via curl

```bash
# Inject fault
curl -X POST http://localhost:8000/demo/inject-fault

# Reset
curl -X POST http://localhost:8000/demo/reset
```

---

## Alert Rules

The semantic overlay (`semantic_overlay/rules.py`) implements five rules:

| Rule                | Condition                                            | Severity |
|---------------------|------------------------------------------------------|----------|
| `HIGH_TEMP`         | `engine_temp > 220°C`                               | HIGH     |
| `HIGH_VIBRATION`    | `vibration > 0.75g`                                 | HIGH     |
| `PREDICTIVE_FAILURE`| `engine_temp` rising 5 consecutive samples AND `vibration` also rising | CRITICAL |
| `LOW_OIL_PRESSURE`  | `oil_pressure < 25 PSI`                             | CRITICAL |
| `RESOURCE_STRESS`   | `cpu_usage > 85%` OR `memory_usage > 85%`           | MEDIUM   |

An additional `ISO_ANOMALY` alert is produced by the Isolation Forest anomaly detector (`semantic_overlay/anomaly_detector.py`) after a 30-sample warmup period.

---

## Health Score

The health score (`semantic_overlay/health_score.py`) starts at 100 and deducts points for:

- Elevated / high / critical engine temperature (5–40 pts)
- Elevated / high / critical vibration (4–35 pts)
- Low / critical oil pressure (5–40 pts)
- High CPU or memory usage (3–15 pts)
- Degraded / failed sensor status (8–20 pts)
- Active alerts (up to 20 additional pts)

| Score  | Status   |
|--------|----------|
| 80–100 | NOMINAL  |
| 50–79  | DEGRADED |
| 0–49   | CRITICAL |

---

## Full TAO ORB Mode

The C++ code in `legacy_corba_app/` is fully implemented for real TAO ORB operation. To build with TAO:

### Prerequisites

```bash
# Ubuntu/Debian
sudo apt-get install libtao-dev libace-dev tao-idl-compiler

# Or build from source: https://github.com/DOCGroup/ACE_TAO
```

### Build

```bash
cd legacy_corba_app
cmake -B build -DUSE_TAO_ORB=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build
```

### Run (TAO mode)

```bash
# Terminal 1 — start the CORBA server
./build/telemetry_server -ORBEndpoint iiop://localhost:12345

# Terminal 2 — start the CORBA bridge
ADAPTER_HOST=localhost ADAPTER_PORT=8000 \
./build/telemetry_client \
  -ORBInitRef TelemetryService=file:///tmp/TelemetryService.ior

# Terminal 3 — start the adapter
cd ../missionforge_adapter
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The Docker mock mode is functionally identical — the mock server uses the same C++ simulation loop and produces the same JSON format that the bridge produces when translating real CORBA data.

---

## Component Descriptions

### `legacy_corba_app/`

The legacy mission computer simulator. Written in C++17, it:

- Implements the `MissionSystem::TelemetryService` CORBA interface from `Telemetry.idl`
- Simulates realistic telemetry with sinusoidal variation around baseline values
- Supports fault injection via flag files (`/tmp/missionforge_fault`, `/tmp/missionforge_reset`)
- In mock mode, outputs JSON to stdout; the bridge forwards this to the adapter
- **This code is never modified by MissionForge — it represents the original legacy system**

### `missionforge_adapter/`

The FastAPI service that forms the heart of the MissionForge overlay. It:

- Receives telemetry from the CORBA bridge via `POST /internal/telemetry`
- Stores readings in a 500-sample in-memory ring buffer
- Invokes the semantic overlay on each new reading
- Exposes a REST API consumed by the dashboard

### `semantic_overlay/`

The intelligence layer. Operates entirely on data extracted from the legacy system:

- `rules.py` — five deterministic rules for known failure modes
- `anomaly_detector.py` — Isolation Forest for statistical outliers
- `health_score.py` — composite 0–100 health score

### `dashboard/`

A self-contained HTML/JS/CSS dashboard (no framework required). Polls the adapter API every 1.5 seconds and displays live telemetry, health score, alerts, and history.

---

## DARPA Low Resource Computing Statement

MissionForge demonstrates that modern predictive maintenance and anomaly detection capability can be added to legacy mission computing infrastructure without:

- Replacing existing hardware
- Modifying existing software
- Requiring high-performance compute
- Installing proprietary middleware on the legacy system

The semantic overlay pattern enables **computational upcycling** — extending the useful life and capability of legacy systems through external observation and intelligence, aligning directly with DARPA's Low Resource Computing programme goals.

---

## Development

### Run the adapter locally (without Docker)

```bash
cd missionforge_adapter
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Useful commands

```bash
# View container logs
docker compose logs -f missionforge-adapter
docker compose logs -f legacy-corba-server

# Stop all services
docker compose down

# Remove volumes
docker compose down -v

# Rebuild single service
docker compose up --build missionforge-adapter
```

---

## License

MIT
