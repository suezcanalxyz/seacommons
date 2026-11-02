# SPDX-License-Identifier: AGPL-3.0-or-later
"""Append-only case-review snapshots for a separately provisioned staging DB.

No engine creation, DDL, migration, scheduler, production writes, or publication.
Callers supply a transaction on a dedicated PostgreSQL database whose name ends
in _staging. A production database, even with a staging *schema*, is rejected.
The caller owns commit/rollback; this module never commits.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
import json
import re

from sqlalchemy import text

from core.domain.visual_category import CATEGORY_COLORS


_HEX = re.compile(r"[0-9a-f]{64}\Z")
_STAGE_DB = re.compile(r"[a-z][a-z0-9_]*_staging\Z")


@dataclass(frozen=True)
class StagingReviewSnapshot:
    snapshot_id: str
    case_review_id: str
    attack_observation_id: str
    evidence_ledger_sha256: str
    snapshot_sha256: str
    payload_json: str


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("staging_review_noncanonical_payload") from exc


def prepare_staging_review_snapshot(review: Mapping[str, object]) -> StagingReviewSnapshot:
    """Validate a derived case review and fingerprint its complete JSON payload.

    This does not authenticate the originating documents or certify witnesses.
    Any revised dossier becomes a *new* snapshot, never an overwrite.
    """
    if not isinstance(review, Mapping):
        raise ValueError("staging_review_mapping_required")
    if (
        review.get("staging_only") is not True
        or review.get("publication_allowed") is not False
        or review.get("ais_as_attack_proof") is not False
        or type(review.get("independent_origins_verified")) is not int
        or review["independent_origins_verified"] != 0
    ):
        raise ValueError("staging_review_publication_boundary")
    kind = review.get("proposed_incident_type")
    if kind not in {"maritime_attack", "piracy"}:
        raise ValueError("staging_review_attack_type_required")
    if review.get("review_color") != CATEGORY_COLORS[kind]:
        raise ValueError("staging_review_visual_category_conflict")
    case_id = review.get("case_review_id")
    observation_id = review.get("attack_observation_id")
    report_id = review.get("attack_report_id")
    if not all(isinstance(x, str) and x for x in (case_id, observation_id, report_id)):
        raise ValueError("staging_review_identity_required")
    if case_id != "staging-case-review:" + observation_id:
        raise ValueError("staging_review_case_id_conflict")

    ledger = review.get("source_evidence_ledger")
    if not isinstance(ledger, list) or not 1 <= len(ledger) <= 17:
        raise ValueError("staging_review_ledger_required")
    if not all(isinstance(entry, dict) for entry in ledger):
        raise ValueError("staging_review_ledger_entry_required")
    if any(
        entry.get("independent_attack_witness_verified") is not False
        or entry.get("publication_allowed") is not False
        or entry.get("republication_approved") is not False
        for entry in ledger
    ):
        raise ValueError("staging_review_untrusted_source_evidence")
    blockers = review.get("review_blockers")
    if (
        not isinstance(blockers, list)
        or "origin_independence_unverified" not in blockers
    ):
        raise ValueError("staging_review_independence_blocker_required")
    attack_entries = [
        entry for entry in ledger if entry.get("role") == "attack_candidate"
    ]
    if (
        len(attack_entries) != 1
        or attack_entries[0].get("canonical_observation_id") != observation_id
        or attack_entries[0].get("original_report_id") != report_id
    ):
        raise ValueError("staging_review_attack_ledger_mismatch")
    source_ids = [entry.get("canonical_observation_id") for entry in ledger]
    if (
        any(not isinstance(x, str) or not x for x in source_ids)
        or len(source_ids) != len(set(source_ids))
    ):
        raise ValueError("staging_review_duplicate_source")
    digest = sha256(_canonical_json(ledger).encode("utf-8")).hexdigest()
    if review.get("evidence_ledger_snapshot_sha256") != digest:
        raise ValueError("staging_review_evidence_digest_mismatch")
    if review.get("evidence_ledger_digest_is_original_document_proof") is not False:
        raise ValueError("staging_review_document_proof_claim")
    payload = _canonical_json(dict(review))
    snapshot_sha = sha256(payload.encode("utf-8")).hexdigest()
    snapshot_id = sha256((case_id + "\n" + snapshot_sha).encode("utf-8")).hexdigest()
    return StagingReviewSnapshot(
        snapshot_id=snapshot_id, case_review_id=case_id,
        attack_observation_id=observation_id,
        evidence_ledger_sha256=digest,
        snapshot_sha256=snapshot_sha, payload_json=payload,
    )


def append_staging_review_snapshot(
    connection: object,
    snapshot: StagingReviewSnapshot,
    *,
    expected_database: str,
) -> bool:
    """Insert an immutable review snapshot; return False on identical replay.

    Requires a dedicated PostgreSQL *_staging database and pre-provisioned
    attack_review_staging.review_snapshots table. No DDL or commit is performed.
    Never pass the production Oracle connection or a production DB URL here.
    """
    if not isinstance(snapshot, StagingReviewSnapshot):
        raise ValueError("staging_review_snapshot_required")
    try:
        revalidated = prepare_staging_review_snapshot(json.loads(snapshot.payload_json))
    except (TypeError, ValueError) as exc:
        raise ValueError("staging_review_snapshot_integrity") from exc
    if revalidated != snapshot:
        raise ValueError("staging_review_snapshot_integrity")
    if not isinstance(expected_database, str) or not _STAGE_DB.fullmatch(expected_database):
        raise ValueError("dedicated_staging_database_required")
    dialect = getattr(getattr(connection, "engine", None), "dialect", None)
    if getattr(dialect, "name", None) != "postgresql":
        raise ValueError("staging_review_postgresql_required")
    actual = connection.execute(text("SELECT current_database()")).scalar_one()
    if actual != expected_database:
        raise ValueError("staging_review_database_mismatch")
    readonly = connection.execute(text("SHOW transaction_read_only")).scalar_one()
    if readonly != "off":
        raise ValueError("staging_review_readonly_transaction")
    table = connection.execute(
        text("SELECT to_regclass('attack_review_staging.review_snapshots')")
    ).scalar_one()
    if table is None:
        raise ValueError("staging_review_schema_not_provisioned")
    # An append-only *table* is not enough: the connection role must be unable
    # to alter, remove or bypass the audit ledger, even through inherited grants.
    # This is a read-only privilege preflight; no DDL or privilege changes here.
    unsafe_role = connection.execute(text("""
        /* staging_review_role_privileges */
        SELECT CASE WHEN
            current_setting('is_superuser') = 'on'
            OR has_database_privilege(current_user, current_database(), 'CREATE')
            OR has_schema_privilege(current_user, 'attack_review_staging', 'CREATE')
            OR NOT has_schema_privilege(current_user, 'attack_review_staging', 'USAGE')
            OR NOT has_table_privilege(current_user,
                'attack_review_staging.review_snapshots', 'SELECT')
            OR NOT has_table_privilege(current_user,
                'attack_review_staging.review_snapshots', 'INSERT')
            OR has_table_privilege(current_user,
                'attack_review_staging.review_snapshots', 'UPDATE')
            OR has_table_privilege(current_user,
                'attack_review_staging.review_snapshots', 'DELETE')
            OR has_table_privilege(current_user,
                'attack_review_staging.review_snapshots', 'TRUNCATE')
            OR has_table_privilege(current_user,
                'attack_review_staging.review_snapshots', 'TRIGGER')
        THEN 1 ELSE 0 END
    """)).scalar_one()
    if unsafe_role != 0:
        raise ValueError("staging_review_role_not_append_only")
    inserted = connection.execute(text("""
        INSERT INTO attack_review_staging.review_snapshots
        (snapshot_id, case_review_id, attack_observation_id,
         evidence_ledger_sha256, snapshot_sha256, payload_json)
        VALUES (:snapshot_id, :case_review_id, :attack_observation_id,
                :evidence_ledger_sha256, :snapshot_sha256, :payload_json)
        ON CONFLICT (snapshot_id) DO NOTHING
        RETURNING snapshot_id
    """), {
        "snapshot_id": snapshot.snapshot_id,
        "case_review_id": snapshot.case_review_id,
        "attack_observation_id": snapshot.attack_observation_id,
        "evidence_ledger_sha256": snapshot.evidence_ledger_sha256,
        "snapshot_sha256": snapshot.snapshot_sha256,
        "payload_json": snapshot.payload_json,
    }).scalar_one_or_none()
    if inserted is not None:
        if inserted != snapshot.snapshot_id:
            raise ValueError("staging_review_insert_identity_mismatch")
        return True
    existing = connection.execute(text("""
        SELECT snapshot_sha256 FROM attack_review_staging.review_snapshots
        WHERE snapshot_id = :snapshot_id
    """), {"snapshot_id": snapshot.snapshot_id}).scalar_one_or_none()
    if existing != snapshot.snapshot_sha256:
        raise ValueError("staging_review_conflicting_replay")
    return False
