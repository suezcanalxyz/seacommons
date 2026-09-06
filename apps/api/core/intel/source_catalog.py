# SPDX-License-Identifier: AGPL-3.0-or-later
"""Source Registry descriptive catalog (docs/updates.md P1.1).

**Goal:** operators can answer what SeaCommons is watching -- not just
whether it is currently healthy (core.intel.source_registry already
answers that operational half; this module is the descriptive half that
was missing entirely: family, coverage, languages, collection method,
terms/constraints, independence grouping, known limitations).

"Source reliability is contextual metadata, not one global truth score"
(docs/updates.md P1.1): nothing here computes or exposes a single
trust/reliability number. ``independence_group`` is the one field this
module uses for source-independence reasoning -- two sources sharing a
group are NOT independent corroboration of each other (e.g. every X/
Twitter-based collector shares the platform's own single point of
failure/moderation policy).

The catalog below is hand-curated from this codebase's own real
collector modules (core.intel.twikit_monitor, gdacs_monitor,
gfw_monitor, viirs_monitor, warfare, twitter_monitor,
vessel_incident_monitor/core.vessels.ais_source_observation,
news_monitor, ingestion_service) -- every field reflects what that
module's own code and docstrings actually say, not an invented
description. A source with no curated entry still appears (via
get_source_registry_catalog()) with its live operational health and an
explicitly ``None`` profile, never a fabricated one.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class SourceProfile:
    source_id: str
    name: str
    source_family: str
    source_type: str  # matches core.intel.source_registry's source_type convention
    operator: str
    geographic_coverage: str
    languages: tuple[str, ...]
    content_types: tuple[str, ...]
    collection_method: str
    polling_cadence_s: Optional[int]
    historical_coverage_start: Optional[str]
    privacy_constraints: str
    preservation_capability: bool
    independence_group: str
    known_limitations: tuple[str, ...] = field(default_factory=tuple)


SOURCE_CATALOG: dict[str, SourceProfile] = {
    "Alarm Phone": SourceProfile(
        source_id="alarm_phone", name="Alarm Phone",
        source_family="distress_network", source_type="twitter",
        operator="Alarm Phone / WatchTheMed", geographic_coverage="Mediterranean, Atlantic/Canary route",
        languages=("en", "ar", "fr"), content_types=("source_post",),
        collection_method="twikit (unofficial X client)",
        polling_cadence_s=None, historical_coverage_start=None,
        privacy_constraints="raw private caller text never published (core.live.projection)",
        preservation_capability=True, independence_group="x_twitter_platform",
        known_limitations=("depends on an unofficial X client (twikit), not the official API",),
    ),
    "X / Twitter": SourceProfile(
        source_id="x_twitter", name="X / Twitter",
        source_family="social_public_reports", source_type="twitter",
        operator="X Corp (via official API)", geographic_coverage="Mediterranean-focused search queries",
        languages=("en",), content_types=("source_post",),
        collection_method="official X API search",
        polling_cadence_s=None, historical_coverage_start=None,
        privacy_constraints="non-operational-context posts marked private, never published",
        preservation_capability=True, independence_group="x_twitter_platform",
        known_limitations=("keyword-query search, not a full-coverage stream",),
    ),
    "GDACS": SourceProfile(
        source_id="gdacs", name="GDACS",
        source_family="official_hazard_alerting", source_type="rss",
        operator="Global Disaster Alert and Coordination System (EU/UN)",
        geographic_coverage="global, filtered to Mediterranean-relevant hazard types",
        languages=("en",), content_types=("source_post",),
        collection_method="RSS poll", polling_cadence_s=None, historical_coverage_start=None,
        privacy_constraints="public institutional alerts only, no private content",
        preservation_capability=True, independence_group="gdacs",
        known_limitations=("only cyclone/earthquake/flood/volcano types are maritime-relevant here",),
    ),
    "GFW": SourceProfile(
        source_id="gfw", name="Global Fishing Watch",
        source_family="ais_derived_event", source_type="api",
        operator="Global Fishing Watch", geographic_coverage="Mediterranean + Black Sea bbox",
        languages=(), content_types=("ais_derived_event",),
        collection_method="GFW Events API (encounter/loitering/gap datasets)",
        polling_cadence_s=None, historical_coverage_start=None,
        privacy_constraints="vessel AIS identity is public maritime data",
        preservation_capability=False, independence_group="ais_derived",
        known_limitations=("requires GFW_API_TOKEN; silently no-ops without it",),
    ),
    "VIIRS VBD": SourceProfile(
        source_id="viirs_vbd", name="VIIRS Boat Detection",
        source_family="satellite_detection", source_type="api",
        operator="Earth Observation Group, Colorado School of Mines",
        geographic_coverage="Mediterranean + Black Sea bbox",
        languages=(), content_types=("satellite_detection",),
        collection_method="EOG VIIRS VBD nightly CSV download",
        polling_cadence_s=None, historical_coverage_start=None,
        privacy_constraints="no personal data -- vessel light detections only",
        preservation_capability=False, independence_group="viirs",
        known_limitations=(
            "public download is 45-days-delayed; near-real-time requires EOG_TOKEN",
            "no AIS match within 2km is the only dark-candidate signal -- no vessel identity",
        ),
    ),
    "ACLED": SourceProfile(
        source_id="acled", name="ACLED",
        source_family="conflict_event_data", source_type="api",
        operator="Armed Conflict Location & Event Data Project",
        geographic_coverage="Mediterranean + Black Sea bbox (lat 28-48, lon -8-45)",
        languages=("en",), content_types=("source_post",),
        collection_method="ACLED read API, 14-day lookback",
        polling_cadence_s=None, historical_coverage_start=None,
        privacy_constraints="public conflict-event data, no personal data",
        preservation_capability=False, independence_group="acled",
        known_limitations=("maritime relevance is a keyword heuristic on event text, not a native filter",),
    ),
    "NGA MSI": SourceProfile(
        source_id="nga_msi", name="NGA MSI Broadcast Warnings",
        source_family="official_navigational_warning", source_type="api",
        operator="US National Geospatial-Intelligence Agency",
        geographic_coverage="NAVAREA IV/XII, HYDROLANT/HYDROPAC, filtered to AOI",
        languages=("en",), content_types=("source_post",),
        collection_method="NGA MSI broadcast-warn API",
        polling_cadence_s=None, historical_coverage_start=None,
        privacy_constraints="public official navigational warnings only",
        preservation_capability=False, independence_group="nga_msi",
        known_limitations=("position extraction depends on a coordinate regex over free text",),
    ),
    "AISStream": SourceProfile(
        source_id="aisstream", name="AISStream",
        source_family="ais", source_type="ais",
        operator="aisstream.io (public AIS aggregator)",
        geographic_coverage="global AIS coverage, filtered to AOI",
        languages=(), content_types=("ais_position", "ais_nav_status"),
        collection_method="AISStream WebSocket (single connection, free tier)",
        polling_cadence_s=None, historical_coverage_start=None,
        privacy_constraints="public AIS transponder data",
        preservation_capability=True, independence_group="ais_terrestrial_satellite_aggregate",
        known_limitations=(
            "free tier allows only one socket per key -- every AIS-derived monitor shares it",
        ),
    ),
    "Official NGO RSS": SourceProfile(
        source_id="ngo_rss", name="Official NGO RSS",
        source_family="ngo_statement", source_type="rss",
        operator="various SAR NGOs", geographic_coverage="Mediterranean",
        languages=("en", "it", "de"), content_types=("source_post",),
        collection_method="RSS poll",
        polling_cadence_s=None, historical_coverage_start=None,
        privacy_constraints="public organisational statements only",
        preservation_capability=True, independence_group="ngo_rss",
    ),
}


def get_source_profile(source_name: str) -> Optional[dict[str, Any]]:
    profile = SOURCE_CATALOG.get(source_name)
    if profile is None:
        return None
    from core.intel.source_identity import resolve_source_identity

    identity = resolve_source_identity(profile.name)
    return {
        "source_id": profile.source_id,
        "source_identity": identity.identity_id,
        "source_role": identity.source_role,
        "may_open_incident": identity.may_open_incident,
        "name": profile.name,
        "source_family": profile.source_family,
        "source_type": profile.source_type,
        "operator": profile.operator,
        "geographic_coverage": profile.geographic_coverage,
        "languages": list(profile.languages),
        "content_types": list(profile.content_types),
        "collection_method": profile.collection_method,
        "polling_cadence_s": profile.polling_cadence_s,
        "historical_coverage_start": profile.historical_coverage_start,
        "privacy_constraints": profile.privacy_constraints,
        "preservation_capability": profile.preservation_capability,
        "independence_group": profile.independence_group,
        "known_limitations": list(profile.known_limitations),
    }


def get_source_registry_catalog() -> list[dict[str, Any]]:
    """The union of live operational health (core.intel.source_registry,
    already built) and this module's descriptive profile, per source
    actually registered at runtime. A registered source with no curated
    profile still appears -- with profile=None, never a fabricated
    description (docs/updates.md invariant #14: automation must not
    silently become canonical truth)."""
    from core.intel.source_registry import source_registry

    catalog = []
    seen_names = set()
    for source in source_registry.get_all():
        name = source.get("name", "")
        seen_names.add(name)
        catalog.append({
            "name": name,
            "operational": {
                "status": source.get("status"),
                "last_poll_at": source.get("last_poll_at"),
                "events_last_hour": source.get("events_last_hour"),
                "total_events": source.get("total_events"),
                "consecutive_errors": source.get("consecutive_errors"),
            },
            "profile": get_source_profile(name),
        })
    # Sources with a curated profile that have never registered at
    # runtime yet (e.g. GFW/VIIRS/ACLED/NGA MSI are best-effort and
    # silently no-op without their token/key configured) still belong in
    # "what SeaCommons is watching" -- shown with operational=None rather
    # than omitted.
    for name, profile in SOURCE_CATALOG.items():
        if name in seen_names:
            continue
        catalog.append({"name": name, "operational": None, "profile": get_source_profile(name)})
    return catalog
