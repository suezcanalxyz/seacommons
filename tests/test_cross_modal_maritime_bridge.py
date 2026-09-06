from __future__ import annotations

from datetime import datetime, timezone

import pytest


def _feature(episode_id="episode:test:1"):
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [14.1, 35.5]},
        "properties": {
            "episode_id": episode_id,
            "episode_family": "gap_episode",
            "subject_ids": ["subj:mmsi:211879870"],
            "first_observed_at": "2026-09-06T18:00:00+00:00",
            "last_observed_at": "2026-09-06T19:00:00+00:00",
            "related_signal_ids": ["gap:a", "gap:b"],
            "independence_groups": ["ais_sensor_lineage"],
            "verification_status": "single_source_multi_indicator",
            "behaviour_context": {"baseline_status": "expected"},
        },
    }


def _ref(evidence_id, *, evidence_class, lineage, modality, derived=False):
    from core.evidence.cross_modal import EvidenceReference
    return EvidenceReference(
        evidence_id=evidence_id,
        evidence_class=evidence_class,
        source_lineage=lineage,
        modality=modality,
        observed_at=datetime(2026, 9, 6, 19, 10, tzinfo=timezone.utc),
        confidence=0.8,
        derived=derived,
    )


def _packet(episode_id="episode:test:1"):
    from core.evidence.cross_modal import CrossModalEvidencePacket
    return CrossModalEvidencePacket(
        subject_id=episode_id,
        evidence=(
            _ref("dsc:1", evidence_class="dsc_message", lineage="radio_receiver:rx_1", modality="radio"),
            _ref("navtex:1", evidence_class="navtex_message", lineage="radio_receiver:rx_2", modality="radio"),
            _ref("audio:1", evidence_class="audio_artifact", lineage="radio_receiver:rx_1", modality="audio"),
            _ref("atr:1", evidence_class="audio_transcript", lineage="radio_receiver:rx_1", modality="audio", derived=True),
        ),
        required_evidence_classes=("dsc_message", "verification_claim"),
        confidence_ceiling=0.75,
    )


@pytest.fixture(autouse=True)
def _tables():
    from core.db.models import InvestigationHypothesisDB, MaritimeEpisodeDB
    from core.db.session import engine, session_scope
    for table in (MaritimeEpisodeDB.__table__, InvestigationHypothesisDB.__table__):
        table.create(bind=engine(), checkfirst=True)
    with session_scope() as db:
        db.query(InvestigationHypothesisDB).delete()
        db.query(MaritimeEpisodeDB).delete()
    yield


def test_bridge_attaches_bounded_cross_modal_context_to_episode():
    from core.db.session import session_scope
    from core.evidence.cross_modal_analysis import evaluate_independence
    from core.evidence.maritime_bridge import attach_episode_context
    from core.intel.episode_store import save_episode

    before = save_episode(_feature())
    packet = _packet()
    updated = attach_episode_context(before.episode_id, packet, evaluate_independence(packet))
    context = updated.behaviour_context["cross_modal_context"]
    assert context["packet_id"] == packet.packet_id
    assert context["evidence_ids"] == ["atr:1", "audio:1", "dsc:1", "navtex:1"]
    assert context["evidence_classes"] == ["audio_artifact", "audio_transcript", "dsc_message", "navtex_message"]
    assert context["independent_group_count"] == 2
    assert context["modalities"] == ["audio", "radio"]
    assert context["missing_evidence_classes"] == ["verification_claim"]
    serialized = str(context).lower()
    assert "rx_1" not in serialized
    assert "receiver" not in serialized


def test_bridge_preserves_episode_identity_status_fingerprint_and_native_independence():
    from core.evidence.cross_modal_analysis import evaluate_independence
    from core.evidence.maritime_bridge import attach_episode_context
    from core.intel.episode_store import save_episode

    before = save_episode(_feature())
    packet = _packet()
    after = attach_episode_context(before.episode_id, packet, evaluate_independence(packet))
    assert after.episode_id == before.episode_id
    assert after.status == before.status
    assert after.verification_status == before.verification_status
    assert after.evidence_fingerprint == before.evidence_fingerprint
    assert after.observation_ids == before.observation_ids
    assert after.independence_groups == before.independence_groups
    assert after.behaviour_context["baseline_status"] == "expected"


def test_bridge_replay_is_idempotent():
    from core.evidence.cross_modal_analysis import evaluate_independence
    from core.evidence.maritime_bridge import attach_episode_context
    from core.intel.episode_store import save_episode

    row = save_episode(_feature())
    packet = _packet()
    analysis = evaluate_independence(packet)
    first = attach_episode_context(row.episode_id, packet, analysis)
    second = attach_episode_context(row.episode_id, packet, analysis)
    assert first.behaviour_context == second.behaviour_context


def test_bridge_rejects_wrong_subject_or_missing_episode():
    from core.evidence.cross_modal_analysis import evaluate_independence
    from core.evidence.maritime_bridge import attach_episode_context
    from core.intel.episode_store import save_episode

    row = save_episode(_feature())
    wrong = _packet("episode:other")
    with pytest.raises(ValueError, match="subject"):
        attach_episode_context(row.episode_id, wrong, evaluate_independence(wrong))
    good = _packet("episode:missing")
    with pytest.raises(ValueError, match="not found"):
        attach_episode_context("episode:missing", good, evaluate_independence(good))


def test_bridge_never_mutates_linked_hypothesis_state_or_evidence_links():
    from core.db.models import InvestigationHypothesisDB
    from core.db.session import session_scope
    from core.evidence.cross_modal_analysis import evaluate_independence
    from core.evidence.maritime_bridge import attach_episode_context
    from core.intel.episode_store import save_episode

    row = save_episode(_feature())
    with session_scope() as db:
        db.add(InvestigationHypothesisDB(
            hypothesis_id="hyp:test", episode_id=row.episode_id, hypothesis_type="gap",
            subject_ids=["subj:mmsi:211879870"], state="candidate", reason_codes=["gap"],
            counter_indicators=[], evidence_links=["gap:a", "gap:b"], evidence_stage="observed",
            has_unresolved_blocking_identity_conflict=False, allegation_shaped_wording=False,
            explicit_review_done=False, audit_history=[],
        ))
    packet = _packet()
    attach_episode_context(row.episode_id, packet, evaluate_independence(packet))
    with session_scope() as db:
        hyp = db.get(InvestigationHypothesisDB, "hyp:test")
        assert hyp.state == "candidate"
        assert hyp.evidence_stage == "observed"
        assert hyp.evidence_links == ["gap:a", "gap:b"]
        assert hyp.explicit_review_done is False
