"""Synthetic negative controls for the AIS v1 cold-archive readback contract.

These tests do NOT certify PostgreSQL/R2 end-to-end restoration.
They exercise gzip, JSON and row-equivalence semantics with no external data.
"""
import gzip
import json
import unittest


def validate_archive(raw: bytes, expected_rows: list[dict]) -> None:
    restored = json.loads(gzip.decompress(raw))
    if (
        not isinstance(restored, dict)
        or restored.get("schema") != "vessel_tracks_v1"
        or restored.get("rows") != expected_rows
    ):
        raise ValueError("AIS cold archive row equivalence failed")


class ArchiveReadbackNegativeControls(unittest.TestCase):
    def setUp(self):
        self.rows = [{"id": 1, "mmsi": "123456789", "ts": "2026-11-01T00:00:00Z"}]

    def archive(self, payload):
        return gzip.compress(json.dumps(payload).encode("utf-8"), mtime=0)

    def test_valid_archive(self):
        validate_archive(self.archive({"schema": "vessel_tracks_v1", "rows": self.rows}), self.rows)

    def test_invalid_gzip(self):
        with self.assertRaises((OSError, EOFError)):
            validate_archive(b"not-gzip", self.rows)

    def test_truncated_gzip(self):
        raw = self.archive({"schema": "vessel_tracks_v1", "rows": self.rows})
        with self.assertRaises((EOFError, OSError)):
            validate_archive(raw[:-5], self.rows)

    def test_invalid_json(self):
        with self.assertRaises(json.JSONDecodeError):
            validate_archive(gzip.compress(b"{invalid", mtime=0), self.rows)

    def test_wrong_schema(self):
        with self.assertRaises(ValueError):
            validate_archive(self.archive({"schema": "vessel_tracks_v2", "rows": self.rows}), self.rows)

    def test_row_mutation(self):
        altered = [{**self.rows[0], "mmsi": "987654321"}]
        with self.assertRaises(ValueError):
            validate_archive(self.archive({"schema": "vessel_tracks_v1", "rows": altered}), self.rows)

    def test_row_reordering(self):
        rows = self.rows + [{"id": 2, "mmsi": "222222222"}]
        with self.assertRaises(ValueError):
            validate_archive(self.archive({"schema": "vessel_tracks_v1", "rows": list(reversed(rows))}), rows)

    def test_non_object_payload(self):
        with self.assertRaises(ValueError):
            validate_archive(self.archive(self.rows), self.rows)


if __name__ == "__main__":
    unittest.main()
