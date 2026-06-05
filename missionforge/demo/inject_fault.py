#!/usr/bin/env python3
"""
inject_fault.py — MissionForge Demo Fault Injector

Sends a fault-injection command to the MissionForge adapter, causing the
legacy telemetry server to gradually degrade its readings:
  - engine_temp rises   → triggers HIGH_TEMP → PREDICTIVE_FAILURE
  - vibration rises     → triggers HIGH_VIBRATION
  - oil_pressure falls  → triggers LOW_OIL_PRESSURE

Usage:
    python3 inject_fault.py [--host localhost] [--port 8000] [--reset]

Options:
    --host    Adapter hostname (default: localhost)
    --port    Adapter port     (default: 8000)
    --reset   Reset the system instead of injecting a fault
    --watch   Poll /alerts and /health after injection
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error


def make_url(host: str, port: int, path: str) -> str:
    return f"http://{host}:{port}{path}"


def post(url: str, body: dict | None = None) -> dict:
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


def get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as resp:
        return json.loads(resp.read())


def print_health(health: dict) -> None:
    score  = health.get("score", "?")
    status = health.get("status", "?")
    count  = health.get("active_alert_count", 0)
    bar    = "█" * int(score // 5) + "░" * (20 - int(score // 5))
    print(f"  Health: [{bar}] {score:.0f}/100  {status}  ({count} active alerts)")


def print_alerts(alerts: list) -> None:
    if not alerts:
        print("  Alerts: none")
        return
    for a in alerts[:5]:
        sev = a.get("severity", "?")
        typ = a.get("alert_type", "?")
        ts  = a.get("timestamp", "")[:19]
        print(f"  [{sev:8s}] {typ:<25s}  {ts}")


def main() -> None:
    parser = argparse.ArgumentParser(description="MissionForge demo fault injector")
    parser.add_argument("--host",  default="localhost")
    parser.add_argument("--port",  type=int, default=8000)
    parser.add_argument("--reset", action="store_true", help="Reset system")
    parser.add_argument("--watch", action="store_true", help="Watch alerts for 30s after injection")
    args = parser.parse_args()

    if args.reset:
        print(f"Resetting MissionForge system at {args.host}:{args.port}…")
        try:
            result = post(make_url(args.host, args.port, "/demo/reset"))
            print("✓", result.get("message", "Reset OK"))
        except Exception as e:
            print("✗ Reset failed:", e, file=sys.stderr)
            sys.exit(1)
        return

    print(f"Injecting fault into legacy CORBA system via {args.host}:{args.port}…")
    print("  Telemetry will degrade over the next 10-15 seconds.")
    print("  Watch the dashboard at http://localhost:8080")
    print()

    try:
        result = post(make_url(args.host, args.port, "/demo/inject-fault"))
        print("✓", result.get("message", "Fault injected"))
    except Exception as e:
        print("✗ Fault injection failed:", e, file=sys.stderr)
        sys.exit(1)

    if not args.watch:
        return

    print()
    print("Watching /health and /alerts for 30 seconds…  (Ctrl-C to stop)")
    print("─" * 60)

    for i in range(30):
        try:
            health = get(make_url(args.host, args.port, "/health"))
            alerts = get(make_url(args.host, args.port, "/alerts?limit=5"))
            print(f"t+{i+1:02d}s")
            print_health(health)
            print_alerts(alerts)
            print()
        except urllib.error.URLError as e:
            print(f"  Warning: could not reach adapter — {e}")
        time.sleep(1)

    print("─" * 60)
    print("Demo complete. Run with --reset to restore normal operation.")


if __name__ == "__main__":
    main()
