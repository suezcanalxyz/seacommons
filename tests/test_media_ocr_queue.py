# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/fixes.md F-02 / Phase 0.2 -- media OCR work is bounded.

A media burst must not spawn one unbounded waiting thread per event. The
pool caps concurrent + pending jobs; overflow is a recoverable
`deferred_queue_full` state that drains as capacity frees, never silent loss.
"""
from __future__ import annotations

import threading
import time

from core.intel.media_ocr_queue import MediaOcrQueue


def _blocking_job(release: threading.Event, ran: list) -> None:
    ran.append(time.monotonic())
    release.wait(timeout=5)


def test_duplicate_job_key_is_deduplicated():
    q = MediaOcrQueue(workers=1, maxsize=4)
    release = threading.Event()
    ran: list = []
    try:
        assert q.submit("evt-1", lambda: _blocking_job(release, ran)) == "queued"
        assert q.submit("evt-1", lambda: ran.append("dup")) == "deduplicated"
    finally:
        release.set()
        q.reset()


def test_backlog_is_bounded_then_deferred_then_dropped():
    q = MediaOcrQueue(workers=1, maxsize=2)
    release = threading.Event()
    ran: list = []
    try:
        # 2 fill the pool+pending, 2 more fill the deferred backlog, 1 dropped.
        assert q.submit("a", lambda: _blocking_job(release, ran)) == "queued"
        assert q.submit("b", lambda: _blocking_job(release, ran)) == "queued"
        assert q.submit("c", lambda: ran.append("c")) == "deferred_queue_full"
        assert q.submit("d", lambda: ran.append("d")) == "deferred_queue_full"
        assert q.submit("e", lambda: ran.append("e")) == "dropped"
    finally:
        release.set()
        q.reset()


def test_deferred_jobs_drain_as_capacity_frees():
    q = MediaOcrQueue(workers=1, maxsize=1)
    gate_a = threading.Event()
    done: list = []

    def job(name: str, gate: threading.Event | None) -> None:
        if gate is not None:
            gate.wait(timeout=5)
        done.append(name)

    try:
        assert q.submit("a", lambda: job("a", gate_a)) == "queued"
        assert q.submit("b", lambda: job("b", None)) == "deferred_queue_full"
        assert "b" not in done
        gate_a.set()
        deadline = time.monotonic() + 5
        while "b" not in done and time.monotonic() < deadline:
            time.sleep(0.02)
        assert done == ["a", "b"]
    finally:
        gate_a.set()
        q.reset()
