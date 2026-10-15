# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import threading
import math
import re
from collections.abc import Callable
from typing import Any

StatusProvider = Callable[[], dict[str, Any]]

_lock = threading.Lock()
_providers: dict[str, tuple[str, StatusProvider]] = {}

_ALLOWED_DETAIL_FIELDS = frozenset(
    {
        "mode", "configured", "started", "failed", "last_observation_at",
        "receivers", "channels", "structured_enabled", "structured_state", "decoder", "pipeline",
    }
)
_ALLOWED_RECEIVER_FIELDS = frozenset(
    {
        "receiver_id",
        "station_label",
        "provider",
        "state",
        "channel_kind",
        "frequency_hz",
        "mode",
        "last_observation_at",
        "observations_received",
    }
)
_ALLOWED_CHANNEL_FIELDS = frozenset(
    {
        "channel_kind", "frequency_hz", "mode", "desired",
        "active", "standby", "cooldown", "failovers",
    }
)
# Radio status is a public endpoint. Never expose receiver lineages, decoder
# commands, raw PCM, payload bodies or free-form internal diagnostics here.
_ALLOWED_DECODER_COUNTERS = frozenset({
    "decoders", "frames", "decoded", "accepted", "dsc_accepted", "navtex_accepted", "rejected", "invalid",
    "dropped", "errors", "queued", "worker_count", "continuity_resets",
    "state_evictions", "bridge_errors", "recent_window_s",
    "recent_frames", "recent_dropped", "recent_invalid", "recent_errors",
    "queue_capacity_per_shard",
})
_ALLOWED_AUDIO_COUNTERS = frozenset({
    "sampled_frames", "silent_frames", "clipped_frames",
    "invalid_pcm_frames", "sampling_interval_frames",
})
_ALLOWED_AUDIO_MEASUREMENTS = frozenset({"sampled_duration_s", "mean_rms"})
_ALLOWED_DECODER_RATIOS = frozenset({"decode_ratio", "drop_ratio", "recent_drop_ratio"})
_ALLOWED_DECODER_SHARDS = frozenset({"queues", "frames_by_shard", "drops_by_shard"})


def _sanitize_decoder(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, Any] = {}
    for key in ("enabled", "worker_alive"):
        if isinstance(value.get(key), bool):
            out[key] = value[key]
    for key in _ALLOWED_DECODER_COUNTERS:
        item = value.get(key)
        if type(item) is int and item >= 0:
            out[key] = item
    for key in _ALLOWED_DECODER_RATIOS:
        item = value.get(key)
        if type(item) in (float, int) and math.isfinite(item) and 0 <= item <= 1:
            out[key] = round(float(item), 6)
    # No arbitrary lists or identifiers. Maximum four worker shards by design.
    for key in _ALLOWED_DECODER_SHARDS:
        item = value.get(key)
        if isinstance(item, (tuple, list)) and len(item) <= 4 and all(
            type(n) is int and n >= 0 for n in item
        ):
            out[key] = list(item)
    audio = value.get("audio_quality")
    reasons = value.get("continuity_reset_reasons")
    allowed_reasons = ("sequence_gap", "session", "timestamp_gap", "stale")
    if isinstance(reasons, dict):
        out["continuity_reset_reasons"] = {
            key: reasons[key] for key in allowed_reasons
            if type(reasons.get(key)) is int and reasons[key] >= 0
        }
    sources = value.get("continuity_reset_sources")
    if isinstance(sources, list) and len(sources) <= 16:
        safe_sources = []
        for item in sources:
            if not isinstance(item, dict):
                continue
            receiver = item.get("receiver_id")
            if not isinstance(receiver, str) or not re.fullmatch(r"[a-z0-9_]{1,64}", receiver):
                continue
            row = {"receiver_id": receiver}
            for key in ("resets", *allowed_reasons):
                if type(item.get(key)) is int and item[key] >= 0:
                    row[key] = item[key]
            safe_sources.append(row)
        out["continuity_reset_sources"] = safe_sources
    if isinstance(audio, dict):
        safe_audio: dict[str, Any] = {}
        for key in _ALLOWED_AUDIO_COUNTERS:
            item = audio.get(key)
            if type(item) is int and item >= 0:
                safe_audio[key] = item
        for key in _ALLOWED_AUDIO_MEASUREMENTS:
            item = audio.get(key)
            if type(item) in (float, int) and math.isfinite(item) and item >= 0:
                safe_audio[key] = round(float(item), 5)
        out["audio_quality"] = safe_audio
    return out


def register_acquisition_status(family: str, label: str, provider: StatusProvider) -> None:
    normalized = str(family or "").strip().lower()
    if not normalized:
        raise ValueError("family is required")
    public_label = " ".join(str(label or "").split()).strip()
    if not public_label:
        raise ValueError("label is required")
    with _lock:
        _providers[normalized] = (public_label[:96], provider)


def _sanitize_receivers(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, (list, tuple)):
        return []
    rows: list[dict[str, Any]] = []
    for item in value[:16]:
        if not isinstance(item, dict):
            continue
        rows.append({key: item.get(key) for key in _ALLOWED_RECEIVER_FIELDS if key in item})
    return rows


def _sanitize_channels(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, (list, tuple)):
        return []
    rows: list[dict[str, Any]] = []
    for item in value[:8]:
        if not isinstance(item, dict):
            continue
        rows.append({key: item.get(key) for key in _ALLOWED_CHANNEL_FIELDS if key in item})
    return rows


_RADIO_STAGE_LABELS = {
    "reception": "Radio reception",
    "demodulation": "DSC signal processing",
    "validation": "Verified DSC messages",
    "evidence": "Persisted DSC evidence",
    "ais_correlation": "Strong AIS correlations",
    "episode": "Linked investigations",
    "safety_review": "Distress candidates requiring review",
}
_RADIO_STAGE_IDS = frozenset(_RADIO_STAGE_LABELS)
_RADIO_STAGE_STATES = frozenset({
    "live", "listening", "idle", "degraded", "offline", "disabled",
    "verified", "awaiting_message", "recorded", "correlated", "awaiting_match",
    "linked", "review_required", "none_verified",
})


def _sanitize_radio_pipeline(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    stages = value.get("stages")
    if not isinstance(stages, list) or len(stages) > 7:
        return {}
    safe = []
    for stage in stages:
        if not isinstance(stage, dict) or stage.get("id") not in _RADIO_STAGE_IDS:
            continue
        if stage.get("state") not in _RADIO_STAGE_STATES:
            continue
        count = stage.get("count")
        if type(count) is not int or count < 0:
            continue
        safe.append({"id": stage["id"],
                     "label": _RADIO_STAGE_LABELS[stage["id"]],
                     "state": stage["state"], "count": count})
    return {"name": "Maritime radio evidence", "count_scope": "since_process_start",
            "stages": safe}


def acquisition_status_sources() -> list[dict[str, Any]]:
    with _lock:
        items = tuple(sorted(_providers.items()))
    result: list[dict[str, Any]] = []
    for family, (label, provider) in items:
        try:
            detail = dict(provider() or {})
        except Exception:
            detail = {"state": "offline"}
        state = str(detail.get("state", "offline") or "offline").strip().lower()
        if state not in {"live", "degraded", "offline", "disabled"}:
            state = "degraded"
        public_detail: dict[str, Any] = {}
        for key in _ALLOWED_DETAIL_FIELDS:
            if key not in detail:
                continue
            if key == "receivers":
                public_detail[key] = _sanitize_receivers(detail[key])
            elif key == "channels":
                public_detail[key] = _sanitize_channels(detail[key])
            elif key == "decoder":
                public_detail[key] = _sanitize_decoder(detail[key])
            elif key == "pipeline":
                public_detail[key] = _sanitize_radio_pipeline(detail[key])
            else:
                public_detail[key] = detail[key]
        result.append({"family": family, "label": label, "state": state, **public_detail})
    return result


def _ais_status() -> dict[str, Any]:
    from core.config import config
    from core.vessels.ais_runtime import runtime
    from core.vessels.aisstream import get_client

    rt = runtime()
    mode = rt.mode if rt is not None else str(config.AIS_FUSION_MODE or "legacy")
    if not config.AISSTREAM_KEY:
        return {"state": "disabled", "mode": mode}
    client = get_client()
    if client is None:
        return {"state": "offline", "mode": mode}
    return {"state": "live" if bool(client.connected) else "degraded", "mode": mode}


def _registry_status(*, types: frozenset[str]) -> dict[str, Any]:
    from core.intel.source_registry import source_registry

    rows = [row for row in source_registry.get_all() if str(row.get("type") or "").lower() in types]
    if not rows:
        return {"state": "offline", "configured": 0}
    states = {str(row.get("pipeline_status") or row.get("status") or "").lower() for row in rows}
    if "active" in states or "healthy" in states:
        state = "live"
    elif states & {"degraded", "pending"}:
        state = "degraded"
    else:
        state = "offline"
    last_values = sorted(str(row.get("last_poll_at")) for row in rows if row.get("last_poll_at"))
    result: dict[str, Any] = {"state": state, "configured": len(rows)}
    if last_values:
        result["last_observation_at"] = last_values[-1]
    return result


def _first_party_status() -> dict[str, Any]:
    return _registry_status(types=frozenset({"twitter", "mastodon", "bluesky", "ngo"}))


def _public_feed_status() -> dict[str, Any]:
    return _registry_status(types=frozenset({"rss", "gdacs", "news", "iom", "scrape"}))


def _partner_status() -> dict[str, Any]:
    from core.config import config

    configured = sum(
        int(bool(value))
        for value in (
            config.PARTNER_WEBHOOK_SECRET,
            config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_WEBHOOK_SECRET,
            config.META_APP_ID and config.META_APP_SECRET and config.META_WEBHOOK_VERIFY_TOKEN,
        )
    )
    return {"state": "degraded" if configured else "disabled", "configured": configured}


def ensure_default_acquisition_status() -> None:
    from core.radio.bridge import radio_acquisition_status

    register_acquisition_status("ais", "AIS", _ais_status)
    register_acquisition_status("first_party", "First-party feeds", _first_party_status)
    register_acquisition_status("partner", "Partner inputs", _partner_status)
    register_acquisition_status("public_feed", "Public feeds", _public_feed_status)
    register_acquisition_status("radio", "Radio", radio_acquisition_status)


def _reset_acquisition_status_for_tests() -> None:
    with _lock:
        _providers.clear()
