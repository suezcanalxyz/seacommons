# Architecture decision records

ADRs capture durable technical decisions and their trade-offs. They complement
the canonical architecture documents; they do not replace runbooks or executable
contracts.

## Status values

- Proposed — under review, not yet authoritative.
- Accepted — current decision.
- Superseded — replaced by a later ADR, which must be linked.
- Deprecated — retained temporarily while migration completes.

## Index

| ADR | Status | Decision |
|---|---|---|
| [0001](0001-modular-monorepo-and-process-boundaries.md) | Accepted | Modular monorepo with separable worker processes |
| [0002](0002-canonical-fail-closed-public-projection.md) | Accepted | One canonical fail-closed public projection |
| [0003](0003-at-least-once-public-live-edge.md) | Accepted | At-least-once publisher and idempotent Durable Object edge |

Create new ADRs with the next four-digit number. Include context, decision,
consequences and links to superseded records. Never rewrite an accepted decision
to hide history; supersede it with a new ADR.
