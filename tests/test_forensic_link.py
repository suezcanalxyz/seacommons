# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import time

from core.intel.forensic_link import attach_forensic_packet
from core.intel.store import IntelEvent


def _wait_for(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_no_position_never_signs(monkeypatch):
    captured = []
    monkeypatch.setattr("core.forensic.logger.sign_and_store", lambda pkt: captured.append(pkt))
    event = IntelEvent(id="fx1", type="twitter", title="No position", source="alarm_phone")
    attach_forensic_packet(event)
    time.sleep(0.05)
    assert captured == []


def test_signs_with_position_and_never_leaks_private_text(monkeypatch):
    captured = []
    monkeypatch.setattr("core.forensic.logger.sign_and_store", lambda pkt: captured.append(pkt))
    event = IntelEvent(
        id="fx2",
        type="twitter",
        title="Boat in distress",
        text="private caller phone number and free-form message",
        source="alarm_phone",
        lat=35.5,
        lon=14.1,
        timestamp_utc="2026-08-05T12:00:00+00:00",
        metadata={
            "coordinate_source": "media_ocr_text",
            "tracked_account": "alarm_phone",
            "report_kind": "distress",
            "verification_status": "machine_extracted_unverified",
            "private_note": "must never appear in a signed/exported record",
        },
    )
    attach_forensic_packet(event)
    assert _wait_for(lambda: len(captured) == 1)

    packet = captured[0]
    assert packet.event_id == "fx2"
    assert packet.position == {"lat": 35.5, "lon": 14.1, "alt": 0, "source": "media_ocr_text"}
    assert "image_ocr" in packet.contributing_sensors
    assert "twitter:alarm_phone" in packet.contributing_sensors
    assert packet.confidence == 0.85
    assert "private_note" not in packet.sensor_data
    assert "text" not in packet.__dict__.get("sensor_data", {})


def test_signing_failure_never_raises(monkeypatch):
    def boom(pkt):
        raise RuntimeError("signing key unavailable")

    monkeypatch.setattr("core.forensic.logger.sign_and_store", boom)
    event = IntelEvent(id="fx3", type="twitter", title="x", source="alarm_phone", lat=35.0, lon=14.0)
    attach_forensic_packet(event)  # must not raise
    time.sleep(0.05)
