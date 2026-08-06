# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from datetime import timezone

import pytest

from core.vessels.aishub import AISHubClient, parse_response


_SAMPLE = [
    {"ERROR": False, "USERNAME": "demo", "FORMAT": "HUMAN", "RECORDS": 2},
    [
        {
            "MMSI": 244750034,
            "TIME": "2026-08-06 08:20:32 GMT",
            "LONGITUDE": 5.03812,
            "LATITUDE": 52.46015,
            "COG": 360,
            "SOG": 0,
            "HEADING": 511,
            "IMO": 0,
            "NAME": "CHATEAUROUX",
            "TYPE": 69,
            "DEST": "",
        },
        {
            "MMSI": 247123456,
            "TIME": "1786000000",
            "LONGITUDE": 14.45,
            "LATITUDE": 35.89,
            "COG": 123.4,
            "SOG": 8.2,
            "HEADING": 124,
            "IMO": 9876543,
            "NAME": "TEST SAR",
            "TYPE": 58,
            "DEST": "VALLETTA",
        },
    ],
]


def test_parse_human_readable_aishub_response() -> None:
    vessels = parse_response(_SAMPLE)

    assert len(vessels) == 2
    assert vessels[0]["mmsi"] == "244750034"
    assert vessels[0]["heading"] is None
    assert vessels[0]["last_seen"].tzinfo == timezone.utc
    assert vessels[1]["ship_name"] == "TEST SAR"
    assert vessels[1]["lat"] == pytest.approx(35.89)


def test_parse_rejects_bad_envelope() -> None:
    with pytest.raises(ValueError):
        parse_response({"records": []})


def test_poll_interval_never_violates_provider_minimum() -> None:
    client = AISHubClient("demo", poll_interval_s=1)
    assert client._poll_interval_s == 60


def test_poll_once_upserts_normalized_vessels() -> None:
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return _SAMPLE

    class HttpClient:
        def get(self, url, params):
            assert params["output"] == "json"
            assert params["format"] == 1
            return Response()

    class Registry:
        def __init__(self) -> None:
            self.rows = []

        def upsert(self, **kwargs) -> None:
            self.rows.append(kwargs)

    registry = Registry()
    client = AISHubClient("demo")
    count = client._poll_once(registry, HttpClient())

    assert count == 2
    assert len(registry.rows) == 2
    assert registry.rows[1]["mmsi"] == "247123456"
    assert client.messages_received == 2
