# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import queue
import threading
from dataclasses import dataclass

from core.radio.decoder_runtime import EphemeralRadioFrame
from core.radio.pcm import normalize_pcm16le


@dataclass(frozen=True)
class AudioSubscription:
    receiver_id: str
    queue: queue.Queue[bytes]


@dataclass(frozen=True)
class _ListenReceiverRecord:
    receiver_id: str
    terms_status: str
    network_family: str


class EphemeralAudioBroker:
    """Bounded in-memory fanout for on-demand listening; never persists audio."""

    def __init__(self, *, max_subscribers: int = 8, queue_size: int = 24) -> None:
        self._max_subscribers = max(1, int(max_subscribers))
        self._queue_size = max(1, int(queue_size))
        self._subscriptions: list[AudioSubscription] = []
        self._published_frames = 0
        self._dropped_frames = 0
        self._lock = threading.Lock()

    def subscribe(self, receiver_id: str) -> AudioSubscription:
        receiver_id = str(receiver_id).strip()
        if not receiver_id:
            raise ValueError("receiver_id required")
        with self._lock:
            if len(self._subscriptions) >= self._max_subscribers:
                raise RuntimeError("listen capacity reached")
            subscription = AudioSubscription(receiver_id, queue.Queue(maxsize=self._queue_size))
            self._subscriptions.append(subscription)
            return subscription

    def unsubscribe(self, subscription: AudioSubscription) -> None:
        with self._lock:
            if subscription in self._subscriptions:
                self._subscriptions.remove(subscription)

    def publish(self, frame: EphemeralRadioFrame) -> int:
        with self._lock:
            targets = [item for item in self._subscriptions if item.receiver_id == frame.receiver_id]
        if not targets:
            return 0
        try:
            pcm = normalize_pcm16le(
                frame.payload, encoding=frame.encoding, sample_rate_hz=frame.sample_rate_hz
            ).payload
        except (TypeError, ValueError):
            return 0
        delivered = 0
        for subscription in targets:
            try:
                subscription.queue.put_nowait(pcm)
                delivered += 1
            except queue.Full:
                with self._lock:
                    self._dropped_frames += 1
        if delivered:
            with self._lock:
                self._published_frames += 1
        return delivered

    def status(self) -> dict[str, int]:
        with self._lock:
            return {
                "subscribers": len(self._subscriptions),
                "published_frames": self._published_frames,
                "dropped_frames": self._dropped_frames,
            }


def _catalog_rows_for_receiver_ids(receiver_ids: set[str]):
    from core.db.models import ReceiverCatalogDB
    from core.db.session import session_scope

    if not receiver_ids:
        return []
    with session_scope() as db:
        rows = db.query(ReceiverCatalogDB).filter(ReceiverCatalogDB.receiver_id.in_(receiver_ids)).all()
        return [
            _ListenReceiverRecord(
                receiver_id=str(row.receiver_id or ""),
                terms_status=str(row.terms_status or ""),
                network_family=str(row.network_family or ""),
            )
            for row in rows
        ]


def listen_eligible_receiver_ids(active_receiver_ids: set[str]) -> set[str]:
    eligible: set[str] = set()
    for row in _catalog_rows_for_receiver_ids(set(active_receiver_ids)):
        if row.receiver_id not in active_receiver_ids:
            continue
        if row.terms_status != "allowed":
            continue
        if row.network_family not in {"kiwisdr", "openwebrx"}:
            continue
        eligible.add(row.receiver_id)
    return eligible


listen_broker = EphemeralAudioBroker()


def publish_ephemeral_audio(frame: EphemeralRadioFrame) -> int:
    return listen_broker.publish(frame)
