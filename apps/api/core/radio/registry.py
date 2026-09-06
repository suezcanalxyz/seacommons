# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit, urlunsplit

from core.radio.provider import ReceiverCapability, _normalize_identifier, normalize_provider_name

_TERMS_STATUSES = frozenset({"allowed", "unknown", "blocked"})
_MAX_OPERATOR_NOTE_CHARS = 256
_MAX_PUBLIC_LABEL_CHARS = 96
_CHANNEL_KINDS = frozenset({"dsc", "navtex", "monitor"})


def _canonical_frontend_url(value: str) -> str:
    parsed = urlsplit(str(value or "").strip())
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https", "ws", "wss"} or not parsed.netloc:
        raise ValueError("frontend_url must be an absolute http(s)/ws(s) URL")
    path = parsed.path.rstrip("/")
    return urlunsplit((scheme, parsed.netloc.lower(), path, parsed.query, ""))


def receiver_id_for(provider: str, frontend_url: str) -> str:
    provider_id = normalize_provider_name(provider)
    canonical_url = _canonical_frontend_url(frontend_url)
    digest = hashlib.blake2s(
        f"{provider_id}:{canonical_url}".encode("utf-8"), digest_size=8
    ).hexdigest()
    return f"radio_rx_{provider_id}_{digest}"


@dataclass(frozen=True)
class ReceiverDescriptor:
    provider: str
    frontend_url: str
    physical_lineage: str
    capabilities: tuple[ReceiverCapability, ...]
    source_terms: str
    terms_status: str = "unknown"
    enabled: bool = True
    latitude: float | None = None
    longitude: float | None = None
    operator_note: str = ""
    receiver_id: str = ""
    public_label: str = ""
    channel_kind: str = "monitor"
    frequency_hz: int | None = None
    mode: str | None = None

    def __post_init__(self) -> None:
        provider = normalize_provider_name(self.provider)
        frontend_url = _canonical_frontend_url(self.frontend_url)
        lineage = _normalize_identifier(self.physical_lineage, field="physical_lineage")
        terms_status = str(self.terms_status or "unknown").strip().lower()
        if terms_status not in _TERMS_STATUSES:
            raise ValueError("terms_status must be allowed, unknown, or blocked")
        source_terms = str(self.source_terms or "").strip()
        if terms_status == "allowed" and not source_terms:
            raise ValueError("allowed receiver requires source_terms")
        if not self.capabilities:
            raise ValueError("receiver requires at least one capability")
        if self.latitude is not None and not -90 <= self.latitude <= 90:
            raise ValueError("latitude out of range")
        if self.longitude is not None and not -180 <= self.longitude <= 180:
            raise ValueError("longitude out of range")
        channel_kind = str(self.channel_kind or "monitor").strip().lower()
        if channel_kind not in _CHANNEL_KINDS:
            raise ValueError("channel_kind must be dsc, navtex, or monitor")
        frequency_hz = int(self.frequency_hz) if self.frequency_hz is not None else None
        if channel_kind in {"dsc", "navtex"} and frequency_hz is None:
            raise ValueError(f"{channel_kind} channel requires frequency_hz")
        if frequency_hz is not None and not any(
            capability.frequency_min_hz <= frequency_hz <= capability.frequency_max_hz
            for capability in self.capabilities
        ):
            raise ValueError("frequency_hz is outside receiver capabilities")
        mode = str(self.mode or "").strip().lower() or None
        if mode is not None and not any(mode in capability.modes for capability in self.capabilities):
            raise ValueError("mode is outside receiver capabilities")
        resolved_receiver_id = (
            _normalize_identifier(self.receiver_id, field="receiver_id")
            if self.receiver_id
            else receiver_id_for(provider, frontend_url)
        )
        public_label = " ".join(str(self.public_label or "").split()).strip()
        if not public_label:
            public_label = resolved_receiver_id
        public_label = public_label[:_MAX_PUBLIC_LABEL_CHARS].strip()

        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "frontend_url", frontend_url)
        object.__setattr__(self, "physical_lineage", lineage)
        object.__setattr__(self, "source_terms", source_terms)
        object.__setattr__(self, "terms_status", terms_status)
        object.__setattr__(self, "operator_note", str(self.operator_note or "")[:_MAX_OPERATOR_NOTE_CHARS])
        object.__setattr__(self, "receiver_id", resolved_receiver_id)
        object.__setattr__(self, "public_label", public_label)
        object.__setattr__(self, "channel_kind", channel_kind)
        object.__setattr__(self, "frequency_hz", frequency_hz)
        object.__setattr__(self, "mode", mode)


class ReceiverRegistry:
    def __init__(
        self,
        descriptors: Iterable[ReceiverDescriptor] = (),
        *,
        max_receivers: int,
    ) -> None:
        if max_receivers <= 0:
            raise ValueError("maximum receiver count must be positive")
        items = tuple(descriptors)
        if len(items) > max_receivers:
            raise ValueError(f"configured receiver count exceeds maximum {max_receivers}")
        self._descriptors = items

    def all(self) -> tuple[ReceiverDescriptor, ...]:
        return self._descriptors

    def runnable(self) -> tuple[ReceiverDescriptor, ...]:
        selected: list[ReceiverDescriptor] = []
        physical_lineages: set[str] = set()
        for descriptor in self._descriptors:
            if not descriptor.enabled or descriptor.terms_status != "allowed":
                continue
            if descriptor.physical_lineage in physical_lineages:
                continue
            physical_lineages.add(descriptor.physical_lineage)
            selected.append(descriptor)
        return tuple(selected)


def _capability_from_mapping(value: Mapping[str, Any]) -> ReceiverCapability:
    return ReceiverCapability(
        frequency_min_hz=int(value["frequency_min_hz"]),
        frequency_max_hz=int(value["frequency_max_hz"]),
        modes=tuple(str(mode) for mode in value.get("modes", ())),
    )


def _descriptor_from_mapping(value: Mapping[str, Any]) -> ReceiverDescriptor:
    capabilities = tuple(
        _capability_from_mapping(item) for item in value.get("capabilities", ())
    )
    return ReceiverDescriptor(
        provider=str(value.get("provider") or ""),
        frontend_url=str(value.get("frontend_url") or ""),
        physical_lineage=str(value.get("physical_lineage") or ""),
        capabilities=capabilities,
        source_terms=str(value.get("source_terms") or ""),
        terms_status=str(value.get("terms_status") or "unknown"),
        enabled=bool(value.get("enabled", True)),
        latitude=float(value["latitude"]) if value.get("latitude") is not None else None,
        longitude=float(value["longitude"]) if value.get("longitude") is not None else None,
        operator_note=str(value.get("operator_note") or ""),
        receiver_id=str(value.get("receiver_id") or ""),
        public_label=str(value.get("public_label") or ""),
        channel_kind=str(value.get("channel_kind") or "monitor"),
        frequency_hz=(int(value["frequency_hz"]) if value.get("frequency_hz") is not None else None),
        mode=(str(value.get("mode") or "") or None),
    )


def load_receiver_descriptors(
    *,
    raw_json: str = "",
    file_path: str = "",
    max_receivers: int,
) -> ReceiverRegistry:
    raw_json = str(raw_json or "").strip()
    file_path = str(file_path or "").strip()
    if raw_json and file_path:
        raise ValueError("configure either raw_json or file_path, not both")
    if not raw_json and not file_path:
        return ReceiverRegistry(max_receivers=max_receivers)

    payload = raw_json if raw_json else Path(file_path).read_text(encoding="utf-8")
    decoded = json.loads(payload)
    if not isinstance(decoded, list):
        raise ValueError("receiver configuration must be a JSON list")
    descriptors = tuple(_descriptor_from_mapping(item) for item in decoded)
    return ReceiverRegistry(descriptors, max_receivers=max_receivers)
