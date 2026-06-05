"""
corba_bridge.py — CORBA / mock telemetry bridge for MissionForge.

In mock mode (default): The legacy_corba_app container streams JSON lines
to a named pipe or HTTP endpoint.  This module provides the in-memory store
that the FastAPI app uses.

In TAO mode: The CORBA client would call the IDL-defined interface and push
readings into the same store.  The adapter is identical in both cases — only
the ingest path differs.

This module is imported by main.py.
"""

from __future__ import annotations

import threading
from collections import deque
from datetime import datetime, timezone
from typing import Deque, List, Optional

from schemas import TelemetryReading

# ---------------------------------------------------------------------------
# In-memory telemetry ring buffer
# ---------------------------------------------------------------------------

MAX_HISTORY = 500  # number of readings to retain


class TelemetryStore:
    """Thread-safe ring buffer for telemetry readings."""

    def __init__(self, maxlen: int = MAX_HISTORY) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._buffer: Deque[TelemetryReading] = deque(maxlen=maxlen)
        self._fault_active: bool = False
        self._fault_step: int = 0
        self._telemetry_count: int = 0

    # ------------------------------------------------------------------
    # Write path
    # ------------------------------------------------------------------

    def push(self, reading: TelemetryReading) -> None:
        """Add a telemetry reading to the store."""
        with self._lock:
            self._buffer.append(reading)
            self._telemetry_count += 1

    # ------------------------------------------------------------------
    # Read path
    # ------------------------------------------------------------------

    def latest(self) -> Optional[TelemetryReading]:
        """Return the most recent reading, or None if the store is empty."""
        with self._lock:
            return self._buffer[-1] if self._buffer else None

    def history(self, limit: int = 100) -> List[TelemetryReading]:
        """Return the most recent *limit* readings (oldest first)."""
        with self._lock:
            items = list(self._buffer)
        return items[-limit:]

    def recent_window(self, n: int) -> List[TelemetryReading]:
        """Return the last *n* readings for trend analysis."""
        with self._lock:
            items = list(self._buffer)
        return items[-n:] if len(items) >= n else items

    @property
    def count(self) -> int:
        with self._lock:
            return self._telemetry_count

    # ------------------------------------------------------------------
    # Fault injection / reset
    # ------------------------------------------------------------------

    @property
    def fault_active(self) -> bool:
        with self._lock:
            return self._fault_active

    def inject_fault(self) -> None:
        """Signal the legacy server to start degrading (via flag file)."""
        with self._lock:
            self._fault_active = True
            self._fault_step = 0
        # Write flag file that telemetry_server.cpp polls
        try:
            open("/tmp/missionforge_fault", "w").close()
        except OSError:
            pass

    def reset(self) -> None:
        """Clear fault state and reset the legacy server."""
        with self._lock:
            self._fault_active = False
            self._fault_step = 0
            self._buffer.clear()
            self._telemetry_count = 0
        try:
            open("/tmp/missionforge_reset", "w").close()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Module-level singleton used by FastAPI routes
# ---------------------------------------------------------------------------
store = TelemetryStore()
