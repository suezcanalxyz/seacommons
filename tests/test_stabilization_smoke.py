# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/fixes.md Phase 6 / section 7 -- end-to-end stabilization smoke corpus.

One place that walks the representative scenarios from source through
classification, drift eligibility, projection and the public feed, so a
regression in any single fix surfaces here. Not a substitute for the
per-fix regression tests -- a backstop that they still compose.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.intel.drift_service import is_auto_drift_eligible
from core.intel.location_evidence import evidence_from_ocr_method, metadata_quality
from core.intel.public_policy import compartment_for_domain
from core.intel.store import IntelEvent, intel_store
from core.live.feed import public_signal_collection


def _recent(hours: float = 2.0) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def _distress(_id: str, text: str, **meta) -> IntelEvent:
    base = {
        "is_distress": True,
        "source_policy": "operator_published",
        "publication_status": "published",
        "tracked_account": "alarm_phone",
    }
    base.update(meta)
    return IntelEvent(
        id=_id, type="twitter", severity="critical",
        title=text[:80], text=text, source="Alarm Phone",
        timestamp_utc=_recent(), metadata=base,
    )


@pytest.fixture
def clean_store():
    yield
    with intel_store._lock:
        intel_store._events = type(intel_store._events)(
            (e for e in intel_store._events if not e.id.startswith("smoke-")),
            maxlen=intel_store._events.maxlen,
        )


# 1-2. verified in-text coordinate (DMM / DMS parsed to decimal) -> drift eligible
def test_verified_text_coordinate_is_drift_eligible():
    event = _distress(
        "smoke-1", "45 people in distress 34 16.292N 011 56.538E",
        lat=34.2715, lon=11.9423,
        coordinate_source="post_text", coordinate_review_status="not_required",
        location_uncertainty_m=250,
    )
    ok, reason = is_auto_drift_eligible(event)
    assert ok, reason


# 3. pin-only screenshot -> approximate position, drift eligible at sea (policy /2)
def test_pin_only_screenshot_at_sea_is_drift_eligible():
    ev = evidence_from_ocr_method("pin_landmark", 34.2, 12.0)
    event = IntelEvent(
        id="smoke-3", type="twitter", severity="critical",
        title="distress south of Crete", text="distress south of Crete",
        source="Alarm Phone", timestamp_utc=_recent(), lat=34.2, lon=12.0,
        metadata={"is_distress": True, "tracked_account": "alarm_phone", **ev.as_metadata()},
    )
    ok, reason = is_auto_drift_eligible(event)
    assert ok is True, reason


# 4. OCR disagreement -> disputed, persisted, zero drift
def test_ocr_disagreement_is_persisted_but_never_drifts():
    ev = evidence_from_ocr_method("easyocr_text_disputed", 34.2, 12.0)
    event = _distress("smoke-4", "distress", lat=34.2, lon=12.0, **ev.as_metadata())
    ok, reason = is_auto_drift_eligible(event)
    assert ok is False and "disputed" in reason
    # the position is still stored -- lower quality than a verified read, never above it
    assert metadata_quality(ev.as_metadata()) < metadata_quality(
        {"coordinate_source": "post_text", "coordinate_review_status": "not_required"}
    )


# 5. region-only text -> no drift
def test_region_only_text_is_not_drift_eligible():
    event = _distress(
        "smoke-5", "boat in distress somewhere in the Central Mediterranean",
        lat=35.0, lon=15.0, coordinate_source="region_area", location_uncertainty_m=60000,
    )
    assert is_auto_drift_eligible(event)[0] is False


# 6-7. a resolution reply removes the case from the live window
@pytest.mark.parametrize("note", [
    "The people have been found and taken to a reception centre on Farmakonisi.",
    "We received news that the people arrived in the reception camp on Lesvos.",
])
def test_resolution_reply_leaves_the_live_window(note):
    from core.intel import lifecycle

    event = _distress(
        "smoke-6", "40 people missing in the Aegean",
        thread_reposts=[{"tweet_id": "r", "posted_at": _recent(1), "kind": "reply", "note": note}],
    )
    assert lifecycle.distress_lifecycle(event, now=datetime.now(timezone.utc), same_source=[]) == "resolved"


# 8. Evros land humanitarian -> land case type, never a maritime drift
def test_evros_land_case_is_land_typed_and_never_drifts():
    from core.intel.humanitarian import _case_type

    assert _case_type("Group located in the forest near Evros, taken to a reception centre",
                      distress=False, resolved=False) == "land_humanitarian"
    event = _distress("smoke-8", "land border case near Evros", lat=41.5, lon=26.5,
                      sea_land_class="LAND", coordinate_source="post_text",
                      coordinate_review_status="not_required")
    assert is_auto_drift_eligible(event)[0] is False


# 10. advocacy / memorial post is not an active distress
def test_advocacy_post_is_not_operational():
    from core.intel.humanitarian import _case_type

    assert _case_type("We remember the victims of this shipwreck, one year on.",
                      distress=False, resolved=False) == "advocacy"


# 15. piracy / security event -> security compartment, never humanitarian, never drift
def test_piracy_event_is_security_and_never_drifts():
    assert compartment_for_domain("piracy") == "security"
    event = IntelEvent(
        id="smoke-15", type="piracy_incident", severity="high", lat=12.0, lon=45.0,
        title="Boarding reported", source="SeaCommons MDA",
        timestamp_utc=_recent(),
        metadata={"source_policy": "official_api", "publication_status": "published"},
    )
    assert is_auto_drift_eligible(event)[0] is False


# 11 + 16. non-Alarm-Phone humanitarian source survives; durable events reach
# the feed even when the in-memory deque never held them.
def test_non_alarm_phone_humanitarian_source_reaches_the_feed(clean_store):
    event = IntelEvent(
        id="smoke-11", type="twitter", severity="high", lat=34.9, lon=13.1,
        title="Sea-Watch sighting", text="Sighted an overcrowded boat in distress",
        source="Sea-Watch", timestamp_utc=_recent(),
        metadata={"is_distress": True, "source_policy": "operator_published",
                  "publication_status": "published", "tracked_account": "seawatch"},
    )
    assert intel_store.add(event) is True
    feed = public_signal_collection(mode="humanitarian", days=30)
    ids = {str(f["properties"]["id"]) for f in feed["features"]}
    assert "intel:smoke-11" in ids


# 12-14. the civil SAR fleet groups civil vs state and keeps offline vessels
def test_fleet_geojson_separates_civil_from_state_and_keeps_offline():
    from core.intel.ngo_registry import ngo_vessel_geojson

    fc = ngo_vessel_geojson()
    ops = {str(f["properties"].get("operator_type")) for f in fc["features"]}
    assert "civil_ngo" in ops
    # offline registered vessels are present with geometry:null
    assert any(f["geometry"] is None for f in fc["features"])
    assert fc["meta"]["state_authority_registered"] >= 0
