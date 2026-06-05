"""
main.py — MissionForge Adapter FastAPI application.

This is the central hub of the MissionForge semantic overlay.  It:
  1. Receives telemetry from the legacy CORBA application (via /internal/telemetry)
  2. Runs the semantic overlay (rules + anomaly detector + health score)
  3. Exposes a public REST API consumed by the dashboard

Architecture:
  Legacy CORBA App  →  /internal/telemetry  →  TelemetryStore
                                               ↓
                              Semantic Overlay (rules + anomaly)
                                               ↓
                        /telemetry/latest  /alerts  /health
                                               ↓
                                         Dashboard
"""

from __future__ import annotations

import sys
import os
import time
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from corba_bridge import store
from schemas import (
    TelemetryReading,
    Alert,
    HealthStatus,
    FaultInjectionRequest,
    SystemStatus,
)

# Semantic overlay modules (mounted at /app/semantic_overlay/)
from rules import evaluate_rules
from anomaly_detector import AnomalyDetector
from health_score import compute_health_score

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("missionforge.adapter")

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="MissionForge Adapter",
    description=(
        "Semantic overlay for legacy CORBA mission systems. "
        "Provides predictive maintenance and anomaly detection without "
        "modifying the legacy application."
    ),
    version="1.0.0",
)

# Allow dashboard (served on port 8080) and local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Module-level anomaly detector instance (trained incrementally)
anomaly_detector = AnomalyDetector()

# Track startup time for uptime reporting
_start_time = time.time()

# In-memory alert ring buffer (most recent MAX_ALERTS)
MAX_ALERTS = 200
_alerts: List[Alert] = []


def _add_alert(alert: Alert) -> None:
    """Append an alert, capping the buffer at MAX_ALERTS."""
    _alerts.append(alert)
    if len(_alerts) > MAX_ALERTS:
        _alerts.pop(0)


# ---------------------------------------------------------------------------
# Internal ingest endpoint — called by the CORBA bridge
# ---------------------------------------------------------------------------

@app.post("/internal/telemetry", include_in_schema=False)
async def ingest_telemetry(reading: TelemetryReading) -> dict:
    """
    Receive a telemetry reading from the CORBA bridge.
    Run the semantic overlay and store results.
    This endpoint is internal and not part of the public API.
    """
    store.push(reading)
    logger.debug("Received telemetry: engine_temp=%.1f", reading.engine_temp)

    # Run rule-based analysis
    new_alerts = evaluate_rules(store)
    for a in new_alerts:
        _add_alert(a)
        logger.info("Alert raised: %s [%s]", a.alert_type, a.severity)

    # Feed anomaly detector (trains incrementally after warmup)
    anomaly_detector.update(reading)
    iso_alerts = anomaly_detector.check(reading)
    for a in iso_alerts:
        _add_alert(a)

    return {"status": "ok", "alerts_generated": len(new_alerts) + len(iso_alerts)}


# ---------------------------------------------------------------------------
# Public API endpoints
# ---------------------------------------------------------------------------

@app.get("/telemetry/latest", response_model=TelemetryReading, tags=["Telemetry"])
async def get_latest_telemetry() -> TelemetryReading:
    """Return the most recent telemetry snapshot from the legacy system."""
    reading = store.latest()
    if reading is None:
        raise HTTPException(
            status_code=503,
            detail="No telemetry received yet — waiting for legacy CORBA server",
        )
    return reading


@app.get("/telemetry/history", response_model=List[TelemetryReading], tags=["Telemetry"])
async def get_telemetry_history(limit: int = 100) -> List[TelemetryReading]:
    """Return recent telemetry history (most recent *limit* readings)."""
    limit = max(1, min(limit, MAX_ALERTS))
    return store.history(limit=limit)


@app.get("/health", response_model=HealthStatus, tags=["Health"])
async def get_health() -> HealthStatus:
    """Return current system health score and status."""
    reading = store.latest()
    if reading is None:
        return HealthStatus(
            score=100.0,
            status="NOMINAL",
            active_alert_count=0,
            last_updated=datetime.now(timezone.utc).isoformat(),
            details={"message": "Awaiting telemetry"},
        )

    active_alerts = _get_active_alerts()
    score, details = compute_health_score(reading, active_alerts)

    if score >= 80:
        status = "NOMINAL"
    elif score >= 50:
        status = "DEGRADED"
    else:
        status = "CRITICAL"

    return HealthStatus(
        score=round(score, 1),
        status=status,
        active_alert_count=len(active_alerts),
        last_updated=reading.timestamp,
        details=details,
    )


@app.get("/alerts", response_model=List[Alert], tags=["Alerts"])
async def get_alerts(limit: int = 50) -> List[Alert]:
    """Return recent alerts generated by the semantic overlay."""
    limit = max(1, min(limit, MAX_ALERTS))
    return list(reversed(_alerts[-limit:]))


# ---------------------------------------------------------------------------
# Demo endpoints
# ---------------------------------------------------------------------------

@app.post("/demo/inject-fault", tags=["Demo"])
async def inject_fault(request: Optional[FaultInjectionRequest] = None) -> dict:
    """
    Inject a fault scenario into the legacy telemetry stream.
    Causes gradual degradation of engine temperature, vibration, and oil pressure,
    triggering predictive maintenance alerts from the semantic overlay.
    """
    store.inject_fault()
    logger.info("Fault injection activated")
    return {
        "status": "fault_injected",
        "message": "Telemetry will degrade over the next 10–15 seconds. "
                   "Watch /alerts and /health for predictive maintenance alerts.",
    }


@app.post("/demo/reset", tags=["Demo"])
async def reset_demo() -> dict:
    """Reset the demo: clear faults, telemetry history, and alerts."""
    store.reset()
    _alerts.clear()
    logger.info("Demo reset")
    return {"status": "reset", "message": "System reset to baseline."}


@app.get("/status", response_model=SystemStatus, tags=["System"])
async def get_status() -> SystemStatus:
    """Return system status information."""
    return SystemStatus(
        running=True,
        mode="mock",
        telemetry_count=store.count,
        uptime_seconds=round(time.time() - _start_time, 1),
        fault_active=store.fault_active,
    )


# ---------------------------------------------------------------------------
# Root — quick sanity check
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
async def root() -> dict:
    return {
        "service": "MissionForge Adapter",
        "version": "1.0.0",
        "docs": "/docs",
        "telemetry": "/telemetry/latest",
        "health": "/health",
        "alerts": "/alerts",
    }


# ---------------------------------------------------------------------------
# Helper — active alerts (last 60 s)
# ---------------------------------------------------------------------------

def _get_active_alerts(window_seconds: int = 60) -> List[Alert]:
    """Return alerts raised in the last *window_seconds*."""
    now = datetime.now(timezone.utc)
    active = []
    for a in reversed(_alerts):
        try:
            ts = datetime.fromisoformat(a.timestamp.replace("Z", "+00:00"))
            if (now - ts).total_seconds() <= window_seconds:
                active.append(a)
        except ValueError:
            pass
    return active
