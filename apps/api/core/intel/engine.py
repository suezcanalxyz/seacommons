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
        self._track_store: object | None = None
        self._vessel_incidents: object | None = None
        self._ais_anomaly: object | None = None
        self._drift_refresh: object | None = None
        self._mda_watch: object | None = None
        self._gdacs: object | None = None
        self._ais_source_observation: object | None = None
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
                from core.vessels.track_store import track_store
                track_store.start()
                self._track_store = track_store
                logger.info("IntelEngine: AIS track store started")
            except Exception as exc:
                logger.warning("IntelEngine: AIS track store failed to start: %s", exc)

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

            try:
                from core.anomaly.ais import AISAnomalyDetector
                self._ais_anomaly = AISAnomalyDetector()
                self._ais_anomaly.start()  # type: ignore[attr-defined]
                logger.info("IntelEngine: AIS anomaly detector started")
            except Exception as exc:
                logger.warning("IntelEngine: AIS anomaly detector failed to start: %s", exc)

            try:
                from core.mda.watch import mda_watch
                mda_watch.start()
                self._mda_watch = mda_watch
                logger.info("IntelEngine: MDA watch (rendezvous / infra / gap / identity) started")
            except Exception as exc:
                logger.warning("IntelEngine: MDA watch failed to start: %s", exc)

            try:
                from core.vessels.ais_source_observation import ais_source_observation_sampler
                ais_source_observation_sampler.start()
                self._ais_source_observation = ais_source_observation_sampler
                logger.info("IntelEngine: AIS SourceObservation sampler started")
            except Exception as exc:
                logger.warning("IntelEngine: AIS SourceObservation sampler failed to start: %s", exc)

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
            self._track_store,
            self._vessel_incidents,
            self._ais_anomaly,
            self._mda_watch,
            self._drift_refresh,
            self._gdacs,
            self._ais_source_observation,
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

    def status(self) -> dict:
        """Which monitors actually attached -- so a silent pipeline is
        visible rather than assumed."""
        try:
            from core.vessels.aisstream import position_hook_count

            hooks = position_hook_count()
        except Exception:
            hooks = 0
        try:
            from core.vessels.ais_runtime import runtime as ais_runtime
            current_runtime = ais_runtime()
            ais_runtime_status = current_runtime.status() if current_runtime is not None else {}
        except Exception:
            ais_runtime_status = {}
        return {
            "running": self._started,
            "ais_fusion_mode": ais_runtime_status.get("mode", "legacy"),
            "aiscast_started": bool(ais_runtime_status.get("aiscast_started", False)),
            "twikit": self._twikit is not None,
            "twitter_api": self._twitter is not None,
            "news": self._news is not None,
            "ais_spike": self._ais is not None,
            "track_store": self._track_store is not None,
            "mda_watch": self._mda_watch is not None,
            "vessel_incidents": self._vessel_incidents is not None,
            "ais_anomaly": self._ais_anomaly is not None,
            "gdacs": self._gdacs is not None,
            "drift_refresher": self._drift_refresh is not None,
            "ais_source_observation": self._ais_source_observation is not None,
            "ais_feed_hooks": hooks,
        }


# Module-level singleton
intel_engine = IntelEngine()
