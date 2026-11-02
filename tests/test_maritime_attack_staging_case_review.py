# SPDX-License-Identifier: AGPL-3.0-or-later
"""Regression: attack, subsequent wreck, investigation and AIS remain distinct."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase

from core.intel.maritime_attack_correlation import VesselRef
from core.intel.maritime_attack_staging_ais_context import build_staging_ais_context
from core.intel.maritime_attack_staging_case_review import build_staging_attack_case_review
from core.intel.maritime_attack_staging_manifest import prepare_staging_bulletin_manifest
from core.intel.maritime_attack_staging_preview import build_staging_attack_previews

DOCS = Path(__file__).resolve().parents[1] / "docs/research"


def _preview(filename: str, index: int = 0):
    manifest = json.loads((DOCS / filename).read_text())
    record = prepare_staging_bulletin_manifest(manifest)[index]
    e = record.envelope
    key = f'{e["source_name"]}:{e["source_id"]}'
    row = SimpleNamespace(
        observation_id="obs:" + hashlib.blake2s(key.encode(), digest_size=16).hexdigest(),
        service=e["service"], lane=e["lane"], observation_type=e["observation_type"],
        source_policy=e["source_policy"], source_name=e["source_name"],
        source_id=e["source_id"], source_url=e["source_url"],
        raw_payload_hash=hashlib.sha256(e["raw_payload"].encode()).hexdigest(),
        subject_refs=e["subject_refs"], provenance=e["provenance"],
        observed_at=e["observed_at"], lat=e["lat"], lon=e["lon"],
        uncertainty_m=e["uncertainty_m"], location_precision=None,
        received_at=datetime(2026, 11, 2, 6, 0, tzinfo=timezone.utc),
    )
    return build_staging_attack_previews([record], [row])[0]


def _attack():
    return _preview("maritime-attack-source-check-2026-11-01.json")


def _navwarn():
    return _preview("maritime-attack-varna-navwarn-768-2026-11-02.json")


def _prosecutor():
    return _preview("maritime-attack-prosecutor-source-check-2026-11-02.json")


def _rescue():
    return _preview("maritime-attack-transport-rescue-2026-11-02.json")


def _ais(attack):
    return build_staging_ais_context(
        attack, VesselRef(imo="9348625", mmsi="636019532", name="CONTSHIP JET"),
        [
            SimpleNamespace(
                mmsi="636019532", ts=datetime(2026, 10, 28, 9, 59, 22),
                received_at=datetime(2026, 10, 28, 9, 59, 22),
                lat=43.2659267, lon=28.8149, sog=10.2
            ),
            SimpleNamespace(
                mmsi="636019532", ts=datetime(2026, 10, 28, 10, 34, 46),
                received_at=datetime(2026, 10, 28, 10, 34, 46),
                lat=43.2591967, lon=28.81574, sog=0.6
            ),
        ],
        crosswalk_source_url="https://www.vtmis.bg/wx/wx_eng.htm",
    )


class StagingCaseReviewTests(TestCase):
    def test_contship_jet_attack_wreck_prosecutor_and_ais_are_distinct(self):
        attack, navwarn, prosecutor, rescue = (
            _attack(), _navwarn(), _prosecutor(), _rescue()
        )
        result = build_staging_attack_case_review(
            attack, [prosecutor, navwarn, rescue], ais_context=_ais(attack)
        )
        self.assertEqual(result["attack_at_utc"], "2026-10-28T10:00:00+00:00")
        self.assertEqual(result["proposed_incident_type"], "maritime_attack")
        self.assertEqual(result["review_color"], "#ff6b35")
        self.assertEqual(result["official_imo_from_documents"], "9348625")
        self.assertEqual(result["external_mmsi_proposed"], "636019532")
        self.assertEqual(result["identity_status"], "requires_manual_review")
        self.assertIsNone(result["attack_reported_location"])
        self.assertEqual(len(result["followups"]), 3)
        hazard = next(f for f in result["followups"] if f["source_kind"] == "navigational_hazard")
        self.assertEqual(hazard["minutes_after_attack"], 630)
        self.assertEqual(hazard["reported_location"]["role"], "hazard_position")
        self.assertAlmostEqual(hazard["reported_location"]["lat"], 43.13)
        self.assertEqual(hazard["role"], "later_hazard_not_attack")
        self.assertFalse(hazard["attack_witness"])
        spatial = hazard["ais_to_hazard_nominal_context"]
        self.assertGreater(spatial["nominal_separation_km"], 10)
        self.assertLess(spatial["nominal_separation_km"], 20)
        self.assertGreater(spatial["elapsed_hours"], 9)
        self.assertLess(spatial["elapsed_hours"], 11)
        self.assertEqual(spatial["uncertainty_status"], "not_quantified")
        self.assertFalse(spatial["route_or_attack_site_inferred"])
        self.assertFalse(spatial["independent_attack_witness"])
        prosecutor_notice = next(f for f in result["followups"] if f["source_kind"] == "investigation")
        self.assertIsNone(prosecutor_notice["minutes_after_attack"])
        self.assertEqual(prosecutor_notice["publication_date"], "2026-10-29")
        rescue = next(f for f in result["followups"] if f["source_kind"] == "rescue")
        self.assertEqual(rescue["publication_date"], "2026-10-28")
        self.assertIsNone(rescue["occurred_at_utc"])
        self.assertIsNone(rescue["minutes_after_attack"])
        self.assertEqual(rescue["role"], "rescue_not_attack_witness")
        self.assertFalse(rescue["attack_witness"])
        self.assertEqual(result["independent_origins_verified"], 0)
        self.assertFalse(result["ais_as_attack_proof"])
        self.assertFalse(result["publication_allowed"])
        self.assertTrue(result["staging_only"])
        self.assertTrue(result["ais_context"]["sudden_stop_signal"])
        self.assertIn("wreck_or_hazard_site_not_attack_site", result["review_blockers"])
        self.assertIn("origin_independence_unverified", result["review_blockers"])

    def test_context_exact_clock_cannot_precede_attack_or_publication(self):
        attack, rescue = _attack(), _rescue()
        for stamp, error in (
            ("2026-10-28T09:59:00+00:00", "context_exact_clock_precedes_attack"),
            ("2026-10-29T12:00:00+00:00", "context_exact_clock_after_publication"),
        ):
            with self.subTest(stamp=stamp), self.assertRaisesRegex(ValueError, error):
                build_staging_attack_case_review(
                    attack, [{**rescue, "occurred_at_utc": stamp}]
                )
        with self.assertRaisesRegex(ValueError, "context_exact_clock_conflicts_with_event_day"):
            build_staging_attack_case_review(
                attack, [{**rescue, "occurred_at_utc": "2026-10-29T10:00:00+00:00",
                          "publication_date": "2026-10-29"}]
            )

    def test_rescue_or_investigation_location_cannot_be_attack_site(self):
        attack, rescue, prosecutor = _attack(), _rescue(), _prosecutor()
        for context in (rescue, prosecutor):
            with self.subTest(kind=context["source_kind"]), self.assertRaisesRegex(
                ValueError, "followup_location_cannot_be_attack_site"
            ):
                build_staging_attack_case_review(
                    attack, [{**context, "reported_location": {
                        "lat": 43.13, "lon": 28.756, "role": "incident_site"
                    }}]
                )

    def test_case_evidence_ledger_preserves_source_clocks_rights_and_lineage(self):
        attack, navwarn, prosecutor, rescue = (
            _attack(), _navwarn(), _prosecutor(), _rescue()
        )
        result = build_staging_attack_case_review(
            attack, [navwarn, prosecutor, rescue], ais_context=_ais(attack)
        )
        ledger = result["source_evidence_ledger"]
        self.assertEqual(len(ledger), 4)
        self.assertEqual(len({x["original_report_id"] for x in ledger}), 4)
        self.assertEqual(len(result["evidence_ledger_snapshot_sha256"]), 64)
        self.assertFalse(result["evidence_ledger_digest_is_original_document_proof"])
        for item in ledger:
            self.assertTrue(item["source_url"].startswith("https://"))
            self.assertEqual(len(item["canonical_metadata_sha256"]), 64)
            self.assertTrue(item["received_at_utc"].endswith("+00:00"))
            self.assertIsNotNone(item["source_checked_on_utc"])
            self.assertIsNotNone(item["source_rights"])
            self.assertFalse(item["independent_attack_witness_verified"])
            self.assertFalse(item["republication_approved"])
            self.assertFalse(item["publication_allowed"])
        original = next(x for x in ledger if x["role"] == "attack_candidate")
        self.assertEqual(original["occurred_at_utc"], "2026-10-28T10:00:00+00:00")
        self.assertEqual(original["original_report_id"], attack["original_report_id"])
        self.assertEqual(original["original_document_sha256"], attack["source_document_sha256"])
        rescue_entry = next(x for x in ledger if x["source_kind"] == "rescue")
        self.assertIsNone(rescue_entry["occurred_at_utc"])
        self.assertEqual(rescue_entry["event_date"], "2026-10-28")
        self.assertEqual(rescue_entry["source_rights"], "public_with_attribution")

    def test_case_evidence_ledger_is_deterministic_and_sensitive_to_provenance(self):
        attack, navwarn, prosecutor = _attack(), _navwarn(), _prosecutor()
        a = build_staging_attack_case_review(attack, [navwarn, prosecutor])
        b = build_staging_attack_case_review(attack, [prosecutor, navwarn])
        self.assertEqual(a["source_evidence_ledger"], b["source_evidence_ledger"])
        self.assertEqual(a["evidence_ledger_snapshot_sha256"], b["evidence_ledger_snapshot_sha256"])
        changed = build_staging_attack_case_review(
            {**attack, "source_url": "https://www.mod.bg/alternate-source"},
            [navwarn, prosecutor]
        )
        self.assertNotEqual(
            a["evidence_ledger_snapshot_sha256"],
            changed["evidence_ledger_snapshot_sha256"]
        )

    def test_case_evidence_ledger_rejects_missing_or_tampered_provenance(self):
        attack = _attack()
        bad_values = (
            ("raw_payload_hash", "bad"),
            ("source_document_sha256", "not-a-sha256"),
            ("source_rights", ""),
            ("source_checked_on_utc", "not-a-date"),
            ("received_at_utc", "2026-10-27T12:00:00+00:00"),
            ("received_at_utc", "2026-11-02"),
            ("source_url", "http://insecure.example/notice"),
        )
        for field, value in bad_values:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                build_staging_attack_case_review({**attack, field: value}, [])

    def test_followup_order_does_not_change_bundle(self):
        attack, navwarn, prosecutor, rescue = (
            _attack(), _navwarn(), _prosecutor(), _rescue()
        )
        first = build_staging_attack_case_review(attack, [navwarn, prosecutor, rescue])
        second = build_staging_attack_case_review(attack, [rescue, prosecutor, navwarn])
        self.assertEqual(first, second)

    def test_transport_ministry_rescue_is_day_only_context_not_attack(self):
        rescue = _rescue()
        self.assertEqual(rescue["source_kind"], "rescue")
        self.assertEqual(rescue["review_status"], "context_only")
        self.assertIsNone(rescue["proposed_incident_type"])
        self.assertEqual(rescue["event_date"], "2026-10-28")
        self.assertIsNone(rescue["occurred_at_utc"])
        self.assertEqual(rescue["source_rights"], "public_with_attribution")
        self.assertFalse(rescue["publication_allowed"])
        self.assertEqual(rescue["independent_origins_verified"], 0)

    def test_transport_ministry_lookalike_domain_is_rejected(self):
        manifest = json.loads(
            (DOCS / "maritime-attack-transport-rescue-2026-11-02.json").read_text()
        )
        manifest["records"][0]["source_url"] = (
            "https://mtc.government.bg.evil.example/contship-jet"
        )
        with self.assertRaisesRegex(ValueError, "official"):
            prepare_staging_bulletin_manifest(manifest)

    def test_unrelated_vessel_and_unnamed_drifting_container_rejected(self):
        attack, navwarn = _attack(), _navwarn()
        for bad in (
            {**navwarn, "vessel_name_as_reported": "KHORYV"},
            {**navwarn, "vessel_name_as_reported": ""},
        ):
            with self.subTest(bad=bad["vessel_name_as_reported"]), self.assertRaisesRegex(
                ValueError, "context_vessel_identity_conflict"
            ):
                build_staging_attack_case_review(attack, [bad])

    def test_conflicting_official_imo_or_crosswalk_rejected(self):
        attack, navwarn = _attack(), _navwarn()
        with self.assertRaisesRegex(ValueError, "conflicting_official_imo"):
            build_staging_attack_case_review(
                {**attack, "vessel_imo_as_reported": "8138712"}, [navwarn]
            )
        ais = _ais(attack)
        with self.assertRaisesRegex(ValueError, "official_imo_conflicts"):
            build_staging_attack_case_review(
                attack, [navwarn],
                ais_context={**ais, "crosswalk": {**ais["crosswalk"], "imo": "8138712"}}
            )

    def test_attack_bulletin_is_not_context_or_independent_witness(self):
        attack = _attack()
        another_attack = _preview("maritime-attack-source-check-2026-11-01.json", 1)
        with self.assertRaisesRegex(ValueError, "attack_witness_must_not_be_followup"):
            build_staging_attack_case_review(attack, [another_attack])

    def test_duplicate_followup_and_self_link_rejected(self):
        attack, navwarn = _attack(), _navwarn()
        for docs in ([navwarn, navwarn], [attack]):
            with self.assertRaises(ValueError):
                build_staging_attack_case_review(attack, docs)

    def test_hazard_before_attack_or_fake_attack_location_rejected(self):
        attack, navwarn = _attack(), _navwarn()
        for bad in (
            {**navwarn, "occurred_at_utc": "2026-10-27T20:30:00Z"},
            {**navwarn, "reported_location": {
                **navwarn["reported_location"], "role": "incident_site"
            }},
        ):
            with self.assertRaises(ValueError):
                build_staging_attack_case_review(attack, [bad])

    def test_foreign_ais_context_and_promotion_rejected(self):
        attack, navwarn = _attack(), _navwarn()
        ais = _ais(attack)
        for bad in (
            {**ais, "canonical_observation_id": "obs:foreign"},
            {**ais, "publication_allowed": True},
            {**ais, "independent_origins_verified": 2},
            {**ais, "ais_as_attack_proof": True},
        ):
            with self.assertRaisesRegex(ValueError, "foreign_or_publishable_ais_context"):
                build_staging_attack_case_review(attack, [navwarn], ais_context=bad)
        with self.assertRaisesRegex(ValueError, "untrusted_or_publishable"):
            build_staging_attack_case_review({**attack, "publication_allowed": True}, [navwarn])

    def test_rescue_from_before_attack_is_not_a_followup(self):
        attack, rescue = _attack(), _rescue()
        with self.assertRaisesRegex(ValueError, "context_event_not_after_attack"):
            build_staging_attack_case_review(
                attack, [{**rescue, "event_date": "2026-10-27"}]
            )

    def test_malformed_crosswalk_or_ais_coordinate_rejected(self):
        attack, navwarn = _attack(), _navwarn()
        ais = _ais(attack)
        for bad in (
            {**ais, "crosswalk": {**ais["crosswalk"], "imo": None}},
            {**ais, "crosswalk": {**ais["crosswalk"], "mmsi": 636019532}},
        ):
            with self.assertRaisesRegex(ValueError, "unreviewed_or_conflicting_ais_crosswalk"):
                build_staging_attack_case_review(attack, [navwarn], ais_context=bad)
        invalid_fix = {**ais["nearest_after"], "lat": 999.0}
        with self.assertRaisesRegex(ValueError, "invalid_contextual_position"):
            build_staging_attack_case_review(
                attack, [navwarn], ais_context={**ais, "nearest_after": invalid_fix}
            )

    def test_future_ais_fix_is_rejected_before_wreck_comparison(self):
        attack, navwarn = _attack(), _navwarn()
        ais = _ais(attack)
        later_fix = {**ais["nearest_after"],
                     "observed_at_utc": "2026-10-29T20:00:00+00:00"}
        with self.assertRaisesRegex(ValueError, "ais_context_fix_outside_event_window"):
            build_staging_attack_case_review(
                attack, [navwarn], ais_context={**ais, "nearest_after": later_fix}
            )

    def test_case_review_rejects_tampered_ais_context_signals(self):
        attack, navwarn = _attack(), _navwarn()
        ais = _ais(attack)
        alterations = (
            ({"event_at_utc": "2026-10-28T11:00:00+00:00"},
             "ais_context_event_or_geometry_conflict"),
            ({"incident_site_from_ais": True}, "ais_context_event_or_geometry_conflict"),
            ({"ais_sampling_gap_minutes": 1.0}, "ais_context_sampling_gap_conflict"),
            ({"ais_coverage_gap_signal": False}, "ais_context_coverage_signal_conflict"),
            ({"sudden_stop_signal": False}, "ais_context_sudden_stop_conflict"),
            ({"ais_kinematic_conflict_signal": True}, "ais_context_sudden_stop_conflict"),
            ({"ais_fixes_in_6h_window": 1}, "ais_context_fix_count_conflict"),
            ({"receipt_latency_status": "verified_live"}, "invalid_ais_context_receipt_status"),
        )
        for patch, error in alterations:
            with self.subTest(patch=patch), self.assertRaisesRegex(ValueError, error):
                build_staging_attack_case_review(attack, [navwarn], ais_context={**ais, **patch})

    def test_case_review_rejects_forged_ais_fix_chronology_and_speed(self):
        attack, navwarn = _attack(), _navwarn()
        ais = _ais(attack)
        altered_fixes = (
            ("nearest_before", {"observed_at_utc": "2026-10-28T10:10:00+00:00"},
             "ais_context_fix_chronology_conflict"),
            ("nearest_after", {"sog_knots": 150.0}, "invalid_ais_context_speed"),
            ("nearest_after", {"position_role": "incident_site"}, "invalid_ais_context_fix"),
        )
        for key, patch, error in altered_fixes:
            with self.subTest(key=key, patch=patch), self.assertRaisesRegex(ValueError, error):
                changed = {**ais, key: {**ais[key], **patch}}
                build_staging_attack_case_review(attack, [navwarn], ais_context=changed)

    def test_no_followup_keeps_imo_and_mmsi_unverified(self):
        result = build_staging_attack_case_review(_attack(), [])
        self.assertIsNone(result["official_imo_from_documents"])
        self.assertIsNone(result["external_mmsi_proposed"])
        self.assertEqual(result["independent_origins_verified"], 0)
        self.assertFalse(result["publication_allowed"])

    def test_spatial_ledger_tracks_original_hazard_coordinates(self):
        attack, navwarn = _attack(), _navwarn()
        original = build_staging_attack_case_review(attack, [navwarn])
        entry = next(item for item in original["source_evidence_ledger"]
                     if item["source_kind"] == "navigational_hazard")
        self.assertEqual(entry["reported_location"]["role"], "hazard_position")
        self.assertAlmostEqual(entry["reported_location"]["lat"], 43.13)
        self.assertEqual(entry["vessel_imo_as_reported"], "9348625")
        revised = {**navwarn, "reported_location": {
            **navwarn["reported_location"], "lat": 43.131
        }}
        changed = build_staging_attack_case_review(attack, [revised])
        self.assertNotEqual(original["evidence_ledger_snapshot_sha256"],
                            changed["evidence_ledger_snapshot_sha256"])
        self.assertFalse(changed["publication_allowed"])

    def test_spatial_ledger_rejects_invalid_source_geometry(self):
        attack, navwarn = _attack(), _navwarn()
        for bad in (
            {"lat": 91.0}, {"lon": float("nan")},
            {"uncertainty_km": -1.0}, {"lat": True},
        ):
            location = {**navwarn["reported_location"], **bad}
            with self.subTest(bad=bad), self.assertRaisesRegex(
                ValueError, "invalid_source"
            ):
                build_staging_attack_case_review(
                    attack, [{**navwarn, "reported_location": location}]
                )

    def test_able_inspection_is_day_only_context_not_attack_candidate(self):
        able = _preview("maritime-attack-able-damage-assessment-2026-11-02.json")
        self.assertEqual(able["source_kind"], "damage_assessment")
        self.assertEqual(able["vessel_name_as_reported"], "ABLE")
        self.assertIsNone(able["occurred_at_utc"])
        self.assertEqual(able["event_date"], "2026-10-09")
        self.assertIsNone(able["vessel_imo_as_reported"] or None)
        self.assertEqual(able["review_status"], "context_only")
        self.assertFalse(able["publication_allowed"])
        with self.assertRaisesRegex(ValueError, "attack_candidate_required"):
            build_staging_attack_case_review(able, [])
        with self.assertRaisesRegex(ValueError, "context_vessel_identity_conflict"):
            build_staging_attack_case_review(_attack(), [able])

    def test_alfa_watan_is_not_same_vessel_as_able_or_contship(self):
        attack, navwarn = _attack(), _navwarn()
        with self.assertRaisesRegex(ValueError, "context_vessel_identity_conflict"):
            build_staging_attack_case_review(
                attack, [{**navwarn, "vessel_name_as_reported": "ALFA WATAN"}]
            )


    def test_unnamed_mscio_164_review_preserves_approximate_clock_without_identity(self):
        attack = _preview("maritime-attack-mscio-164-2026-11-02.json")
        review = build_staging_attack_case_review(attack, [])
        self.assertEqual(review["attack_report_id"], "MSCIO:164/26")
        self.assertEqual(review["attack_at_utc"], "2026-11-01T15:09:00+00:00")
        self.assertEqual(review["attack_time_precision"], "approximate")
        self.assertEqual(review["attack_event_date"], "2026-11-01")
        self.assertEqual(review["identity_status"], "unidentified_vessel")
        self.assertEqual(review["vessel_name_as_reported"], "")
        self.assertIsNone(review["official_imo_from_documents"])
        self.assertIsNone(review["external_mmsi_proposed"])
        self.assertIsNone(review["ais_context"])
        self.assertIsNone(review["attack_reported_location"])
        self.assertEqual(review["independent_origins_verified"], 0)
        self.assertFalse(review["publication_allowed"])
        self.assertIn("unidentified_vessel_no_ais_or_followup_linkage", review["review_blockers"])
        self.assertEqual(len(review["source_evidence_ledger"]), 1)

    def test_day_only_mscio_163_review_does_not_invent_attack_hour(self):
        attack = _preview("maritime-attack-mscio-163-2026-11-02.json")
        review = build_staging_attack_case_review(attack, [])
        self.assertIsNone(review["attack_at_utc"])
        self.assertEqual(review["attack_event_date"], "2026-10-28")
        self.assertEqual(review["attack_time_precision"], "day")
        self.assertEqual(review["identity_status"], "unidentified_vessel")
        self.assertIn("day_only_event_time_no_temporal_correlator", review["review_blockers"])
        self.assertFalse(review["publication_allowed"])

    def test_unidentified_attack_cannot_inherit_foreign_followup_or_ais(self):
        attack = _preview("maritime-attack-mscio-164-2026-11-02.json")
        for kwargs in ({"context_previews": [_navwarn()]},
                       {"context_previews": [], "ais_context": _ais(_attack())}):
            with self.subTest(kwargs=tuple(kwargs)), self.assertRaisesRegex(
                ValueError, "unidentified_vessel_cannot_link_context_or_ais"
            ):
                build_staging_attack_case_review(attack, **kwargs)

    def test_day_only_attack_rejects_fabricated_or_invalid_event_day(self):
        attack = _preview("maritime-attack-mscio-163-2026-11-02.json")
        for event_day in (None, "2026-10-99", "2026-10-28T00:00:00Z"):
            with self.subTest(day=event_day), self.assertRaises(ValueError):
                build_staging_attack_case_review({**attack, "event_date": event_day}, [])
        with self.assertRaisesRegex(ValueError, "day_only_attack_cannot_link_context_or_ais"):
            named = {**attack, "vessel_name_as_reported": "EXAMPLE"}
            build_staging_attack_case_review(named, [_navwarn()])

    def test_approximate_clock_cannot_be_laundered_as_day_or_other_date(self):
        attack = _preview("maritime-attack-mscio-164-2026-11-02.json")
        for patch, error in (
            ({"event_time_precision": "day"}, "attack_clock_precision_conflict"),
            ({"event_date": "2026-11-02"}, "attack_clock_day_conflict"),
        ):
            with self.subTest(patch=patch), self.assertRaisesRegex(ValueError, error):
                build_staging_attack_case_review({**attack, **patch}, [])
