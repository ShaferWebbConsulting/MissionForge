"""
rules.py — Rule-based semantic overlay for MissionForge.

This module implements the lightweight rule engine that analyzes incoming
telemetry and generates predictive maintenance / anomaly alerts.

Rules operate on the TelemetryStore (read-only access) and produce Alert
objects.  The legacy CORBA application is never modified or contacted by
this module.

Rule definitions:
  1. HIGH_TEMP          — engine_temp > 220°C
  2. HIGH_VIBRATION     — vibration  > 0.75 g
  3. PREDICTIVE_FAILURE — engine_temp rising 5 consecutive samples
                          AND vibration also rising
  4. LOW_OIL_PRESSURE   — oil_pressure < 25 PSI
  5. RESOURCE_STRESS    — cpu_usage > 85% OR memory_usage > 85%
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from corba_bridge import TelemetryStore

from schemas import Alert

# ---------------------------------------------------------------------------
# Thresholds (centralised so they are easy to tune)
# ---------------------------------------------------------------------------
THRESHOLDS = {
    "HIGH_TEMP":         220.0,   # °C
    "HIGH_VIBRATION":    0.75,    # g
    "LOW_OIL_PRESSURE":  25.0,    # PSI
    "RESOURCE_STRESS":   85.0,    # % (cpu or memory)
    "TREND_WINDOW":      5,       # samples for trend detection
}

# ---------------------------------------------------------------------------
# Deduplication: track the last timestamp each alert type was fired so we
# don't spam identical alerts every second.
# ---------------------------------------------------------------------------
_last_fired: dict[str, str] = {}
_COOLDOWN_SECONDS = 15  # minimum gap between same alert type


def _should_fire(alert_type: str, now_iso: str) -> bool:
    """Return True if the alert_type cooldown has expired."""
    last = _last_fired.get(alert_type)
    if last is None:
        return True
    try:
        last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
        now_dt  = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
        return (now_dt - last_dt).total_seconds() >= _COOLDOWN_SECONDS
    except ValueError:
        return True


def _fire(alert_type: str, severity: str, explanation: str,
          timestamp: str, signals: List[str]) -> Alert:
    _last_fired[alert_type] = timestamp
    return Alert(
        alert_type=alert_type,
        severity=severity,
        explanation=explanation,
        timestamp=timestamp,
        contributing_signals=signals,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def evaluate_rules(store: "TelemetryStore") -> List[Alert]:
    """
    Evaluate all rules against the current telemetry store state.
    Returns a (possibly empty) list of new Alert objects.
    """
    latest = store.latest()
    if latest is None:
        return []

    alerts: List[Alert] = []
    ts = latest.timestamp

    # ------------------------------------------------------------------
    # Rule 1: HIGH_TEMP
    # ------------------------------------------------------------------
    if latest.engine_temp > THRESHOLDS["HIGH_TEMP"]:
        if _should_fire("HIGH_TEMP", ts):
            alerts.append(_fire(
                alert_type="HIGH_TEMP",
                severity="HIGH",
                explanation=(
                    f"Engine temperature {latest.engine_temp:.1f}°C exceeds "
                    f"safety threshold of {THRESHOLDS['HIGH_TEMP']}°C. "
                    "Immediate inspection recommended."
                ),
                timestamp=ts,
                signals=["engine_temp"],
            ))

    # ------------------------------------------------------------------
    # Rule 2: HIGH_VIBRATION
    # ------------------------------------------------------------------
    if latest.vibration > THRESHOLDS["HIGH_VIBRATION"]:
        if _should_fire("HIGH_VIBRATION", ts):
            alerts.append(_fire(
                alert_type="HIGH_VIBRATION",
                severity="HIGH",
                explanation=(
                    f"Vibration {latest.vibration:.3f}g exceeds threshold "
                    f"of {THRESHOLDS['HIGH_VIBRATION']}g. "
                    "Possible bearing or rotor imbalance."
                ),
                timestamp=ts,
                signals=["vibration"],
            ))

    # ------------------------------------------------------------------
    # Rule 3: PREDICTIVE_FAILURE (trend detection)
    # ------------------------------------------------------------------
    window = store.recent_window(THRESHOLDS["TREND_WINDOW"])
    if len(window) == THRESHOLDS["TREND_WINDOW"]:
        temps  = [r.engine_temp  for r in window]
        vibs   = [r.vibration    for r in window]
        temp_rising = all(temps[i] < temps[i + 1] for i in range(len(temps) - 1))
        vib_rising  = all(vibs[i]  < vibs[i + 1]  for i in range(len(vibs) - 1))

        if temp_rising and vib_rising:
            if _should_fire("PREDICTIVE_FAILURE", ts):
                delta_temp = temps[-1] - temps[0]
                delta_vib  = vibs[-1]  - vibs[0]
                alerts.append(_fire(
                    alert_type="PREDICTIVE_FAILURE",
                    severity="CRITICAL",
                    explanation=(
                        f"Engine temperature has risen {delta_temp:.1f}°C over "
                        f"{THRESHOLDS['TREND_WINDOW']} consecutive samples while "
                        f"vibration increased {delta_vib:.3f}g. "
                        "Combined trend indicates imminent component failure. "
                        "Recommend immediate maintenance action."
                    ),
                    timestamp=ts,
                    signals=["engine_temp", "vibration"],
                ))

    # ------------------------------------------------------------------
    # Rule 4: LOW_OIL_PRESSURE
    # ------------------------------------------------------------------
    if latest.oil_pressure < THRESHOLDS["LOW_OIL_PRESSURE"]:
        if _should_fire("LOW_OIL_PRESSURE", ts):
            alerts.append(_fire(
                alert_type="LOW_OIL_PRESSURE",
                severity="CRITICAL",
                explanation=(
                    f"Oil pressure {latest.oil_pressure:.1f} PSI is below "
                    f"minimum safe level of {THRESHOLDS['LOW_OIL_PRESSURE']} PSI. "
                    "Risk of engine seizure."
                ),
                timestamp=ts,
                signals=["oil_pressure"],
            ))

    # ------------------------------------------------------------------
    # Rule 5: RESOURCE_STRESS
    # ------------------------------------------------------------------
    if (latest.cpu_usage > THRESHOLDS["RESOURCE_STRESS"] or
            latest.memory_usage > THRESHOLDS["RESOURCE_STRESS"]):
        if _should_fire("RESOURCE_STRESS", ts):
            signals = []
            parts   = []
            if latest.cpu_usage > THRESHOLDS["RESOURCE_STRESS"]:
                signals.append("cpu_usage")
                parts.append(f"CPU {latest.cpu_usage:.1f}%")
            if latest.memory_usage > THRESHOLDS["RESOURCE_STRESS"]:
                signals.append("memory_usage")
                parts.append(f"memory {latest.memory_usage:.1f}%")
            alerts.append(_fire(
                alert_type="RESOURCE_STRESS",
                severity="MEDIUM",
                explanation=(
                    f"Legacy computer resource stress: {', '.join(parts)} "
                    f"exceed {THRESHOLDS['RESOURCE_STRESS']}%. "
                    "Mission computation may be impaired."
                ),
                timestamp=ts,
                signals=signals,
            ))

    return alerts
