# SPDX-License-Identifier: AGPL-3.0-or-later
"""
IntelEngine — orchestrates all maritime intelligence monitors.

Usage (called once at API startup):
    from core.intel.engine import intel_engine
    intel_engine.start()
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class IntelEngine:
    def __init__(self) -> None:
        self._twitter: object | None = None
        self._twikit: object | None = None
        self._news: object | None = None
        self._ais: object | None = None
        self._vessel_incidents: object | None = None
        self._drift_refresh: object | None = None
        self._gdacs: object | None = None
        self._started = False

    def start(
        self,
        twitter_bearer: str = "",
        twitter_enabled: bool = True,
        twikit_enabled: bool = False,
        twikit_cookies_file: str = "",
        twikit_accounts: str = "",
        twikit_poll_interval_s: int = 300,
        twikit_priority_accounts: str = "",
        twikit_priority_poll_interval_s: int = 45,
        twikit_alerts_enabled: bool = False,
        news_enabled: bool = True,
        ais_enabled: bool = True,
        gdacs_enabled: bool = True,
    ) -> None:
        if self._started:
            return
        self._started = True

        if twitter_enabled:
            try:
                from core.intel.twikit_monitor import TwikitMonitor
                self._twikit = TwikitMonitor(
                    enabled=twikit_enabled,
                    cookies_file=twikit_cookies_file,
                    accounts=twikit_accounts,
                    poll_interval_s=twikit_poll_interval_s,
                    priority_accounts=twikit_priority_accounts,
                    priority_poll_interval_s=twikit_priority_poll_interval_s,
                    alerts_enabled=twikit_alerts_enabled,
                )
                self._twikit.start()  # type: ignore[attr-defined]
                logger.info(
                    "IntelEngine: X monitor (twikit, primary) %s",
                    "started with account session"
                    if self._twikit.configured
                    else "inactive — set TWIKIT_ENABLED + TWIKIT_COOKIES_FILE",
                )
            except Exception as exc:
                logger.warning("IntelEngine: X (twikit) monitor failed to start: %s", exc)

            try:
                from core.intel.twitter_monitor import TwitterMonitor
                self._twitter = TwitterMonitor(bearer_token=twitter_bearer)
                self._twitter.start()  # type: ignore[attr-defined]
                logger.info(
                    "IntelEngine: X monitor (official API, secondary) %s",
                    "started with official API" if twitter_bearer else "waiting for official credentials",
                )
            except Exception as exc:
                logger.warning("IntelEngine: Twitter monitor failed to start: %s", exc)

        if news_enabled:
            try:
                from core.intel.news_monitor import NewsMonitor
                self._news = NewsMonitor()
                self._news.start()  # type: ignore[attr-defined]
                logger.info("IntelEngine: News monitor started")
            except Exception as exc:
                logger.warning("IntelEngine: News monitor failed to start: %s", exc)

        if ais_enabled:
            try:
                from core.intel.ais_spike_detector import AISSpikeDetector
                self._ais = AISSpikeDetector()
                self._ais.start()  # type: ignore[attr-defined]
                logger.info("IntelEngine: AIS spike detector started")
            except Exception as exc:
                logger.warning("IntelEngine: AIS spike detector failed to start: %s", exc)

            try:
                from core.intel.drift_refresher import DriftRefresher
                self._drift_refresh = DriftRefresher()
                self._drift_refresh.start()  # type: ignore[attr-defined]
            except Exception as exc:
                logger.warning("IntelEngine: drift refresher failed to start: %s", exc)

            try:
                from core.intel.vessel_incident_monitor import vessel_incident_monitor
                vessel_incident_monitor.start()
                self._vessel_incidents = vessel_incident_monitor
                logger.info("IntelEngine: vessel incident monitor started")
            except Exception as exc:
                logger.warning("IntelEngine: vessel incident monitor failed to start: %s", exc)

        if gdacs_enabled:
            try:
                from core.intel.gdacs_monitor import GDACSMonitor
                self._gdacs = GDACSMonitor()
                self._gdacs.start()  # type: ignore[attr-defined]
                logger.info("IntelEngine: GDACS monitor started")
            except Exception as exc:
                logger.warning("IntelEngine: GDACS monitor failed to start: %s", exc)

    def stop(self) -> None:
        for monitor in (
            self._twitter,
            self._twikit,
            self._news,
            self._ais,
            self._vessel_incidents,
            self._drift_refresh,
            self._gdacs,
        ):
            if monitor:
                try:
                    monitor.stop()  # type: ignore[attr-defined]
                except Exception:
                    pass
        self._started = False

    @property
    def is_running(self) -> bool:
        return self._started


# Module-level singleton
intel_engine = IntelEngine()
