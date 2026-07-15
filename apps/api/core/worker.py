# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations
import logging, os, socket, time, threading
from datetime import datetime
from core.config import config
from core.db.session import init_database
from core.jobs import claim, complete, fail, heartbeat, renew
from core.observability import JOB_RUNS, configure_logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
configure_logging()
logger = logging.getLogger("seacommons.worker")


def execute(job: dict) -> dict:
    payload = job["payload"]
    if job["job_type"] == "drift":
        from core.api.routes.drift import DriftRequest, _run_drift
        _run_drift(payload["drift_id"], DriftRequest.model_validate(payload["request"]))
        from core.db.store import get_drift
        result = get_drift(payload["drift_id"])
        if not result or result.get("status") != "completed":
            raise RuntimeError((result or {}).get("metadata", {}).get("error", "Drift failed"))
        return {"drift_id": payload["drift_id"]}
    if job["job_type"] == "alert_drift":
        from core.api.routes.alerts import MaritimeEvent, _process_drift_inner
        _process_drift_inner(payload["event_id"], MaritimeEvent.model_validate(payload["event"]))
        from core.db.store import get_drift
        result = get_drift(payload["event_id"])
        if not result or result.get("status") != "completed":
            raise RuntimeError((result or {}).get("metadata", {}).get("error", "Alert drift failed"))
        return {"event_id": payload["event_id"]}
    raise ValueError(f"Unknown job type: {job['job_type']}")


def run(once: bool = False) -> None:
    init_database()
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    logger.info("worker started id=%s", worker_id)
    last_heartbeat = 0.0
    while True:
        if time.monotonic() - last_heartbeat >= config.WORKER_HEARTBEAT_SECONDS:
            heartbeat(worker_id, socket.gethostname(), os.getpid())
            last_heartbeat = time.monotonic()
        job = claim(worker_id)
        if job is None:
            if once: return
            time.sleep(config.JOB_POLL_SECONDS); continue
        stop_lease = threading.Event()
        def keep_alive():
            while not stop_lease.wait(min(30, max(1, config.JOB_LEASE_SECONDS // 3))):
                renew(job["job_id"], worker_id)
                heartbeat(worker_id, socket.gethostname(), os.getpid(), job["job_id"])
        lease_thread = threading.Thread(target=keep_alive, daemon=True, name="job-lease-renewal")
        lease_thread.start()
        heartbeat(worker_id, socket.gethostname(), os.getpid(), job["job_id"])
        try:
            complete(job["job_id"], execute(job))
            JOB_RUNS.labels(job["job_type"], "completed").inc()
            logger.info("job completed id=%s type=%s", job["job_id"], job["job_type"])
        except Exception as exc:
            state = fail(job["job_id"], str(exc))
            JOB_RUNS.labels(job["job_type"], state).inc()
            logger.exception("job failed id=%s state=%s", job["job_id"], state)
        finally:
            stop_lease.set(); lease_thread.join(timeout=1)
            heartbeat(worker_id, socket.gethostname(), os.getpid())
        if once: return


if __name__ == "__main__":
    run()
