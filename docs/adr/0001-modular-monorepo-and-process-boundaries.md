# ADR 0001: Modular monorepo and process boundaries

- Status: Accepted
- Date: 2026-08-26

## Context

SeaCommons ships a web console, FastAPI backend, public edge worker and static
site. The backend also performs scientific jobs and polls external intelligence
sources. These responsibilities need independent resource/restart boundaries,
but they share domain models and are operated by a small team.

## Decision

Keep one monorepo and one backend package. Separate deployment processes at
existing responsibility boundaries: API, durable job worker, intel worker and
Live edge publisher. All backend processes share the durable database and reuse
the same domain/service modules. Do not introduce network microservices solely
to reorganize code.

## Consequences

- Domain changes can be tested atomically across runtimes.
- Workers can be scaled or restarted independently from the API.
- Shared-database and cache synchronization become explicit operational
  contracts and require metrics.
- Process entrypoints must stay thin; business policy belongs in shared domain
  services rather than being duplicated per process.
