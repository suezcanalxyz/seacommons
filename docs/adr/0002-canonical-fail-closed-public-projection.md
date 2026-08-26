# ADR 0002: Canonical fail-closed public projection

- Status: Accepted
- Date: 2026-08-26

## Context

SeaCommons handles private humanitarian reports and also publishes a reduced
Public Live feed. Publication policy had been represented by repeated string
checks across routes, publisher and Edge code, creating drift and disclosure
risk.

## Decision

Define publication status, source policy, verification status, lifecycle and
location precision in canonical domain contracts. Backend public feed and edge
publisher reuse one projection/policy implementation. Unknown policy values and
contract-invalid projected payloads are rejected. The Edge validates the public
contract again and rejects private visibility.

## Consequences

- User-originated input is private by default and typos fail closed.
- Provider additions must choose an explicit source policy and add contract
  tests.
- Backend and Edge retain defence-in-depth validation in two languages; enum and
  schema parity tests are required to prevent drift.
- Public payload evolution requires versioned schema changes and compatibility
  review.
