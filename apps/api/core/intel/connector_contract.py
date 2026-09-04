# SPDX-License-Identifier: AGPL-3.0-or-later
"""Connector contract (docs/updates.md Section 5).

**Goal:** "Use a connector contract instead of source-specific logic
leaking into domain code" -- one shared shape every collector adapter
implements, so failure handling, health signalling and idempotency stop
being reinvented per module.

Not to be confused with ``core.connectors`` (a separate, pre-existing
package: partner WhatsApp Cloud connector *accounts*, i.e. an
organisation's inbound-message integration). This module is the
docs/updates.md Section 5 data-collection connector contract
(IMPORT/STREAM/ENRICH/PRESERVE/EXPORT) -- an unrelated concept that
happens to share the English word "connector". Deliberately placed
under core.intel, not core.connectors, to avoid that exact collision
(docs/fixes.md-era lesson: core.audit vs a same-named package once
silently broke an unrelated import in this codebase).

v0 scope, honestly bounded: this packet defines the CONTRACT --
``ConnectorClass``, ``FailureClass``, ``ConnectorHealth``,
``FetchResult``, and the ``Connector`` ABC itself, plus
``run_connector_fetch()``, the one shared safe-call wrapper that
enforces "Connector failure must not mutate existing incidents or
silently mark sources as empty" (a raised exception becomes an explicit
FetchResult(failure=...), never a swallowed empty success). It does NOT
yet migrate any of this codebase's ~10 existing collector modules
(core.intel.gfw_monitor, viirs_monitor, gdacs_monitor, twikit_monitor,
twitter_monitor, core.mda.warfare, etc.) onto this ABC -- each is its
own working, tested, production adapter today; converting it is a
separate, bounded, one-adapter-per-PR migration packet (docs/updates.md
Section 5's own instruction: "Do not build one giant news scraper.
Build bounded adapters with measurable coverage" applies equally to how
this contract itself gets adopted -- one adapter migration at a time,
each independently reviewable and revertable).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ConnectorClass(str, Enum):
    IMPORT = "import"
    STREAM = "stream"
    ENRICH = "enrich"
    PRESERVE = "preserve"
    EXPORT = "export"


class FailureClass(str, Enum):
    RATE_LIMITED = "rate_limited"
    SERVER_ERROR = "server_error"
    TIMEOUT = "timeout"
    AUTH_ERROR = "auth_error"
    MALFORMED_PAYLOAD = "malformed_payload"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ConnectorHealth:
    source_id: str
    status: str  # healthy | degraded | down
    last_success_at: Optional[str]
    last_failure_at: Optional[str]
    last_failure_class: Optional[FailureClass]
    consecutive_failures: int


@dataclass(frozen=True)
class FetchResult:
    """The outcome of one connector fetch cycle. ``items`` is always a
    list (possibly empty -- a source genuinely having nothing new is a
    real, distinct outcome from a failed fetch); ``failure`` is set only
    when the fetch itself did not complete, and callers must never treat
    an empty ``items`` list from a *successful* fetch as equivalent to a
    failure, or vice versa."""
    source_id: str
    ok: bool
    items: list[Any] = field(default_factory=list)
    next_cursor: Optional[str] = None
    failure_class: Optional[FailureClass] = None
    failure_detail: Optional[str] = None


class Connector(ABC):
    """The docs/updates.md Section 5 connector contract. A concrete
    adapter (e.g. a future GFWConnector) implements ``fetch`` and
    ``to_observation``; capabilities/idempotency/rate-limit/retry
    policy are declared as plain attributes so they are inspectable
    without instantiating or calling the connector."""

    source_id: str
    connector_class: ConnectorClass
    capabilities: tuple[str, ...] = ()
    rate_limit_per_minute: Optional[int] = None
    max_retries: int = 3
    fixture_mode: bool = False
    terms_notes: str = ""

    @abstractmethod
    def fetch(self, cursor: Optional[str] = None) -> FetchResult:
        """One bounded fetch cycle. Must return a FetchResult, never
        raise for an ordinary source-side failure (429/5xx/timeout/
        malformed payload) -- those are FetchResult(ok=False,
        failure_class=...). Raising is reserved for programming errors."""

    @abstractmethod
    def to_observation(self, raw_item: Any) -> dict[str, Any]:
        """Maps one raw fetched item to the SourceObservation shape
        (core.intel.source_observation). Must be deterministic: the same
        raw_item always produces the same idempotency-relevant fields."""

    @abstractmethod
    def idempotency_key(self, raw_item: Any) -> str:
        """A stable key for this raw item -- the same source event
        fetched twice (pagination overlap, retry, redelivery) must
        produce the same key so it is never double-counted."""


def run_connector_fetch(
    connector: Connector, cursor: Optional[str] = None,
) -> FetchResult:
    """The one shared safe-call wrapper every caller should use instead
    of calling connector.fetch() directly: an unexpected exception from
    a connector becomes an explicit failed FetchResult -- never a
    silently empty one, and never propagates to mutate whatever the
    caller was about to do with existing incidents."""
    try:
        return connector.fetch(cursor=cursor)
    except Exception as exc:  # noqa: BLE001 -- deliberate: any connector exception must become a typed failure, never propagate
        return FetchResult(
            source_id=connector.source_id, ok=False,
            failure_class=FailureClass.UNKNOWN, failure_detail=str(exc),
        )
