"""
health_score.py — Health score computation for MissionForge.

Computes a composite health score (0–100) from the latest telemetry and
active alert set.  The score starts at 100 and deductions are applied for
abnormal readings and active alerts.
"""

from __future__ import annotations

from typing import List, Tuple

from schemas import Alert, TelemetryReading


# ---------------------------------------------------------------------------
# Deduction table
# ---------------------------------------------------------------------------

def compute_health_score(
    reading: TelemetryReading,
    active_alerts: List[Alert],
) -> Tuple[float, dict]:
    """
    Compute health score from telemetry and active alerts.

    Returns:
        (score, details_dict) where score is 0–100.
    """
    score = 100.0
    details: dict = {}

    # ------------------------------------------------------------------
    # Continuous deductions from raw telemetry
    # ------------------------------------------------------------------

    # Engine temperature
    if reading.engine_temp > 260:
        deduct = 40.0
        details["engine_temp"] = f"CRITICAL ({reading.engine_temp:.1f}°C)"
    elif reading.engine_temp > 240:
        deduct = 25.0
        details["engine_temp"] = f"SEVERE ({reading.engine_temp:.1f}°C)"
    elif reading.engine_temp > 220:
        deduct = 15.0
        details["engine_temp"] = f"HIGH ({reading.engine_temp:.1f}°C)"
    elif reading.engine_temp > 200:
        deduct = 5.0
        details["engine_temp"] = f"ELEVATED ({reading.engine_temp:.1f}°C)"
    else:
        deduct = 0.0
        details["engine_temp"] = f"OK ({reading.engine_temp:.1f}°C)"
    score -= deduct

    # Vibration
    if reading.vibration > 1.5:
        deduct = 35.0
        details["vibration"] = f"CRITICAL ({reading.vibration:.3f}g)"
    elif reading.vibration > 1.0:
        deduct = 20.0
        details["vibration"] = f"SEVERE ({reading.vibration:.3f}g)"
    elif reading.vibration > 0.75:
        deduct = 12.0
        details["vibration"] = f"HIGH ({reading.vibration:.3f}g)"
    elif reading.vibration > 0.5:
        deduct = 4.0
        details["vibration"] = f"ELEVATED ({reading.vibration:.3f}g)"
    else:
        deduct = 0.0
        details["vibration"] = f"OK ({reading.vibration:.3f}g)"
    score -= deduct

    # Oil pressure
    if reading.oil_pressure < 10:
        deduct = 40.0
        details["oil_pressure"] = f"CRITICAL ({reading.oil_pressure:.1f} PSI)"
    elif reading.oil_pressure < 15:
        deduct = 25.0
        details["oil_pressure"] = f"SEVERE ({reading.oil_pressure:.1f} PSI)"
    elif reading.oil_pressure < 25:
        deduct = 15.0
        details["oil_pressure"] = f"LOW ({reading.oil_pressure:.1f} PSI)"
    elif reading.oil_pressure < 30:
        deduct = 5.0
        details["oil_pressure"] = f"MARGINAL ({reading.oil_pressure:.1f} PSI)"
    else:
        deduct = 0.0
        details["oil_pressure"] = f"OK ({reading.oil_pressure:.1f} PSI)"
    score -= deduct

    # CPU / memory stress
    max_resource = max(reading.cpu_usage, reading.memory_usage)
    if max_resource > 95:
        deduct = 15.0
    elif max_resource > 85:
        deduct = 8.0
    elif max_resource > 75:
        deduct = 3.0
    else:
        deduct = 0.0
    score -= deduct
    details["resources"] = (
        f"CPU {reading.cpu_usage:.1f}%, MEM {reading.memory_usage:.1f}%"
    )

    # Sensor status
    if reading.sensor_status == "FAILED":
        score -= 20.0
        details["sensor_status"] = "FAILED"
    elif reading.sensor_status == "DEGRADED":
        score -= 8.0
        details["sensor_status"] = "DEGRADED"
    else:
        details["sensor_status"] = "OK"

    # ------------------------------------------------------------------
    # Active alert deductions
    # ------------------------------------------------------------------
    alert_deduction = 0.0
    for alert in active_alerts:
        if alert.severity == "CRITICAL":
            alert_deduction += 5.0
        elif alert.severity == "HIGH":
            alert_deduction += 3.0
        elif alert.severity == "MEDIUM":
            alert_deduction += 1.5
        elif alert.severity == "LOW":
            alert_deduction += 0.5
    # Cap alert deductions to avoid double-penalising
    alert_deduction = min(alert_deduction, 20.0)
    score -= alert_deduction

    # ------------------------------------------------------------------
    # Clamp and return
    # ------------------------------------------------------------------
    score = max(0.0, min(100.0, score))
    details["active_alerts"] = len(active_alerts)
    return score, details
