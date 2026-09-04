# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/fixes.md section 7 -- public Live stays responsive during an OCR burst.

F-02: before the bounded pool, every tweet carrying media spawned its own
daemon thread that then blocked on the Tesseract/EasyOCR lock. A media burst
piled up hundreds of waiting threads and their RAM, starving Uvicorn and the
Live feed.

This proves the replacement holds the line: a burst far larger than the pool
adds at most ``workers`` threads, every ``submit`` returns immediately instead
of blocking the caller, overflow is a recoverable state rather than silent
loss, and the public feed still answers while the pool is saturated.
"""
from __future__ import annotations

import threading
import time

from core.intel.media_ocr_queue import MediaOcrQueue, media_ocr_queue


def test_a_burst_far_larger_than_the_pool_adds_at_most_worker_threads():
    workers = 2
    q = MediaOcrQueue(workers=workers, maxsize=8)
    release = threading.Event()

    def blocking_job() -> None:
        release.wait(timeout=5)

    baseline = threading.active_count()
    outcomes: list[str] = []
    started = time.monotonic()
    try:
        for i in range(400):
            outcomes.append(q.submit(f"evt-{i}", blocking_job))
        elapsed = time.monotonic() - started

        # the caller is never blocked by a saturated pool
        assert elapsed < 1.0, f"400 submits took {elapsed:.2f}s -- submit is blocking"

        # thread count is bounded by the pool, not by the burst size
        grew_by = threading.active_count() - baseline
        assert grew_by <= workers + 1, f"burst spawned {grew_by} threads"

        # nothing is silently lost: every job is accounted for
        assert set(outcomes) <= {"queued", "deferred_queue_full", "dropped"}
        assert outcomes.count("queued") <= 8
        assert "deferred_queue_full" in outcomes and "dropped" in outcomes

        # the pool's own view stays bounded
        stats = q.stats()
        assert stats["depth"] <= 8
        assert stats["deferred"] <= 8
    finally:
        release.set()
        q.reset()


def test_public_feed_answers_while_the_ocr_pool_is_saturated():
    from core.intel.store import IntelEvent, intel_store
    from core.live.feed import public_signal_collection

    intel_store.add(IntelEvent(
        id="ocr-burst-feed-1",
        type="twitter",
        severity="critical",
        lat=34.9,
        lon=13.1,
        title="Alarm Phone: distress in the Central Med",
        text="boat in distress",
        source="Alarm Phone",
        metadata={
            "is_distress": True,
            "tracked_account": "alarm_phone",
            "source_policy": "operator_published",
            "publication_status": "published",
        },
    ))

    release = threading.Event()

    def blocking_job() -> None:
        release.wait(timeout=5)

    try:
        for i in range(200):
            media_ocr_queue.submit(f"burst-{i}", blocking_job)

        started = time.monotonic()
        collection = public_signal_collection(mode="humanitarian", days=7)
        elapsed = time.monotonic() - started

        assert elapsed < 3.0, f"feed took {elapsed:.2f}s during an OCR burst"
        ids = {str(f["properties"]["id"]) for f in collection["features"]}
        assert "intel:ocr-burst-feed-1" in ids
    finally:
        release.set()
        media_ocr_queue.reset()
        with intel_store._lock:
            intel_store._events = type(intel_store._events)(
                (e for e in intel_store._events if e.id != "ocr-burst-feed-1"),
                maxlen=intel_store._events.maxlen,
            )
