# SPDX-License-Identifier: AGPL-3.0-or-later
"""core.live.mode_policy -- one canonical Live-mode decision (docs/prompt.md PHASE 5)."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from core.intel.store import IntelEvent, intel_store
from core.live import mode_policy
from core.live.feed import public_signal_collection
from core.live_edge_publisher import public_event_from_row


def _event(**meta):
    return IntelEvent(
        id="mode-x",
        type="distress",
        severity="medium",
        lat=35.0,
        lon=18.0,
        title="t",
        source="SeaCommons MDA",
        timestamp_utc="2026-08-30T00:00:00+00:00",
        metadata=meta,
    )


def test_mode_for_event_is_a_positive_decision():
    assert mode_policy.mode_for_event(_event(maritime_domain="sar")) == "humanitarian"
    assert mode_policy.mode_for_event(_event(maritime_domain="piracy")) == "security"
    assert mode_policy.mode_for_event(_event(maritime_domain="sanctions")) == "security"
    assert mode_policy.mode_for_event(_event(maritime_domain="environmental")) is None
    # safety is humanitarian *context*, never security
    assert mode_policy.mode_for_event(_event(maritime_domain="safety")) == "humanitarian"


def test_safety_context_flag():
    assert mode_policy.is_safety_context(_event(maritime_domain="safety")) is True
    assert mode_policy.is_safety_context(_event(maritime_domain="sar")) is False


def test_eligible_for_mode():
    e = _event(maritime_domain="safety")
    assert mode_policy.eligible_for_mode(e, "humanitarian") is True
    assert mode_policy.eligible_for_mode(e, "security") is False
    assert mode_policy.eligible_for_mode(_event(maritime_domain="sanctions"), "humanitarian") is False


def _cleanup(prefix):
    with intel_store._lock:
        intel_store._events = type(intel_store._events)(
            (e for e in intel_store._events if not e.id.startswith(prefix)),
            maxlen=intel_store._events.maxlen,
        )


def test_safety_context_reaches_humanitarian_live_as_non_distress():
    event = IntelEvent(
        id="modepolicy-safety-1",
        type="distress",
        severity="medium",
        lat=34.5,
        lon=13.0,
        title="Vessel aground — AIS reported",
        source="SeaCommons MDA",
        timestamp_utc="2026-08-30T00:00:00+00:00",
        metadata={
            "maritime_domain": "safety",
            "publication_status": "published",
            "is_distress": False,
            "report_kind": "news",
        },
    )
    assert intel_store.add(event) is True
    try:
        hum = public_signal_collection(mode="humanitarian", days=60)
        feats = {str(f["properties"]["id"]): f for f in hum["features"]}
        assert "intel:modepolicy-safety-1" in feats
        props = feats["intel:modepolicy-safety-1"]["properties"]
        assert props.get("safety_context") is True
        assert props.get("kind") == "context"
        # never in the security feed
        sec_ids = {
            str(f["properties"]["id"])
            for f in public_signal_collection(mode="security", days=60)["features"]
        }
        assert "intel:modepolicy-safety-1" not in sec_ids
    finally:
        _cleanup("modepolicy-")


def test_vm_and_edge_agree_on_humanitarian_eligibility():
    now_str = "2026-08-30T12:00:00+00:00"
    now = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)
    rows = [
        {"maritime_domain": "sar", "expect": True},
        {"maritime_domain": "safety", "expect": True},
        {"maritime_domain": "piracy", "expect": False},
        {"maritime_domain": "sanctions", "expect": False},
        {"maritime_domain": "environmental", "expect": False},
    ]
    for i, spec in enumerate(rows):
        meta = {
            "maritime_domain": spec["maritime_domain"],
            "publication_status": "published",
            "source_policy": "operator_published",
            "is_distress": True,
        }
        row = SimpleNamespace(
            id=f"parity-{i}", type="distress", severity="medium", lat=35.0, lon=18.0,
            title="t", text="Public source report of a boat in distress",
            url="https://example.test/r", source="alarm_phone", linked_mmsi="",
            timestamp_utc=now_str, meta=meta,
        )
        event = IntelEvent(
            id=row.id, type=row.type, severity="medium", lat=row.lat, lon=row.lon,
            title=row.title, text=row.text, url=row.url, source=row.source,
            timestamp_utc=now_str, metadata=meta,
        )
        vm_ok = mode_policy.eligible_for_mode(event, "humanitarian")
        edge = public_event_from_row(row, "node", now=now, same_source=[])
        edge_ok = edge is not None
        assert vm_ok == spec["expect"], spec
        # the edge must never publish what the VM policy excludes
        if not vm_ok:
            assert not edge_ok, spec
