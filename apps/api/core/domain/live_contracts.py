# SPDX-License-Identifier: AGPL-3.0-or-later
"""Canonical vocabulary and boundary models for public Live data."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

LIVE_SIGNAL_SCHEMA = "org.seacommons.live-signal/v1"
FEDERATED_EVENT_SCHEMA = "seacommons-event-v1"


class PublicationStatus(StrEnum):
    PRIVATE = "private"
    INTERNAL = "internal"
    PUBLISHED = "published"


class Visibility(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"


class IncidentLifecycle(StrEnum):
    ACTIVE = "active"
    RESOLVED = "resolved"
    NEEDS_REVIEW = "needs_review"
    ARCHIVED = "archived"


class LiveSignalKind(StrEnum):
    DISTRESS = "distress"
    CONTEXT = "context"


class MaritimeDomain(StrEnum):
    """Which maritime-awareness compartment an intel event belongs to.

    ``sar`` is the primary operational lane (migrant and general distress) and
    the only compartment published to the public Live map by default; every
    other compartment is operator-only unless it appears in
    ``PUBLIC_MARITIME_DOMAINS`` or the event is explicitly published.
    """

    SAR = "sar"
    SANCTIONS = "sanctions"
    GREY_ZONE = "grey_zone"
    IUU_FISHING = "iuu_fishing"
    PIRACY = "piracy"
    SMUGGLING = "smuggling"
    ENVIRONMENTAL = "environmental"
    SAFETY = "safety"


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class IntelTier(StrEnum):
    OPERATIONAL = "operational"
    NEWS = "news"
    SIGNAL = "signal"


class LocationPrecision(StrEnum):
    UNPOSITIONED = "unpositioned"
    APPROXIMATE = "approximate"
    REGIONAL_CENTROID = "regional_centroid"
    REPORTED_OR_DERIVED = "reported_or_derived"
    AREA = "area"
    AREA_LOW_CONFIDENCE = "area_low_confidence"


class SourcePolicy(StrEnum):
    OFFICIAL_API = "official_api"
    OFFICIAL_RSS = "official_rss"
    OFFICIAL_SITE_EMBED = "official_site_embed"
    TRUSTED_PARTNER = "trusted_partner"
    OPERATOR_PUBLISHED = "operator_published"
    ARCHIVE = "archive"
    UNOFFICIAL = "unofficial"
    NITTER = "nitter"
    SCRAPE = "scrape"
    TWSCRAPE = "twscrape"


class VerificationStatus(StrEnum):
    UNVERIFIED_PUBLIC_SOURCE = "unverified_public_source"
    OPERATOR_ASSERTED = "operator_asserted"
    MACHINE_EXTRACTED_UNVERIFIED = "machine_extracted_unverified"
    MULTI_SOURCE_CORROBORATED = "multi_source_corroborated"
    PARTNER_REPORTED = "partner_reported"
    USER_REPORTED = "user_reported"
    DERIVED = "derived"
    MODELLED_SPATIOTEMPORAL = "modelled_spatiotemporal"
    MODELLED_LIVE_FIELDS = "modelled_live_fields"


APPROVED_SOURCE_POLICIES = frozenset(
    {
        SourcePolicy.OFFICIAL_API.value,
        SourcePolicy.OFFICIAL_RSS.value,
        SourcePolicy.OFFICIAL_SITE_EMBED.value,
        SourcePolicy.TRUSTED_PARTNER.value,
    }
)
BLOCKED_SOURCE_POLICIES = frozenset(
    {
        SourcePolicy.NITTER.value,
        SourcePolicy.SCRAPE.value,
        SourcePolicy.TWSCRAPE.value,
        SourcePolicy.UNOFFICIAL.value,
    }
)

# Compartments eligible for the public Live map without an explicit per-event
# publish decision. ``sar`` is always public (the primary lane). Operators may
# widen this via the PUBLIC_MARITIME_DOMAINS env var (see core.intel.public_policy).
DEFAULT_PUBLIC_MARITIME_DOMAINS = frozenset(
    {
        MaritimeDomain.SAR.value,
        MaritimeDomain.PIRACY.value,
    }
)


def _validate_geometry(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    geometry_type = value.get("type")
    if geometry_type not in {"Point", "Polygon", "MultiPolygon"}:
        raise ValueError("public geometry must be Point, Polygon, MultiPolygon, or null")
    if "coordinates" not in value:
        raise ValueError("public geometry requires coordinates")
    return value


class LiveSignalProperties(BaseModel):
    """Stable public properties; provider-specific safe metadata remains allowed."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    schema_id: Literal["org.seacommons.live-signal/v1"] = Field(alias="schema")
    id: str = Field(min_length=1)
    type: str = Field(min_length=1)
    kind: LiveSignalKind
    severity: Severity
    tier: IntelTier
    verification_status: str = Field(min_length=1)
    publication_status: Literal["published"]
    source_policy: SourcePolicy
    timestamp_utc: datetime
    location_precision: LocationPrecision
    incident_lifecycle: IncidentLifecycle | None = None
    title: str = Field(default="", max_length=255)
    text: Literal[""] = ""
    source: str = Field(default="", max_length=64)
    url: str = ""


class LiveSignalFeature(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["Feature"]
    id: str = Field(min_length=1)
    geometry: dict[str, Any] | None
    properties: LiveSignalProperties

    _geometry = field_validator("geometry")(_validate_geometry)

    @model_validator(mode="after")
    def identifiers_match(self) -> LiveSignalFeature:
        if self.id != self.properties.id:
            raise ValueError("feature id and properties.id must match")
        return self


class FederatedEventInput(BaseModel):
    """Publisher payload before the edge adds receipt/hash-chain fields."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_id: Literal["seacommons-event-v1"] = Field(alias="schema")
    id: str = Field(min_length=16)
    type: str = Field(min_length=1)
    source: str = Field(min_length=1)
    node: str = Field(min_length=1)
    observed_at: datetime
    visibility: Visibility
    confidence: float | None = Field(default=None, ge=0, le=1)
    geometry: dict[str, Any] | None
    properties: dict[str, Any]
    source_url: str | None = None

    _geometry = field_validator("geometry")(_validate_geometry)


def validate_live_signal(feature: dict[str, Any]) -> dict[str, Any]:
    """Validate without rewriting the compatibility-preserving response object."""
    LiveSignalFeature.model_validate(feature)
    return feature


def validate_federated_event_input(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate the VM-to-edge event before it enters the durable outbox."""
    FederatedEventInput.model_validate(payload)
    return payload
