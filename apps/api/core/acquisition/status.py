# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

StatusProvider = Callable[[], dict[str, Any]]

_lock = threading.Lock()
_providers: dict[str, tuple[str, StatusProvider]] = {}


def register_acquisition_status(family: str, label: str, provider: StatusProvider) -> None:
    normalized = str(family or "").strip().lower()
    if not normalized:
        raise ValueError("family is required")
    public_label = " ".join(str(label or "").split()).strip()
    if not public_label:
        raise ValueError("label is required")
    with _lock:
        _providers[normalized] = (public_label[:96], provider)


def acquisition_status_sources() -> list[dict[str, Any]]:
    with _lock:
        items = tuple(sorted(_providers.items()))
    result: list[dict[str, Any]] = []
    for family, (label, provider) in items:
        try:
            detail = dict(provider() or {})
        except Exception:
            detail = {"state": "offline"}
        state = str(detail.pop("state", "offline") or "offline").strip().lower()
        if state not in {"live", "degraded", "offline", "disabled"}:
            state = "degraded"
        result.append({"family": family, "label": label, "state": state, **detail})
    return result


def _reset_acquisition_status_for_tests() -> None:
    with _lock:
        _providers.clear()
