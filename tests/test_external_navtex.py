import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core.radio import external_navtex as navtex
from core.radio.external_navtex import (
    fetch_navtex_messages, normalize_navtex_message,
)


class TestExternalNavtex(unittest.TestCase):
    def test_secondary_evidence_not_radio(self):
        row = normalize_navtex_message({
            "id": 42,
            "station": {"id": "test", "navarea": "III"},
            "text": "NAVIGATION WARNING",
            "positions": [[11.0, 35.0]],
        })
        self.assertEqual(row["source_class"], "secondary_maritime_safety_information")
        self.assertFalse(row["independent_rf_reception"])
        self.assertFalse(row["is_dsc_decode"])
        self.assertEqual(row["external_id"], "42")
        self.assertEqual(row["positions_unverified"], [[11.0, 35.0]])

    def test_missing_id(self):
        with self.assertRaises(ValueError):
            normalize_navtex_message({})

    def test_bounded_inputs(self):
        for value in ("../../", "", "MED", "XXII"):
            with self.assertRaises(ValueError):
                fetch_navtex_messages(navarea=value)
        with self.assertRaises(ValueError):
            fetch_navtex_messages(limit=201)

    def test_fetch_uses_governed_fixed_origin_client(self):
        response = SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"messages": [{"id": "nav-1"}]},
        )
        with patch.object(navtex, "FixedOriginClient") as client_type:
            client_type.return_value.request.return_value = response

            rows = fetch_navtex_messages(navarea="III", limit=1, timeout=4.0)

        client_type.assert_called_once_with((navtex.BASE,), timeout=4.0)
        requested_url = client_type.return_value.request.call_args.args[0]
        self.assertEqual(
            requested_url,
            "https://navtex.online/api/v1/messages?navarea=III&limit=1",
        )
        self.assertEqual(rows[0]["external_id"], "nav-1")
