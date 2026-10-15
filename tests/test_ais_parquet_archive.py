# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read/restore and corruption tests for non-destructive AIS Parquet archives."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("pyarrow")

from core.archive import ais_parquet as archive


def _row(id: int = 101, *, source="aisstream", ts=None):
    observed = ts or datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
    return {
        "id": id, "mmsi": "123456789", "ts": observed,
        "received_at": observed + timedelta(seconds=2),
        "lat": 35.123456789, "lon": 14.987654321, "sog": 12.5,
        "cog": None, "heading": 89.0, "nav_status": None,
        "source": source,
    }


@pytest.fixture
def fake_r2(monkeypatch):
    from core.config import config
    from core import object_store

    monkeypatch.setattr(config, "OBJECT_STORAGE_ENDPOINT", "account.r2.cloudflarestorage.com")
    monkeypatch.setattr(config, "OBJECT_STORAGE_ACCESS_KEY", "test-access")
    monkeypatch.setattr(config, "OBJECT_STORAGE_SECRET_KEY", "test-secret")
    monkeypatch.setattr(config, "OBJECT_STORAGE_BUCKET", "seacommons")
    monkeypatch.setattr(config, "OBJECT_STORAGE_SECURE", True)

    objects = {}
    writes = []

    def put(key, data, mime):
        objects[key] = bytes(data)
        writes.append((key, mime))

    monkeypatch.setattr(object_store, "put", put)
    monkeypatch.setattr(object_store, "get", lambda key: objects[key])
    return objects, writes


def test_pack_roundtrip_preserves_all_fields_nulls_and_provenance():
    pkg = archive.build_archive([
        _row(103, source="volunteer"), _row(101),
        _row(102, source="aisstream"),
    ])
    assert pkg.row_count == 3
    assert pkg.object_key.startswith("cold/ais-tracks/v2/2026/10/15/")
    assert pkg.object_key.endswith(".parquet")
    manifest = json.loads(pkg.manifest_bytes)
    assert manifest["id_min"] == 101
    assert manifest["id_max"] == 103
    assert manifest["source_counts"] == {"aisstream": 2, "volunteer": 1}
    assert manifest["parquet_sha256"] == hashlib.sha256(pkg.parquet_bytes).hexdigest()
    restored = archive._decode(pkg.parquet_bytes)
    assert restored == [_row(101), _row(102), _row(103, source="volunteer")]
    assert restored[0]["cog"] is None
    assert restored[0]["nav_status"] is None


def test_publish_and_restore_check_hashes_without_touching_postgres(fake_r2):
    objects, writes = fake_r2
    pkg = archive.build_archive([_row(202), _row(201)])
    info = archive.publish_verified_archive(pkg)
    assert info["verified"] is True
    assert info["postgres_rows_deleted"] == 0
    assert len(writes) == 2
    assert archive.restore_verified_archive(pkg.manifest_key) == [_row(201), _row(202)]


def test_corrupt_r2_object_is_detected_before_manifest_write(fake_r2, monkeypatch):
    from core import object_store
    objects, writes = fake_r2
    pkg = archive.build_archive([_row(301)])
    original = object_store.put

    def corrupt_put(key, data, mime):
        original(key, b"broken" if key.endswith(".parquet") else data, mime)

    monkeypatch.setattr(object_store, "put", corrupt_put)
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        archive.publish_verified_archive(pkg)
    assert len(writes) == 1
    assert not any(key.endswith(".manifest.json") for key in objects)


def test_restore_detects_corruption(fake_r2):
    objects, _ = fake_r2
    pkg = archive.build_archive([_row(401)])
    archive.publish_verified_archive(pkg)
    objects[pkg.object_key] = b"tampered"
    with pytest.raises(ValueError, match="checksum mismatch"):
        archive.restore_verified_archive(pkg.manifest_key)


def test_rejects_duplicate_ids_and_cross_day_batch():
    with pytest.raises(ValueError, match="duplicate AIS row"):
        archive.build_archive([_row(501), _row(501)])
    with pytest.raises(ValueError, match="one UTC day"):
        archive.build_archive([
            _row(501),
            _row(502, ts=datetime(2026, 10, 16, 0, 1, tzinfo=timezone.utc)),
        ])


def test_rejects_missing_and_extra_field():
    missing = _row()
    del missing["received_at"]
    with pytest.raises(ValueError, match="schema mismatch"):
        archive.build_archive([missing])
    extra = _row()
    extra["private"] = "must not enter archive"
    with pytest.raises(ValueError, match="schema mismatch"):
        archive.build_archive([extra])


def test_insecure_store_and_missing_credentials_fail_closed(fake_r2, monkeypatch):
    from core.config import config
    from core import object_store
    monkeypatch.setattr(
        object_store, "put",
        lambda *_: pytest.fail("unexpected unauthorized storage write"),
    )
    pkg = archive.build_archive([_row(601)])
    monkeypatch.setattr(config, "OBJECT_STORAGE_SECURE", False)
    with pytest.raises(RuntimeError, match="HTTPS"):
        archive.publish_verified_archive(pkg)
    monkeypatch.setattr(config, "OBJECT_STORAGE_SECURE", True)
    monkeypatch.setattr(config, "OBJECT_STORAGE_SECRET_KEY", "")
    with pytest.raises(RuntimeError, match="refusing filesystem fallback"):
        archive.publish_verified_archive(pkg)


def test_pack_never_contacts_storage(fake_r2, monkeypatch):
    from core import object_store
    monkeypatch.setattr(
        object_store, "put",
        lambda *_: pytest.fail("pack triggered a storage write"),
    )
    pkg = archive.build_archive([_row(701)])
    assert pkg.row_count == 1


def test_manifest_path_validation(fake_r2):
    with pytest.raises(ValueError, match="manifest path"):
        archive.restore_verified_archive("../rogue.json")
