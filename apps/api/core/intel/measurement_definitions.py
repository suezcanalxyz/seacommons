# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared evidence classification rules for SeaCommons measurements.

These classify current IntelEvent rows. They do not provide a transition log,
an immutable ingestion total, or proof that any underlying observation is true.
"""
DERIVED_EVENT_TYPES = frozenset({
    "ais_anomaly", "ais_rendezvous", "correlated_alert",
    "dark_candidate", "vessel_identity", "sar_model",
})
DERIVED_ANALYSIS_STATES = ("anomaly", "evidence_candidate", "evidence")
