# SPDX-License-Identifier: AGPL-3.0-or-later
"""
IntelEngine — orchestrates all maritime intelligence monitors.

Starts TwitterMonitor, NewsMonitor, and AISSpikeDetector in background
daemon threads.  All three share the module-level IntelStore singleton.

Usage (called once at API startup):
    from core.intel.engine import intel_engine
    intel_engine.start()
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class IntelEngine:
    def __init__(self) -> None:
        self._twitter: Optional[object] = None
        self._news: Optional[object] = None
        self._ais: Optional[object] = None
        self._mastodon: Optional[object] = None
        self._started = False

    def start(
        self,
        twitter_bearer: str = "",
        twscrape_accounts: str = "",
        twitter_enabled: bool = True,
        news_enabled: bool = True,
        ais_enabled: bool = True,
        mastodon_enabled: bool = True,
    ) -> None:
        if self._started:
            return
        self._started = True

        if twitter_enabled:
            try:
                from core.intel.twitter_monitor import TwitterMonitor
                self._twitter = TwitterMonitor(
                    bearer_token=twitter_bearer,
                    twscrape_accounts=twscrape_accounts,
                )
                self._twitter.start()  # type: ignore[attr-defined]
                api = "official" if twitter_bearer else ("twscrape" if twscrape_accounts else "nitter")
                logger.info("IntelEngine: Twitter monitor started (api=%s)", api)
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

        if mastodon_enabled:
            try:
                from core.intel.mastodon_monitor import MastodonMonitor
                self._mastodon = MastodonMonitor()
                self._mastodon.start()  # type: ignore[attr-defined]
                logger.info("IntelEngine: Mastodon monitor started")
            except Exception as exc:
                logger.warning("IntelEngine: Mastodon monitor failed to start: %s", exc)

    def stop(self) -> None:
        for monitor in (self._twitter, self._news, self._ais, self._mastodon):
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
