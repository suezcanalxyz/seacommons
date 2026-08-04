# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Periodic drift refresh for in-window distress events.

A drift is a snapshot of wind/current forcing at the time it ran. Weather and
currents keep changing, so a single run stays accurate only for the duration of
its forecast horizon. This refresher re-runs the OpenDrift model for distress
events that are still inside the Live window (7 days) whenever the last run is
older than DRIFT_REFRESH_AFTER_HOURS — so the "current position" estimate on
the map keeps tracking the conditions instead of freezing at the original
forecast.

It is deliberately conservative:

  * only events still within lifecycle.DISTRESS_LIVE_MAX_AGE_DAYS are touched;
  * re-runs go through the shared drift slot (intel.schedule_intel_drift) so a
    burst of refreshes can never starve an operator-triggered manual run;
  * an event currently "computing" is left alone (the in-flight run wins);
  * failures are logged, never raised into the polling loop.

Wired into IntelEngine.start() as a daemon thread.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional

from core.intel.store import IntelEvent, intel_store

logger = logging.getLogger(__name__)

SCAN_INTERVAL_S = 20 * 60            # how often we look for stale drifts
DRIFT_REFRESH_AFTER_HOURS = float(os.getenv("DRIFT_REFRESH_AFTER_HOURS", "6"))


def _parse_utc(value: Any) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _is_drift_stale(event: IntelEvent, *, now: datetime) -> bool:
    """True when the event's last completed drift is older than the cadence."""
    completed_at = _parse_utc(event.metadata.get("drift_completed_at"))
    if completed_at is None:
        requested_at = _parse_utc(event.metadata.get("drift_requested_at"))
        if requested_at is None:
            return False  # never successfully run and not currently computing — leave to manual flow
        completed_at = requested_at
    return (now - completed_at).total_seconds() / 3600 >= DRIFT_REFRESH_AFTER_HOURS


class DriftRefresher:
    """Background thread that re-runs stale drifts for in-window distress events."""

    def __init__(self) -> None:
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="intel-drift-refresh"
        )
        self._thread.start()
        logger.info("DriftRefresher started (scan=%ds, refresh after %.0fh)", SCAN_INTERVAL_S, DRIFT_REFRESH_AFTER_HOURS)

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        # Let the monitors and the drift engine settle before the first pass.
        time.sleep(120)
        while self._running:
            try:
                self._scan()
            except Exception as exc:
                logger.warning("DriftRefresher scan error: %s", exc)
            time.sleep(SCAN_INTERVAL_S)

    def _scan(self) -> None:
        from core.api.routes.intel import schedule_intel_drift
        from core.intel import lifecycle

        now = datetime.now(timezone.utc)
        candidates = intel_store.events(limit=200, max_age_days=lifecycle.DISTRESS_LIVE_MAX_AGE_DAYS)
        refreshed = 0
        for event in candidates:
            if event.lat is None or event.lon is None:
                continue
            if event.tier() != "operational":
                continue
            if not lifecycle.is_within_live_window(event, now=now):
                continue
            if event.metadata.get("drift_status") != "completed":
                continue
            if not _is_drift_stale(event, now=now):
                continue
            observed_at = event.timestamp_utc or now.isoformat()
            if schedule_intel_drift(
                event.id,
                event.lat,
                event.lon,
                event.metadata.get("persons"),
                event.metadata.get("vessel_type"),
                observed_at,
                force=True,
            ):
                refreshed += 1
                logger.info(
                    "DriftRefresher: re-running drift for event %s (last run before %s)",
                    event.id,
                    event.metadata.get("drift_completed_at") or event.metadata.get("drift_requested_at"),
                )
        if refreshed:
            logger.info("DriftRefresher: refreshed %d drift(s)", refreshed)
