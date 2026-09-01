# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bounded worker pool for humanitarian media-OCR jobs (docs/fixes.md F-02).

``_TESSERACT_LOCK`` / ``_EASYOCR_LOCK`` already serialize the CPU-heavy OCR
passes, but each tweet carrying media still spawned its own daemon thread that
then blocked on those locks -- a media burst piled up unbounded waiting
threads and RAM, degrading Uvicorn/Live latency even though Tesseract itself
was serialized.

This replaces per-event ``threading.Thread()`` with one fixed-size pool plus
an explicit bounded backlog. A job is deduplicated by event identity; a job
that would overflow both the pool backlog and the deferred backlog is
rejected with a recoverable ``deferred_queue_full`` state and a metric --
never a silent daemon-thread pile-up and never silent loss.

VM-safe defaults (env-overridable): ``MEDIA_OCR_WORKERS=1``,
``MEDIA_OCR_QUEUE_MAXSIZE=16``.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

logger = logging.getLogger(__name__)

MEDIA_OCR_WORKERS = max(1, int(os.getenv("MEDIA_OCR_WORKERS", "1")))
MEDIA_OCR_QUEUE_MAXSIZE = max(1, int(os.getenv("MEDIA_OCR_QUEUE_MAXSIZE", "16")))


class MediaOcrQueue:
    """One process-wide bounded executor for media-OCR jobs."""

    def __init__(self, workers: int, maxsize: int) -> None:
        self._workers = max(1, workers)
        self._maxsize = max(1, maxsize)
        self._executor: ThreadPoolExecutor | None = None
        self._lock = threading.Lock()
        self._pending: dict[str, float] = {}  # job_key -> enqueued monotonic ts
        self._inflight: set[str] = set()
        self._deferred: deque[tuple[str, Callable[[], None]]] = deque()

    def _ensure_executor(self) -> ThreadPoolExecutor:
        executor = self._executor
        if executor is None:
            with self._lock:
                if self._executor is None:
                    self._executor = ThreadPoolExecutor(
                        max_workers=self._workers, thread_name_prefix="intel-x-ocr"
                    )
                executor = self._executor
        return executor

    def submit(self, job_key: str, fn: Callable[[], None]) -> str:
        """Enqueue a dedup'd OCR job.

        Returns one of ``queued`` | ``deduplicated`` | ``deferred_queue_full``
        | ``dropped``.
        """
        self._ensure_executor()
        with self._lock:
            if self._is_known_locked(job_key):
                return "deduplicated"
            if len(self._pending) + len(self._inflight) < self._maxsize:
                self._enqueue_locked(job_key, fn)
                return "queued"
            if len(self._deferred) < self._maxsize:
                self._deferred.append((job_key, fn))
                _record_rejected("deferred")
                logger.warning(
                    "media OCR pool full (%d active) -- job %s deferred (backlog=%d)",
                    len(self._pending) + len(self._inflight),
                    job_key,
                    len(self._deferred),
                )
                return "deferred_queue_full"
        _record_rejected("dropped")
        logger.error("media OCR pool and deferred backlog both full -- dropped %s", job_key)
        return "dropped"

    def _is_known_locked(self, job_key: str) -> bool:
        return (
            job_key in self._pending
            or job_key in self._inflight
            or any(key == job_key for key, _ in self._deferred)
        )

    def _enqueue_locked(self, job_key: str, fn: Callable[[], None]) -> None:
        self._pending[job_key] = time.monotonic()
        self._ensure_executor().submit(self._run, job_key, fn)

    def _run(self, job_key: str, fn: Callable[[], None]) -> None:
        with self._lock:
            self._pending.pop(job_key, None)
            self._inflight.add(job_key)
        started = time.perf_counter()
        try:
            fn()
        except Exception as exc:  # pragma: no cover - defensive; job owns its logging
            logger.debug("media OCR job %s failed: %s", job_key, exc)
        finally:
            _observe_duration(time.perf_counter() - started)
            with self._lock:
                self._inflight.discard(job_key)
                self._drain_one_deferred_locked()

    def _drain_one_deferred_locked(self) -> None:
        while self._deferred and len(self._pending) + len(self._inflight) < self._maxsize:
            job_key, fn = self._deferred.popleft()
            if job_key in self._pending or job_key in self._inflight:
                continue
            self._enqueue_locked(job_key, fn)
            return

    def stats(self) -> dict[str, float]:
        with self._lock:
            now = time.monotonic()
            oldest = min(self._pending.values(), default=now)
            return {
                "depth": float(len(self._pending) + len(self._inflight)),
                "deferred": float(len(self._deferred)),
                "oldest_job_seconds": now - oldest,
            }

    def reset(self) -> None:
        """Test-only: drop backlog and rebuild the pool."""
        with self._lock:
            executor, self._executor = self._executor, None
            self._pending.clear()
            self._inflight.clear()
            self._deferred.clear()
        if executor is not None:
            executor.shutdown(wait=False, cancel_futures=True)


def _record_rejected(reason: str) -> None:
    try:
        from core.observability import OCR_QUEUE_REJECTED

        OCR_QUEUE_REJECTED.labels(reason).inc()
    except Exception:  # pragma: no cover - metrics must never break ingestion
        pass


def _observe_duration(seconds: float) -> None:
    try:
        from core.observability import OCR_JOB_DURATION

        OCR_JOB_DURATION.observe(max(0.0, seconds))
    except Exception:  # pragma: no cover
        pass


media_ocr_queue = MediaOcrQueue(MEDIA_OCR_WORKERS, MEDIA_OCR_QUEUE_MAXSIZE)
