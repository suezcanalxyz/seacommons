# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read-only R2 backup verification regressions (no credentials or network)."""
import hashlib
from types import SimpleNamespace

import pytest

from scripts.verify_r2_pg_backup_manifest import validate_manifest, verify_objects


def item(payload=b"safe-backup"):
    return {"key": "postgresql-backups/backup.dump", "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(), "verified": True}


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.closed = False
        self.released = False

    def stream(self, amt):
        yield self.payload[:2]
        yield self.payload[2:]

    def close(self):
        self.closed = True

    def release_conn(self):
        self.released = True


def test_manifest_rejects_duplicate_keys_and_invalid_sizes():
    with pytest.raises(ValueError, match="duplicate"):
        validate_manifest([item(), item()])
    for bad in [0, -1, True, "12"]:
        entry = item()
        entry["bytes"] = bad
        with pytest.raises(ValueError, match="size"):
            validate_manifest([entry])


def test_manifest_rejects_traversal_and_invalid_hash():
    entry = item()
    entry["key"] = "postgresql-backups/../private"
    with pytest.raises(ValueError, match="key"):
        validate_manifest([entry])
    entry = item()
    entry["sha256"] = "not-a-digest"
    with pytest.raises(ValueError, match="SHA-256"):
        validate_manifest([entry])


def test_metadata_check_is_not_sha256_verification():
    results = verify_objects(validate_manifest([item()]), stat=lambda _: SimpleNamespace(size=11))
    assert results[0]["status"] == "metadata_verified"


def test_mismatched_size_is_failure_even_if_manifest_claims_verified():
    results = verify_objects(validate_manifest([item()]), stat=lambda _: SimpleNamespace(size=5))
    assert results[0]["status"] == "failed"
    assert "size mismatch" in results[0]["error"]


def test_deep_verification_streams_hash_and_closes_response():
    response = FakeResponse(b"safe-backup")
    results = verify_objects(validate_manifest([item()]),
                             stat=lambda _: SimpleNamespace(size=11),
                             stream=lambda _: response)
    assert results[0]["status"] == "sha256_verified"
    assert response.closed and response.released


def test_deep_verification_detects_corruption_and_closes_response():
    response = FakeResponse(b"bad-content")
    results = verify_objects(validate_manifest([item()]),
                             stat=lambda _: SimpleNamespace(size=11),
                             stream=lambda _: response)
    assert results[0]["status"] == "failed"
    assert "SHA-256 mismatch" in results[0]["error"]
    assert response.closed and response.released
