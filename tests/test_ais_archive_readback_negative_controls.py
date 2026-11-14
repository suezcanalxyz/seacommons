"""Synthetic negative controls for the AIS v1 cold-archive readback contract.

These tests do NOT certify PostgreSQL/R2 end-to-end restoration.
They exercise gzip, JSON and row-equivalence semantics with no external data.
"""
import gzip
import io
import json
import unittest


def validate_archive(raw: bytes, expected_rows: list[dict]) -> None:
    expected_plain = json.dumps({"schema": "vessel_tracks_v1", "rows": expected_rows}, sort_keys=True, separators=(",", ":")).encode("utf-8")
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
        decoded = stream.read(len(expected_plain) + 1)
    if len(decoded) != len(expected_plain):
        raise ValueError("AIS cold archive decompressed size mismatch")
    restored = json.loads(decoded)
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
        return gzip.compress(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"), mtime=0)

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
            expected = json.dumps({"schema": "vessel_tracks_v1", "rows": self.rows}, sort_keys=True, separators=(",", ":")).encode("utf-8")
            malformed = b"{" + b" " * (len(expected) - 1)
            validate_archive(gzip.compress(malformed, mtime=0), self.rows)

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

    def test_oversized_valid_gzip_rejected_before_json_parse(self):
        payload = {"schema": "vessel_tracks_v1", "rows": self.rows, "padding": "x" * 100_000}
        with self.assertRaisesRegex(ValueError, "decompressed size mismatch"):
            validate_archive(self.archive(payload), self.rows)

    def test_missing_row_rejected(self):
        with self.assertRaises(ValueError):
            validate_archive(self.archive({"schema": "vessel_tracks_v1", "rows": []}), self.rows)

    def test_non_object_payload(self):
        with self.assertRaises(ValueError):
            validate_archive(self.archive(self.rows), self.rows)


if __name__ == "__main__":
    unittest.main()
