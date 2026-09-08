# Radio Coverage & Auto-Failover Design

**Date:** 2026-09-08
**Status:** approved for implementation

## Goal

Turn the Mediterranean radio mesh from a start-everything pool into a bounded, channel-aware receiver service with deterministic standby selection and automatic failover, while preserving multi-receiver RF correlation and all existing evidence/privacy boundaries.

## Context

Packet F closed Listen Live on the Oracle VM. The current `RemoteRadioRuntime` starts every runnable primary and public-pool receiver concurrently and reconnects each one independently. This provides redundancy but no explicit channel assignment, no bounded standby pool, and no failover state that operators can inspect.

The persistent receiver catalog already ranks candidates by reachability, target-frequency support, geographic distance, uptime/failure history, lineage independence and source terms. Packet G reuses that rank as the coverage prior; it does not invent a second receiver-scoring authority.

## Non-negotiable boundaries

- No continuous audio/IQ persistence.
- `AUDIO_EVIDENCE_ENABLED` remains false.
- No Humanitarian incident/lifecycle/publication mutation.
- Physical receiver lineage remains the independence boundary.
- Multiple provider frontends for one physical receiver never occupy multiple active slots.
- DSC/NAVTEX decoding, AIS association and RF-burst correlation keep their existing semantics.
- No DB migration is required.

## Channel model

A channel target is identified by `(channel_kind, frequency_hz, mode)`. Packet G initially supports the same bounded kinds already accepted by receiver descriptors: `dsc`, `navtex`, and `monitor`.

Configured descriptors with an explicit frequency/mode define authoritative targets. If no explicit target exists, the existing public DSC monitor target `monitor / 2187500 Hz / usb` remains the bootstrap fallback.

Each target has `desired_replicas`, defaulting to 3 when managed failover is enabled. Three active independent lineages preserve the existing multi-receiver RF correlation capability while bounding connections and leaving ranked candidates in standby.

Candidate order is deterministic:

1. explicitly configured target-compatible receivers, in configuration order;
2. terms-allowed persistent-catalog receivers, already sorted by catalog score;
3. duplicate physical lineages removed before assignment.

The runtime does not recompute geographic/uptime coverage scores. The persistent catalog remains authoritative for that ranking.

## Runtime state

For each candidate the runtime tracks only ephemeral process state: `active`, `standby`, or `cooldown`, activation time, last known health, and retry eligibility. This state is not evidence and is not persisted.

At startup, only the first `desired_replicas` candidates per target are started/tuned. Remaining candidates stay unconnected standby. Descriptors without an explicit managed target retain legacy behavior only when managed failover is disabled.

## Health and failover rules

An active receiver is unhealthy when its adapter reports `connected=false`, or when it has produced no message beyond the configured stale window after its activation grace. A hard disconnect first gets one immediate reconnect-and-retune attempt on the same receiver. Only a failed reconnect is eligible for failover on that supervisor pass; silence uses the stale window so a quiet network does not flap immediately.

When an active slot becomes unhealthy:

1. on a hard disconnect, attempt one immediate reconnect and retune of the same receiver; if it succeeds, keep the slot active and do not consume standby;
2. if reconnect fails, or the receiver is connected but stale, stop the unhealthy adapter;
3. move it to cooldown until `REMOTE_RADIO_FAILOVER_RETRY_S` elapses;
4. promote the highest-ranked compatible standby lineage;
5. start and tune the replacement;
6. increment bounded failover counters only when an active slot is actually demoted.

There is no eager failback. A recovered higher-ranked receiver remains standby until a currently active receiver becomes unhealthy. This is the anti-flapping rule.

If no standby can start, the channel remains degraded and the supervisor retries eligible cooldown candidates later. Failure of one target never stops another target.

## Configuration

New fail-closed settings:

- `REMOTE_RADIO_FAILOVER_ENABLED=false` by default;
- `REMOTE_RADIO_CHANNEL_REPLICAS=3`, bounded 1–8;
- `REMOTE_RADIO_FAILOVER_STALE_S=30`, minimum 5 seconds;
- `REMOTE_RADIO_FAILOVER_RETRY_S=120`, minimum 30 seconds.

Production activation is a separate runtime flag change after release gates. Disabling `REMOTE_RADIO_FAILOVER_ENABLED` restores the current start-all/reconnect behavior.

## Public-safe status and observability

`/api/v1/live/pipeline` keeps the existing public receiver rows and adds a bounded `channels` summary. Each row exposes only `channel_kind`, `frequency_hz`, `mode`, `desired`, `active`, `standby`, `cooldown`, and `failovers`.

It must never expose frontend URLs, source terms, session IDs, physical-lineage identifiers, provider errors, raw payloads, audio bodies, or decoder text.

The existing bounded remote-radio metric accepts explicit `failover`, `standby_promoted`, and `cooldown_retry` outcomes. Labels remain provider/state/outcome only; frequency and receiver IDs never become metric labels.

## Compatibility

Listen Live continues to attach only to receivers that are actually connected and eligible. An active replacement therefore becomes listenable through the existing mesh projection without a new public endpoint.

RF burst correlation still sees observations from multiple independent active receivers because the default managed target keeps three replicas. No derived evidence or publication rule changes.

## Verification

Required automated coverage:

- deterministic channel grouping and lineage deduplication;
- only desired replicas start in managed mode;
- hard disconnect promotes the best standby;
- stale active receiver promotes standby after the stale window;
- recovered higher-ranked receiver does not force eager failback;
- failed promoted candidate does not prevent trying the next standby;
- cooldown candidate becomes retry-eligible after the retry window;
- three active lineages remain available for RF correlation by default;
- public pipeline contains channel aggregates and no private receiver fields;
- disabled managed failover preserves legacy runtime behavior.

Release gate: focused Packet G tests, full backend suite, Ruff critical/canonical checks, web/edge regressions, production restart and a controlled failover smoke on the VM. Rollback is `REMOTE_RADIO_FAILOVER_ENABLED=false` plus service restart.
