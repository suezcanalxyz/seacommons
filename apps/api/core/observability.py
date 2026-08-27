# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations
import json, logging, time, uuid
from collections import Counter as CollectionCounter
from datetime import datetime, timezone
from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUESTS = Counter("seacommons_http_requests_total", "HTTP requests", ["method", "path", "status"])
HTTP_LATENCY = Histogram("seacommons_http_request_duration_seconds", "HTTP request latency", ["method", "path"])
JOBS = Gauge("seacommons_jobs", "Durable jobs by state", ["status"])
WORKERS = Gauge("seacommons_workers_alive", "Workers with a fresh heartbeat")
JOB_RUNS = Counter("seacommons_job_runs_total", "Worker job executions", ["type", "outcome"])
INTEL_SYNC_RUNS = Counter(
    "seacommons_intel_sync_runs_total",
    "Split-runtime intel database sync attempts",
    ["outcome"],
)
INTEL_SYNC_EVENTS = Counter(
    "seacommons_intel_sync_events_total",
    "Intel events observed by split-runtime database sync",
    ["change"],
)
INTEL_SYNC_CONSECUTIVE_FAILURES = Gauge(
    "seacommons_intel_sync_consecutive_failures",
    "Consecutive split-runtime intel database sync failures",
)
INTEL_SYNC_LAST_SUCCESS = Gauge(
    "seacommons_intel_sync_last_success_unixtime",
    "Unix timestamp of the last successful split-runtime intel database sync",
)
INTEL_SOURCES = Gauge(
    "seacommons_intel_sources",
    "Registered intel sources by current health state",
    ["status"],
)
INTEL_SOURCE_EVENTS = Gauge(
    "seacommons_intel_source_events_last_hour",
    "Events received from all registered intel sources in the last hour",
)
LIVE_PUBLISH_CYCLES = Counter(
    "seacommons_live_publish_cycles_total",
    "Live edge publisher cycles by outcome",
    ["outcome"],
)
LIVE_PUBLISH_EVENTS = Counter(
    "seacommons_live_publish_events_total",
    "Live edge payloads by pipeline stage",
    ["stage"],  # collected | delivered | delivery_failed
)
LIVE_OUTBOX_DEPTH = Gauge(
    "seacommons_live_outbox_depth",
    "Live edge publisher outbox rows by state",
    ["state"],  # pending | retrying
)
LIVE_PUBLISH_LAST_CYCLE = Gauge(
    "seacommons_live_publish_last_cycle_unixtime",
    "Unix timestamp of the last completed live edge publisher cycle",
)
LIVE_PUBLISH_LAST_DELIVERY = Gauge(
    "seacommons_live_publish_last_delivery_unixtime",
    "Unix timestamp of the last successful live edge delivery",
)
LIVE_EDGE_HEARTBEAT_OK = Gauge(
    "seacommons_live_edge_heartbeat_ok",
    "1 if the last live edge heartbeat POST succeeded, else 0",
)


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
    refresh_source_health_gauges()


def refresh_source_health_gauges() -> None:
    """Export bounded-cardinality health totals from the in-process registry."""
    from core.intel.source_registry import source_registry

    sources = source_registry.get_all()
    counts = CollectionCounter(source.get("status", "pending") for source in sources)
    for status in ("pending", "active", "degraded", "offline"):
        INTEL_SOURCES.labels(status).set(counts.get(status, 0))
    INTEL_SOURCE_EVENTS.set(sum(int(source.get("events_last_hour") or 0) for source in sources))


def record_intel_sync_success(new_count: int, updated_count: int) -> None:
    """Record a successful API-side database sync in split-runtime mode."""
    INTEL_SYNC_RUNS.labels("success").inc()
    INTEL_SYNC_EVENTS.labels("new").inc(max(0, int(new_count)))
    INTEL_SYNC_EVENTS.labels("updated").inc(max(0, int(updated_count)))
    INTEL_SYNC_CONSECUTIVE_FAILURES.set(0)
    INTEL_SYNC_LAST_SUCCESS.set_to_current_time()


def record_intel_sync_failure(consecutive_failures: int) -> None:
    """Record a failed API-side database sync without exposing exception details."""
    INTEL_SYNC_RUNS.labels("failure").inc()
    INTEL_SYNC_CONSECUTIVE_FAILURES.set(max(1, int(consecutive_failures)))


def record_publisher_cycle(
    *, outcome: str, collected: int, outbox_counts: dict[str, int]
) -> None:
    """Record one live edge publisher cycle and the current outbox backlog."""
    LIVE_PUBLISH_CYCLES.labels(outcome if outcome in {"ok", "degraded"} else "degraded").inc()
    if collected:
        LIVE_PUBLISH_EVENTS.labels("collected").inc(max(0, int(collected)))
    LIVE_OUTBOX_DEPTH.labels("pending").set(int(outbox_counts.get("pending", 0)))
    LIVE_OUTBOX_DEPTH.labels("retrying").set(int(outbox_counts.get("retrying", 0)))
    LIVE_PUBLISH_LAST_CYCLE.set_to_current_time()


def record_publisher_delivery(*, delivered: bool) -> None:
    """Record a single edge delivery attempt outcome."""
    if delivered:
        LIVE_PUBLISH_EVENTS.labels("delivered").inc()
        LIVE_PUBLISH_LAST_DELIVERY.set_to_current_time()
    else:
        LIVE_PUBLISH_EVENTS.labels("delivery_failed").inc()


def record_publisher_heartbeat(*, ok: bool) -> None:
    LIVE_EDGE_HEARTBEAT_OK.set(1 if ok else 0)
