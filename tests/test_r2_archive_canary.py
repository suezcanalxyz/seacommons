# SPDX-License-Identifier: AGPL-3.0-or-later
"""Offline, hermetic regression tests for the manual R2 canary."""
from __future__ import annotations

import gzip
import json

import pytest

from scripts import r2_archive_canary as canary


def test_default_is_dry_run_and_never_contacts_storage(monkeypatch):
    monkeypatch.setattr(
        canary.object_store, "put",
        lambda *_: pytest.fail("dry-run performed an object write"),
    )
    monkeypatch.setattr(
        canary.object_store, "get",
        lambda *_: pytest.fail("dry-run performed an object read"),
    )
    assert canary.run() == {"status": "dry_run", "writes": 0, "deletes": 0}


def test_explicit_execution_requires_credentials(monkeypatch):
    for attr in (
        "OBJECT_STORAGE_ENDPOINT",
        "OBJECT_STORAGE_ACCESS_KEY",
        "OBJECT_STORAGE_SECRET_KEY",
    ):
        monkeypatch.setattr(canary.config, attr, "")
    monkeypatch.setattr(
        canary.object_store, "put",
        lambda *_: pytest.fail("unexpected local fallback"),
    )
    with pytest.raises(RuntimeError, match="refusing local fallback"):
        canary.run(execute=True)


def _configured(monkeypatch):
    monkeypatch.setattr(canary.config, "OBJECT_STORAGE_ENDPOINT", "test.r2.local")
    monkeypatch.setattr(canary.config, "OBJECT_STORAGE_ACCESS_KEY", "test-access")
    monkeypatch.setattr(canary.config, "OBJECT_STORAGE_SECRET_KEY", "test-secret")
    monkeypatch.setattr(canary.config, "OBJECT_STORAGE_BUCKET", "seacommons")


def test_execute_roundtrip_verifies_compressed_data_and_manifest(monkeypatch):
    _configured(monkeypatch)
    archive = {}

    def put(key, data, content_type):
        archive[key] = bytes(data)

    monkeypatch.setattr(canary.object_store, "put", put)
    monkeypatch.setattr(canary.object_store, "get", lambda key: archive[key])
    result = canary.run(execute=True)
    assert result["status"] == "verified"
    assert result["writes"] == 2
    assert result["deletes"] == 0
    body = json.loads(gzip.decompress(archive[result["object_key"]]))
    assert body["schema"] == "seacommons_ais_archive_canary_v1"
    assert len(body["sample"]) == 1
    manifest = json.loads(archive[result["manifest_key"]])
    assert manifest["compressed_sha256"] == result["compressed_sha256"]
    assert manifest["uncompressed_sha256"] == result["original_sha256"]


def test_archive_corruption_aborts_before_manifest_upload(monkeypatch):
    _configured(monkeypatch)
    archive = {}

    def put(key, data, content_type):
        archive[key] = bytes(data)

    monkeypatch.setattr(canary.object_store, "put", put)
    monkeypatch.setattr(canary.object_store, "get", lambda key: b"corrupt-data")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        canary.run(execute=True)
    assert len(archive) == 1
    assert next(iter(archive)).endswith(".json.gz")
