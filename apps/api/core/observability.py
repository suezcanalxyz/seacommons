# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations
import json, logging, time, uuid
from datetime import datetime, timezone
from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUESTS = Counter("seacommons_http_requests_total", "HTTP requests", ["method", "path", "status"])
HTTP_LATENCY = Histogram("seacommons_http_request_duration_seconds", "HTTP request latency", ["method", "path"])
JOBS = Gauge("seacommons_jobs", "Durable jobs by state", ["status"])
WORKERS = Gauge("seacommons_workers_alive", "Workers with a fresh heartbeat")
JOB_RUNS = Counter("seacommons_job_runs_total", "Worker job executions", ["type", "outcome"])


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {"timestamp": datetime.now(timezone.utc).isoformat(), "level": record.levelname,
                   "logger": record.name, "message": record.getMessage()}
        for key in ("request_id", "job_id", "worker_id"):
            if hasattr(record, key): payload[key] = getattr(record, key)
        if record.exc_info: payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    from core.config import config
    if config.LOG_FORMAT != "json": return
    handler = logging.StreamHandler(); handler.setFormatter(JsonFormatter())
    root = logging.getLogger(); root.handlers[:] = [handler]; root.setLevel(logging.INFO)


async def metrics_middleware(request, call_next):
    started = time.perf_counter(); request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    request.state.request_id = request_id
    try:
        response = await call_next(request); status = response.status_code
    except Exception:
        status = 500; raise
    finally:
        route = request.scope.get("route"); path = getattr(route, "path", request.url.path)
        HTTP_REQUESTS.labels(request.method, path, str(status)).inc()
        HTTP_LATENCY.labels(request.method, path).observe(time.perf_counter() - started)
    response.headers["X-Request-Id"] = request_id
    return response


def refresh_operational_gauges() -> None:
    from datetime import timedelta
    from sqlalchemy import func, select
    from core.db.models import JobDB, WorkerHeartbeatDB
    from core.db.session import session_scope
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with session_scope() as db:
        counts = dict(db.execute(select(JobDB.status, func.count()).group_by(JobDB.status)).all())
        for state in ("queued", "running", "retry", "completed", "dead"):
            JOBS.labels(state).set(counts.get(state, 0))
        alive = db.execute(select(func.count()).select_from(WorkerHeartbeatDB).where(
            WorkerHeartbeatDB.last_seen_at >= now - timedelta(seconds=60))).scalar_one()
        WORKERS.set(alive)
