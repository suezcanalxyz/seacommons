# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bounded batched read-only provenance audits for public attack episodes.

A single catalog request may contain several attack episodes. Fetch canonical
observations once and traverse the union of their lineage frontiers, then
re-evaluate each episode independently. No collector, DB write, timer, or
publication side effect. Truncated batches fail closed.
"""
from __future__ import annotations

from typing import Callable, Iterable, Sequence

from core.intel.maritime_attack_independence_readonly import (
    IndependenceAudit, audit_attack_episode_independence,
)
from core.intel.maritime_attack_play_guard import (
    _ATTACK_FAMILIES, has_distinct_independence_groups,
)

_MAX_EPISODES = 8
_MAX_OBSERVATIONS_PER_EPISODE = 32
_MAX_LINEAGE_DEPTH = 8
_MAX_TOTAL_NODES = 2048
_MAX_TOTAL_EDGES = 8192


def _blocked(episodes: Sequence[object], reason: str) -> dict[str, IndependenceAudit]:
    return {
        str(getattr(episode, "episode_id", "") or ""): IndependenceAudit(False, reason=reason)
        for episode in episodes
    }


def audit_attack_episodes_independence(
    episodes: Sequence[object],
    fetch_observations: Callable[[tuple[str, ...]], Iterable[object]],
    fetch_lineage: Callable[[tuple[str, ...]], Iterable[object]],
    *,
    require_chronology: bool = False,
) -> dict[str, IndependenceAudit]:
    """Batch at most eight attacks and preserve each episode's own proof.

    The caller must not interpret missing results as successful verification.
    A bad shared fetch invalidates the whole batch, never just the bad rows.
    Database adapters require complete chronology for each observation.
    """
    items = tuple(episodes)
    if not items:
        return {}
    if len(items) > _MAX_EPISODES:
        return _blocked(items, "batch_episode_limit")
    keys = [str(getattr(ep, "episode_id", "") or "").strip() for ep in items]
    if any(not key for key in keys) or len(set(keys)) != len(keys):
        return _blocked(items, "invalid_or_duplicate_episode_id")

    results: dict[str, IndependenceAudit] = {}
    selected: list[object] = []
    seed_ids: set[str] = set()
    for key, episode in zip(keys, items):
        if str(getattr(episode, "episode_family", "") or "") not in _ATTACK_FAMILIES:
            results[key] = IndependenceAudit(False, reason="not_attack_episode")
            continue
        # Match the single-episode preflight before touching PostgreSQL.
        # A candidate or duplicate canonical label cannot be corroborated,
        # so it must not trigger expensive observation/lineage traversal.
        if (str(getattr(episode, "verification_status", "") or "") != "multi_source_corroborated"
                or not has_distinct_independence_groups(
                    getattr(episode, "independence_groups", None))):
            results[key] = IndependenceAudit(False, reason="canonical_verification_incomplete")
            continue
        raw = getattr(episode, "observation_ids", None)
        if (not isinstance(raw, (tuple, list))
                or not 2 <= len(raw) <= _MAX_OBSERVATIONS_PER_EPISODE
                or any(not isinstance(x, str) or not x.strip() for x in raw)
                or len({x.strip() for x in raw}) != len(raw)):
            results[key] = IndependenceAudit(False, reason="invalid_observation_ids")
            continue
        selected.append(episode)
        seed_ids.update(x.strip() for x in raw)
    if not selected:
        return results
    if len(seed_ids) > _MAX_TOTAL_NODES:
        results.update(_blocked(selected, "batch_node_limit"))
        return results

    rows = list(fetch_observations(tuple(sorted(seed_ids))))
    if len(rows) > len(seed_ids):
        results.update(_blocked(selected, "batch_observation_overflow"))
        return results
    observations: dict[str, list[object]] = {}
    for row in rows:
        identifier = str(getattr(row, "observation_id", "") or "").strip()
        if identifier not in seed_ids:
            results.update(_blocked(selected, "batch_unexpected_observation"))
            return results
        observations.setdefault(identifier, []).append(row)

    visited = set(seed_ids)
    frontier = set(seed_ids)
    edges: dict[str, list[object]] = {}
    count = 0
    for _ in range(_MAX_LINEAGE_DEPTH):
        if not frontier:
            break
        batch = list(fetch_lineage(tuple(sorted(frontier))))
        count += len(batch)
        if count > _MAX_TOTAL_EDGES:
            results.update(_blocked(selected, "batch_edge_limit"))
            return results
        new_nodes: set[str] = set()
        for row in batch:
            derived = str(getattr(row, "from_observation_id", "") or "").strip()
            original = str(getattr(row, "to_observation_id", "") or "").strip()
            if not derived or derived not in frontier or not original:
                results.update(_blocked(selected, "batch_invalid_lineage_row"))
                return results
            edges.setdefault(derived, []).append(row)
            if original not in visited:
                new_nodes.add(original)
        if len(visited | new_nodes) > _MAX_TOTAL_NODES:
            results.update(_blocked(selected, "batch_node_limit"))
            return results
        visited.update(new_nodes)
        frontier = new_nodes

    def cached_observations(ids: tuple[str, ...]) -> Iterable[object]:
        return [row for identifier in ids for row in observations.get(identifier, ())]

    def cached_lineage(ids: tuple[str, ...]) -> Iterable[object]:
        return [row for identifier in ids for row in edges.get(identifier, ())]

    for episode in selected:
        key = str(getattr(episode, "episode_id"))
        results[key] = audit_attack_episode_independence(
            episode, cached_observations, cached_lineage,
            require_chronology=require_chronology,
        )
    return results


def audit_attack_episodes_independence_db(
    episodes: Sequence[object], db: object,
) -> dict[str, IndependenceAudit]:
    """SELECT-only SQLAlchemy adapter, using a caller-owned session.

    The caller is responsible for enforcing a read-only transaction and
    handling DB failures by withholding the corroborated label.
    """
    from core.db.models import LineageEdgeDB, SourceObservationDB

    items = tuple(episodes)
    results: dict[str, IndependenceAudit] = {}
    for start in range(0, len(items), _MAX_EPISODES):
        chunk = items[start:start + _MAX_EPISODES]

        def observations(ids: tuple[str, ...]) -> Iterable[object]:
            return (db.query(SourceObservationDB)
                    .filter(SourceObservationDB.observation_id.in_(ids))
                    .order_by(SourceObservationDB.observation_id)
                    .limit(len(ids) + 1).all())

        def lineage(ids: tuple[str, ...]) -> Iterable[object]:
            return (db.query(LineageEdgeDB)
                    .filter(LineageEdgeDB.from_observation_id.in_(ids))
                    .order_by(LineageEdgeDB.from_observation_id,
                              LineageEdgeDB.to_observation_id)
                    .limit(_MAX_TOTAL_EDGES + 1).all())

        results.update(audit_attack_episodes_independence(
            chunk, observations, lineage, require_chronology=True,
        ))
    return results
