"""
anomaly_detector.py — Isolation Forest anomaly detection for MissionForge.

This module provides a second layer of detection on top of the rule engine.
It trains an Isolation Forest model incrementally on incoming telemetry and
flags statistical outliers that the rule engine may not catch.

The detector warms up silently for the first WARMUP_SAMPLES readings, then
starts producing ISO_ANOMALY alerts for anomalous readings.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

import numpy as np

from schemas import Alert, TelemetryReading

logger = logging.getLogger("missionforge.anomaly")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
WARMUP_SAMPLES   = 30       # Collect this many samples before first training
RETRAIN_INTERVAL = 20       # Retrain every N new samples after warmup
CONTAMINATION    = 0.05     # Expected fraction of anomalies (5 %)

# Features used for anomaly detection
FEATURE_NAMES = [
    "engine_temp",
    "vibration",
    "fuel_flow",
    "oil_pressure",
    "cpu_usage",
    "memory_usage",
]

# Cooldown between identical anomaly alerts (seconds)
_ANOMALY_COOLDOWN = 30


def _reading_to_vector(r: TelemetryReading) -> List[float]:
    return [
        r.engine_temp,
        r.vibration,
        r.fuel_flow,
        r.oil_pressure,
        r.cpu_usage,
        r.memory_usage,
    ]


class AnomalyDetector:
    """
    Incremental Isolation Forest anomaly detector.

    Collects telemetry vectors, retrains periodically, and flags anomalies.
    Falls back gracefully if scikit-learn is not available.
    """

    def __init__(self) -> None:
        self._samples: List[List[float]] = []
        self._model = None
        self._samples_since_train = 0
        self._last_alert_ts: str = ""
        self._sklearn_available = self._check_sklearn()

    @staticmethod
    def _check_sklearn() -> bool:
        try:
            from sklearn.ensemble import IsolationForest  # noqa: F401
            return True
        except ImportError:
            logger.warning("scikit-learn not available — anomaly detection disabled")
            return False

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def update(self, reading: TelemetryReading) -> None:
        """Add a new reading to the training buffer and retrain if needed."""
        if not self._sklearn_available:
            return

        vec = _reading_to_vector(reading)
        self._samples.append(vec)
        self._samples_since_train += 1

        # Train after warmup; retrain periodically
        if (len(self._samples) == WARMUP_SAMPLES or
                (len(self._samples) > WARMUP_SAMPLES and
                 self._samples_since_train >= RETRAIN_INTERVAL)):
            self._train()
            self._samples_since_train = 0

    def check(self, reading: TelemetryReading) -> List[Alert]:
        """
        Check whether the reading is anomalous.
        Returns a list containing one Alert if anomalous, otherwise empty.
        """
        if not self._sklearn_available or self._model is None:
            return []

        vec = np.array([_reading_to_vector(reading)])
        try:
            score = self._model.score_samples(vec)[0]
            prediction = self._model.predict(vec)[0]
        except Exception as exc:
            logger.debug("Anomaly check failed: %s", exc)
            return []

        if prediction == -1:
            ts = reading.timestamp
            if not self._should_alert(ts):
                return []
            self._last_alert_ts = ts

            # Identify which features deviate most from training mean
            train_arr = np.array(self._samples)
            means = train_arr.mean(axis=0)
            stds  = train_arr.std(axis=0) + 1e-9
            z_scores = (np.array(_reading_to_vector(reading)) - means) / stds
            top_idxs = np.argsort(np.abs(z_scores))[-3:][::-1]
            culprits = [FEATURE_NAMES[i] for i in top_idxs]

            return [Alert(
                alert_type="ISO_ANOMALY",
                severity="MEDIUM",
                explanation=(
                    f"Isolation Forest detected a statistical anomaly "
                    f"(anomaly score: {score:.3f}). "
                    f"Top deviating signals: {', '.join(culprits)}."
                ),
                timestamp=ts,
                contributing_signals=culprits,
            )]

        return []

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _train(self) -> None:
        from sklearn.ensemble import IsolationForest
        try:
            X = np.array(self._samples)
            self._model = IsolationForest(
                contamination=CONTAMINATION,
                random_state=42,
                n_estimators=100,
            )
            self._model.fit(X)
            logger.debug("Isolation Forest retrained on %d samples", len(X))
        except Exception as exc:
            logger.warning("Failed to train Isolation Forest: %s", exc)
            self._model = None

    def _should_alert(self, ts: str) -> bool:
        if not self._last_alert_ts:
            return True
        try:
            last = datetime.fromisoformat(self._last_alert_ts.replace("Z", "+00:00"))
            now  = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return (now - last).total_seconds() >= _ANOMALY_COOLDOWN
        except ValueError:
            return True
