# SPDX-License-Identifier: AGPL-3.0-or-later
"""Contract tests for core.intel.public_policy.

These two rules -- explicit privacy is absolute, and a blocked source/
transport is never exposed -- must hold identically on both public Live
paths (the VM's core.live.projection and the edge's
core.live_edge_publisher). This file exists so a future edit to one path
that silently drifts from the other is caught here instead of in
production, per docs/ENGINEERING_AUDIT.md's P1 finding on duplicated
public/private policy.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from core.intel.public_policy import (
    BLOCKED_SOURCE_POLICIES,
    is_blocked_source,
    is_explicitly_private,
)


def test_explicitly_private_overrides_everything_else() -> None:
    assert is_explicitly_private({"publication_status": "private"}) is True
    assert is_explicitly_private({"publication_status": "PRIVATE"}) is True
    assert is_explicitly_private({"publication_status": "published"}) is False
    assert is_explicitly_private({}) is False


def test_blocked_source_policy_and_transport_are_both_checked() -> None:
    for policy in BLOCKED_SOURCE_POLICIES:
        assert is_blocked_source({"source_policy": policy}) is True
    assert is_blocked_source({"via": "nitter"}) is True
    assert is_blocked_source({"scrape_source": "twscrape-mirror"}) is True
    assert is_blocked_source({"source_policy": "official_api"}) is False
    assert is_blocked_source({}) is False


def test_vm_and_edge_paths_agree_on_the_two_privacy_absolute_rules() -> None:
    """Same metadata, same verdict, on both public Live paths.

    Only exercises the two rules public_policy actually unifies (privacy
    is absolute; blocked source is absolute) -- NOT full public/private
    eligibility, which the two paths intentionally keep separate (see
    core/intel/public_policy.py's module docstring).
    """
    from core.intel.store import IntelEvent
    from core.live.projection import _public_intel_feature
    from core.live_edge_publisher import public_event_from_row

    now = datetime(2026, 8, 2, 12, 30, tzinfo=timezone.utc)

    cases = [
        {
            "publication_status": "private",
            "source_policy": "official_api",
            "is_distress": True,
        },
        {"source_policy": "nitter", "is_distress": True},
        {"via": "twscrape-mirror", "is_distress": True},
    ]
    for metadata in cases:
        vm_event = IntelEvent(
            id="parity-01",
            type="distress",
            severity="high",
            lat=35.1,
            lon=14.2,
            title="Parity check",
            source="alarm_phone",
            metadata=dict(metadata),
        )
        edge_row = SimpleNamespace(
            id="parity-01",
            type="distress",
            severity="high",
            lat=35.1,
            lon=14.2,
            title="Parity check",
            text="",
            url="",
            source="alarm_phone",
            linked_mmsi="",
            timestamp_utc="2026-08-02T12:00:00+00:00",
            meta=dict(metadata),
        )
        assert _public_intel_feature(vm_event) is None, metadata
        assert (
            public_event_from_row(edge_row, "node", now=now, same_source=[]) is None
        ), metadata
