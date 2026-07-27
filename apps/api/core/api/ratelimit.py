# SPDX-License-Identifier: AGPL-3.0-or-later
"""Lightweight in-memory rate limiting for mutating endpoints.

No external dependencies (no Redis required): a sliding-window counter per
client IP, plus a global semaphore capping concurrent drift computations.
Suitable for the single-process pilot deployment; swap for a Redis-backed
limiter if the API is ever scaled horizontally.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

# ── Per-IP sliding window ──────────────────────────────────────────────────────
_WINDOW_S = 60.0
_hits: dict[str, deque[float]] = defaultdict(deque)
_hits_lock = threading.Lock()
_MAX_TRACKED_IPS = 10_000  # hard memory bound


def _client_ip(request: Request) -> str:
    # Behind the production reverse proxy the real client is in x-forwarded-for.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(request: Request, *, max_per_minute: int, scope: str) -> None:
    """Raise 429 if this client exceeded max_per_minute calls in the window.

    `scope` separates buckets so e.g. alert and intel limits are independent.
    """
    key = f"{scope}:{_client_ip(request)}"
    now = time.monotonic()
    with _hits_lock:
        if len(_hits) > _MAX_TRACKED_IPS:
            _hits.clear()  # pathological flood from many IPs — reset rather than OOM
        window = _hits[key]
        while window and (now - window[0]) > _WINDOW_S:
            window.popleft()
        if len(window) >= max_per_minute:
            retry_in = int(_WINDOW_S - (now - window[0])) + 1
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded ({max_per_minute}/min). Retry in {retry_in}s.",
                headers={"Retry-After": str(retry_in)},
            )
        window.append(now)


# ── Concurrent drift cap ───────────────────────────────────────────────────────
# Each SAR alert spawns a real OpenDrift simulation thread. Cap how many run
# at once so a burst of requests cannot exhaust CPU/RAM on the pilot VM.
MAX_CONCURRENT_DRIFTS = 4
_drift_slots = threading.BoundedSemaphore(MAX_CONCURRENT_DRIFTS)


def acquire_drift_slot() -> bool:
    """Non-blocking. Returns False when all drift slots are busy."""
    return _drift_slots.acquire(blocking=False)


def release_drift_slot() -> None:
    try:
        _drift_slots.release()
    except ValueError:  # over-release guard
        pass
