# SPDX-License-Identifier: AGPL-3.0-or-later
"""Traceable confidence scoring — docs/prompt.md Phase 9.

Additive alongside the existing severity tier (low/medium/high/critical),
not a replacement of it yet. Every score names WHY it landed where it did
instead of being one opaque number a detector invented inline — the
pre-existing pattern this replaces (see scan_gaps' old inline formula,
scan_spoofing's severity-from-jamming-alone with no confidence at all).

This module computes and stores; it does not change public-feed
eligibility, severity thresholds, or publication behaviour anywhere it is
wired in — shadow mode, per docs/prompt.md section "SHADOW MODE": build the
new model alongside the old one, let it prove itself, cut over later as its
own separate, deliberate change.

Every component is 0.0-1.0. The combined score is a weighted mean, not a
product — one weak component (e.g. a source that is merely "derived" rather
than "official_api") should pull the score down, not multiply it toward
zero the way independent-probability multiplication would for signals that
are not actually independent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

CLASSIFICATION_VERSION = "v1-shadow"

# ── component: source reliability ──────────────────────────────────────────
# Mirrors core.domain.live_contracts.APPROVED_SOURCE_POLICIES' ordering of
# how much a source_policy is trusted, expressed as a number instead of a
# yes/no gate.
_SOURCE_RELIABILITY = {
    "official_api": 0.95,       # AIS transponder, official registry lookups
    "official_rss": 0.85,       # ACLED, GDACS, vetted RSS
    "official_site_embed": 0.85,
    "operator_published": 0.9,  # a human reviewed and approved it
    "derived": 0.7,             # computed from official_api data, one step removed
    "unofficial": 0.35,
}


def source_reliability(source_policy: str) -> float:
    return _SOURCE_RELIABILITY.get(str(source_policy or "").lower(), 0.5)


# ── component: observation freshness ───────────────────────────────────────
def observation_freshness(age_seconds: float, *, half_life_s: float = 4 * 3600) -> float:
    """1.0 for a fresh observation, decaying toward 0.2 as it ages.

    half_life_s: age at which freshness has dropped to ~0.6 (chosen so a
    gap first seen 4h ago -- the old scan_gaps default window -- still
    reads as moderately fresh, matching its previous inline formula).
    """
    age = max(0.0, float(age_seconds))
    decayed = 0.9 * (0.5 ** (age / max(1.0, half_life_s)))
    return round(max(0.2, min(1.0, 0.2 + decayed)), 3)


# ── component: rule strength ───────────────────────────────────────────────
# How strong the underlying rule's evidence is in principle, independent of
# this specific instance's data quality. A named table instead of a magic
# number scattered per call site, so the same rule always contributes the
# same base strength and a reviewer can see every rule's weight in one place.
_RULE_STRENGTH = {
    "ais_gap": 0.6,                 # a single transponder silence, many causes
    "ais_gap_long": 0.7,            # sustained silence, fewer benign explanations
    "spoof_teleport": 0.85,         # an impossible-speed jump is hard to fake benignly
    "spoof_circular": 0.55,         # shares its signature with legitimate anchoring/trawling
    "spoof_frozen": 0.55,
    "infra_loiter": 0.6,
    "sanctions_bunkering_loiter": 0.8,  # sanctions match + zone together, not proximity alone
    "rendezvous": 0.65,
    "identity_screen": 0.5,
}


def rule_strength(rule_id: str) -> float:
    return _RULE_STRENGTH.get(rule_id, 0.5)


# ── component: persistence ─────────────────────────────────────────────────
def persistence(sample_count: int, duration_s: float, *, min_samples: int = 3, min_duration_s: float = 600) -> float:
    """More independent fixes over more time = a pattern, not one noisy read."""
    sample_score = min(1.0, sample_count / max(1, min_samples))
    duration_score = min(1.0, max(0.0, duration_s) / max(1.0, min_duration_s))
    return round(max(0.2, 0.3 + 0.35 * sample_score + 0.35 * duration_score), 3)


# ── component: location precision ──────────────────────────────────────────
_LOCATION_PRECISION = {
    "ais_position": 0.95,
    "reported_or_derived": 0.75,
    "media_ocr_text": 0.55,
    "region_area": 0.4,
    "post_text": 0.5,
    "approximate": 0.4,
}


def location_precision_score(coordinate_source: str) -> float:
    return _LOCATION_PRECISION.get(str(coordinate_source or "").lower(), 0.5)


# ── component: independent corroboration ───────────────────────────────────
def independent_corroboration(corroborating_source_count: int) -> float:
    """0 extra sources = 0.4 (uncorroborated); each independent source adds,
    capped at 1.0."""
    return round(min(1.0, 0.4 + 0.25 * max(0, corroborating_source_count)), 3)


# ── component: coverage quality ─────────────────────────────────────────────
def coverage_quality(jamming_score: float) -> float:
    """GNSS jamming in the area makes an AIS anomaly here less trustworthy as
    a deliberate signal -- it may just be reception loss. jamming_score is
    already 0 (clear) .. 1 (heavily jammed)."""
    return round(max(0.2, 1.0 - max(0.0, min(1.0, jamming_score))), 3)


# ── component: contradicting evidence ───────────────────────────────────────
def contradicting_evidence_penalty(contradicting_count: int) -> float:
    """1.0 = nothing contradicts this reading; each contradicting signal
    pulls it down, floor 0.1 (never fully zero out an otherwise-strong
    reading from one disagreeing source)."""
    return round(max(0.1, 1.0 - 0.3 * max(0, contradicting_count)), 3)


@dataclass
class ConfidenceScore:
    value: float
    components: dict[str, float] = field(default_factory=dict)
    rule_id: str = ""
    classification_version: str = CLASSIFICATION_VERSION

    def as_metadata(self) -> dict[str, Any]:
        return {
            "confidence": round(self.value, 3),
            "confidence_components": {k: round(v, 3) for k, v in self.components.items()},
            "rule_id": self.rule_id,
            "classification_version": self.classification_version,
        }


def combine(rule_id: str, **components: float) -> ConfidenceScore:
    """Weighted mean of named components. Every component contributes
    equally by default -- a detector can pass a subset of the available
    components (not every rule has all of them, e.g. a gap has no
    'independent_corroboration' input) and the mean is over whichever were
    actually supplied, not diluted by absent ones defaulting to some
    arbitrary value."""
    if not components:
        return ConfidenceScore(value=0.5, components={}, rule_id=rule_id)
    value = sum(components.values()) / len(components)
    return ConfidenceScore(
        value=round(max(0.0, min(1.0, value)), 3),
        components=components,
        rule_id=rule_id,
    )
