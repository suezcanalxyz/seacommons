# ADR 0003: At-least-once Public Live edge delivery

- Status: Accepted
- Date: 2026-08-26

## Context

Public Live must remain available when the primary API restarts or the network
between the collector and edge is temporarily unavailable. Exact-once delivery
would add coordination cost without improving visible map semantics.

## Decision

Use a local SQLite outbox for at-least-once publisher delivery and one named
Cloudflare Durable Object as the single-writer Public Live room. Event versions
have deterministic IDs; the Edge deduplicates IDs, retains one latest visible
version per incident, records hash continuity and sends a snapshot before
WebSocket deltas.

## Consequences

- Publisher restart and temporary edge outage do not lose pending versions.
- Duplicate HTTP delivery is normal and must remain idempotent.
- Removal/resolution and out-of-order delivery require explicit invariant tests.
- Durable Object state is an ephemeral public read model, not the operational
  database or a permanent evidence ledger.
