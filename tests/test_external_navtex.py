import unittest

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
