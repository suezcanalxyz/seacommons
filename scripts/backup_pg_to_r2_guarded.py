#!/usr/bin/env python3
"""Opt-in, low-priority PostgreSQL custom-format backup streamed to private R2.

Default mode only performs resource and configuration preflight. No database
changes, no local dump file, no deletion. An uploaded object is trusted only
when the producer exited cleanly and the remote SHA256 roundtrip matches.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import subprocess
import threading
import time
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api"))


class HashingReader:
    def __init__(self, source, *, max_bytes_per_second=0):
        self.source = source
        self.digest = hashlib.sha256()
        self.count = 0
        self.max_bytes_per_second = max(0.0, float(max_bytes_per_second or 0))
        self.started = time.monotonic()

    def read(self, size=-1):
        # Keep individual producer bursts bounded when throttling is enabled so
        # pg_dump blocks on the pipe instead of monopolising a small VM CPU.
        if self.max_bytes_per_second:
            size = min(size if size and size > 0 else 1024 * 1024, 1024 * 1024)
        chunk = self.source.read(size)
        if chunk:
            self.digest.update(chunk)
            self.count += len(chunk)
            if self.max_bytes_per_second:
                target_elapsed = self.count / self.max_bytes_per_second
                remaining = target_elapsed - (time.monotonic() - self.started)
                if remaining > 0:
                    time.sleep(remaining)
        return chunk


def resource_check(*, load1, cpu_psi_avg10, mem_available, disk_available, cpus, cpu_psi_avg60=None, cpu_psi_avg300=None):
    """Fail closed under CPU contention or low headroom."""
    if cpus < 1 or load1 > max(2.0, cpus * 1.25):
        return False, "cpu_load_high"
    if cpu_psi_avg10 > 45.0:
        return False, "cpu_pressure_high"
    # A brief quiet period is not sufficient after prolonged host saturation.
    if cpu_psi_avg60 is not None and cpu_psi_avg60 > 35.0:
        return False, "cpu_pressure_60s_high"
    if cpu_psi_avg300 is not None and cpu_psi_avg300 > 45.0:
        return False, "cpu_pressure_300s_high"
    if mem_available < 3 * 1024**3:
        return False, "memory_headroom_low"
    if disk_available < 6 * 1024**3:
        return False, "disk_headroom_low"
    return True, "ok"



def runtime_headroom_safe(*, mem_available, disk_available):
    """Abort a running dump if host RAM or disk becomes critically scarce."""
    if mem_available < 2 * 1024**3:
        return False, "runtime_memory_headroom_low"
    if disk_available < 4 * 1024**3:
        return False, "runtime_disk_headroom_low"
    return True, "ok"


def cpu_pressure_avg10():
    """Current host CPU PSI, not process CPU percent."""
    pressure = Path("/proc/pressure/cpu").read_text().splitlines()[0]
    return float(next(x.split("=")[1] for x in pressure.split() if x.startswith("avg10=")))


def sustained_cpu_pressure(samples, *, threshold=55.0, consecutive=2):
    """Avoid aborting a backup on a single transient PSI spike."""
    return len(samples) >= consecutive and all(x > threshold for x in samples[-consecutive:])


def preflight():
    import shutil
    load1 = os.getloadavg()[0]
    pressure = Path("/proc/pressure/cpu").read_text().splitlines()[0]
    psi = float(next(x.split("=")[1] for x in pressure.split() if x.startswith("avg10=")))
    psi60 = float(next(x.split("=")[1] for x in pressure.split() if x.startswith("avg60=")))
    psi300 = float(next(x.split("=")[1] for x in pressure.split() if x.startswith("avg300=")))
    available_kib = int(next(line.split()[1] for line in Path("/proc/meminfo").read_text().splitlines() if line.startswith("MemAvailable:")))
    disk = shutil.disk_usage("/").free
    cpus = os.cpu_count() or 1
    ok, reason = resource_check(load1=load1, cpu_psi_avg10=psi, cpu_psi_avg60=psi60, cpu_psi_avg300=psi300, mem_available=available_kib * 1024, disk_available=disk, cpus=cpus)
    return {"safe_to_run": ok, "reason": reason, "load1": round(load1, 2), "cpu_psi_avg10": round(psi, 2), "cpu_psi_avg60": round(psi60, 2), "cpu_psi_avg300": round(psi300, 2), "memory_available_gib": round(available_kib / 1024**2, 2), "disk_free_gib": round(disk / 1024**3, 2), "cpus": cpus}



def acquire_backup_lock(path=None):
    """Prevent overlapping full dumps from separate maintenance loops.

    The kernel releases the advisory lock on process exit, including a crash.
    No database or object-store content is touched by this guard.
    """
    lock_path = Path(path) if path is not None else Path.home() / ".local/state/seacommons/backup_pg_to_r2_guarded.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    handle = os.fdopen(fd, "r+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    return handle


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="Actually stream a full database backup if preflight passes")
    parser.add_argument(
        "--max-mibps", type=float,
        default=float(os.environ.get("SEACOMMONS_BACKUP_MAX_MIBPS", "3")),
        help="Throttle dump upload to protect the shared VM; 0 disables throttling",
    )
    args = parser.parse_args()
    from core.config import config
    from core import object_store
    from sqlalchemy.engine import make_url

    # An overlapping backup would double PostgreSQL read and CPU pressure.
    # The open handle keeps the kernel lock until this process exits.
    backup_lock = acquire_backup_lock() if args.execute else None
    if args.execute and backup_lock is None:
        print(json.dumps({"status": "blocked", "reason": "backup_already_running"}))
        return 7
    check = preflight()
    check["remote_configured"] = bool(config.OBJECT_STORAGE_ENDPOINT and config.OBJECT_STORAGE_BUCKET and config.OBJECT_STORAGE_ACCESS_KEY and config.OBJECT_STORAGE_SECRET_KEY)
    check["database_configured"] = bool(config.DATABASE_URL)
    if not args.execute:
        print(json.dumps(check, sort_keys=True))
        return 0
    if not check["safe_to_run"] or not check["remote_configured"] or not check["database_configured"]:
        print(json.dumps({"status": "blocked", **check}, sort_keys=True))
        return 2

    url = make_url(config.DATABASE_URL)
    env = os.environ.copy()
    if url.password:
        env["PGPASSWORD"] = url.password
    cmd = ["nice", "-n", "15", "ionice", "-c", "3", "pg_dump", "--format=custom", "--compress=1", "--no-owner", "--no-acl", "--host", url.host or "localhost", "--port", str(url.port or 5432), "--username", url.username or "seacommons", "--dbname", url.database or "seacommons"]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    key = f"seacommons/backups/full/pgdump-{stamp}.dump"
    client = object_store._client()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)
    # Runtime circuit breaker: preflight alone cannot protect a shared VM.
    # A read-only pg_dump can be stopped safely; an incomplete R2 object is
    # explicitly untrusted and must never be used for restore.
    monitor_stop = threading.Event()
    resource_abort = threading.Event()
    abort_reason = []

    def monitor_cpu_pressure():
        samples = []
        while not monitor_stop.wait(10):
            if proc.poll() is not None:
                return
            try:
                samples.append(cpu_pressure_avg10())
                samples = samples[-2:]
                if sustained_cpu_pressure(samples):
                    abort_reason.append("runtime_cpu_pressure_high")
                    resource_abort.set()
                    proc.terminate()
                    return
                import shutil
                available_kib = int(next(line.split()[1] for line in Path("/proc/meminfo").read_text().splitlines() if line.startswith("MemAvailable:")))
                safe, reason = runtime_headroom_safe(
                    mem_available=available_kib * 1024,
                    disk_available=shutil.disk_usage("/").free,
                )
                if not safe:
                    abort_reason.append(reason)
                    resource_abort.set()
                    proc.terminate()
                    return
            except (OSError, ValueError, StopIteration):
                continue

    monitor = threading.Thread(target=monitor_cpu_pressure, name="pgdump-cpu-guard", daemon=True)
    monitor.start()
    stream = HashingReader(proc.stdout, max_bytes_per_second=max(0.0, args.max_mibps) * 1024**2)
    try:
        client.put_object(config.OBJECT_STORAGE_BUCKET, key, stream, length=-1, part_size=64 * 1024**2, content_type="application/octet-stream")
    except Exception:
        proc.kill()
        proc.wait()
        print(json.dumps({"status": "upload_failed", "key": key}))
        return 3
    finally:
        monitor_stop.set()
        monitor.join(timeout=2)
        if proc.stdout:
            proc.stdout.close()
    if resource_abort.is_set():
        proc.wait()
        print(json.dumps({"status": "resource_abort_object_untrusted", "reason": abort_reason[-1] if abort_reason else "resource_guard", "key": key, "bytes": stream.count}))
        return 6
    if proc.wait() != 0 or stream.count < 1024 or not stream.digest:
        print(json.dumps({"status": "producer_failed_object_untrusted", "key": key, "bytes": stream.count}))
        return 4
    response = client.get_object(config.OBJECT_STORAGE_BUCKET, key)
    remote_hash = hashlib.sha256()
    remote_bytes = 0
    try:
        for chunk in response.stream(1024 * 1024):
            remote_hash.update(chunk)
            remote_bytes += len(chunk)
    finally:
        response.close()
        response.release_conn()
    verified = remote_bytes == stream.count and remote_hash.digest() == stream.digest.digest()
    print(json.dumps({"status": "roundtrip_verified" if verified else "checksum_mismatch", "key": key, "bytes": remote_bytes, "sha256": remote_hash.hexdigest(), "restore_drill_done": False}, sort_keys=True))
    return 0 if verified else 5


if __name__ == "__main__":
    raise SystemExit(main())
