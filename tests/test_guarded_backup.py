"""Pre-deploy R2 backup resource and byte-integrity guards."""
import io
import importlib.util
from pathlib import Path

p = Path(__file__).resolve().parents[1] / 'scripts/backup_pg_to_r2_guarded.py'
spec = importlib.util.spec_from_file_location('guarded_backup', p)
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


def test_resource_guard_rejects_cpu_pressure():
    ok, reason = backup.resource_check(load1=1.0, cpu_psi_avg10=91.0, mem_available=5 * 1024**3, disk_available=14 * 1024**3, cpus=2)
    assert not ok and reason == 'cpu_pressure_high'


def test_resource_guard_rejects_low_disk():
    ok, reason = backup.resource_check(load1=1.0, cpu_psi_avg10=2.0, mem_available=5 * 1024**3, disk_available=2 * 1024**3, cpus=2)
    assert not ok and reason == 'disk_headroom_low'


def test_resource_guard_accepts_idle_host():
    assert backup.resource_check(load1=1.0, cpu_psi_avg10=3.0, mem_available=5 * 1024**3, disk_available=14 * 1024**3, cpus=2) == (True, 'ok')


def test_stream_hash_and_size_match_bytes():
    payload = b'PGDMP' + b'archive' * 1024
    stream = backup.HashingReader(io.BytesIO(payload))
    assert b''.join(iter(lambda: stream.read(91), b'')) == payload
    assert stream.count == len(payload)
    import hashlib
    assert stream.digest.hexdigest() == hashlib.sha256(payload).hexdigest()


def test_runtime_cpu_circuit_breaker_requires_sustained_pressure():
    assert not backup.sustained_cpu_pressure([78.0])
    assert not backup.sustained_cpu_pressure([78.0, 30.0])
    assert backup.sustained_cpu_pressure([32.0, 65.0, 66.0])
    assert not backup.sustained_cpu_pressure([65.0, 55.0])


def test_long_cpu_pressure_blocks_backup_after_short_quiet_period():
    kw = dict(load1=1.0, cpu_psi_avg10=2.0, mem_available=5 * 1024**3,
              disk_available=14 * 1024**3, cpus=2)
    assert backup.resource_check(**kw, cpu_psi_avg60=38.0, cpu_psi_avg300=20.0) == (False, "cpu_pressure_60s_high")
    assert backup.resource_check(**kw, cpu_psi_avg60=20.0, cpu_psi_avg300=67.0) == (False, "cpu_pressure_300s_high")
    assert backup.resource_check(**kw, cpu_psi_avg60=20.0, cpu_psi_avg300=25.0) == (True, "ok")


def test_full_backup_lock_prevents_overlapping_jobs(tmp_path):
    path = tmp_path / "backup.lock"
    first = backup.acquire_backup_lock(path)
    assert first is not None
    try:
        assert backup.acquire_backup_lock(path) is None
    finally:
        first.close()
    second = backup.acquire_backup_lock(path)
    assert second is not None
    second.close()


def test_runtime_headroom_guard_rejects_critical_ram_and_disk():
    gib = 1024**3
    assert backup.runtime_headroom_safe(mem_available=1 * gib, disk_available=14 * gib) == (False, "runtime_memory_headroom_low")
    assert backup.runtime_headroom_safe(mem_available=5 * gib, disk_available=3 * gib) == (False, "runtime_disk_headroom_low")
    assert backup.runtime_headroom_safe(mem_available=5 * gib, disk_available=14 * gib) == (True, "ok")


def test_partial_streams_never_land_in_trusted_full_prefix():
    pending, attestation = backup.backup_object_keys("20261101T120000Z")
    assert pending == "seacommons/backups/pending/pgdump-20261101T120000Z.dump"
    assert attestation == "seacommons/backups/byte-verified/pgdump-20261101T120000Z.json"
    assert "/full/" not in pending
    assert "/full/" not in attestation


def test_attestation_never_claims_restore_or_deploy_readiness():
    digest = "a" * 64
    key, _ = backup.backup_object_keys("20261101T120000Z")
    manifest = backup.backup_attestation(key=key, size=12345, sha256=digest, stamp="20261101T120000Z")
    assert manifest["status"] == "checksum_verified_restore_pending"
    assert manifest["object_key"] == key
    assert manifest["bytes"] == 12345
    assert manifest["sha256"] == digest
    assert manifest["restore_drill_done"] is False
    assert "database_url" not in manifest
    assert "password" not in manifest


def test_attestation_rejects_trusted_prefix_and_truncated_stream():
    import pytest
    with pytest.raises(ValueError):
        backup.backup_attestation(key="seacommons/backups/full/dump.dump", size=12345, sha256="a"*64, stamp="x")
    with pytest.raises(ValueError):
        backup.backup_attestation(key="seacommons/backups/pending/dump.dump", size=999, sha256="a"*64, stamp="x")
    with pytest.raises(ValueError):
        backup.backup_attestation(key="seacommons/backups/pending/dump.dump", size=12345, sha256="bad", stamp="x")
