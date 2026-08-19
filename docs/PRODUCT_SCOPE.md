# SeaCommons — Product Scope

Date: 19 August 2026
Status: active scope for repository refactor and funding preparation

## Product thesis

SeaCommons is an open-source maritime infrastructure cluster.

It originates from a Central Mediterranean case study, where rescue activity, vessel movements, fragmented public information, ocean conditions and operational coordination expose the need for interoperable maritime software. That context remains the first deployment and a demanding validation environment.

It is **not** the software boundary.

The reusable core must support other maritime contexts without changing its fundamental architecture.

## What SeaCommons should become

SeaCommons should provide a compact open maritime operating substrate that allows an organisation to:

1. create and manage one or more fleets;
2. register vessels using stable internal identities plus maritime identifiers such as MMSI/IMO where available;
3. attach real-time or periodic vessel observations from one or more providers;
4. see latest vessel position, track history, source and data freshness;
5. ingest maritime events and observations from replaceable adapters;
6. combine vessel state with weather, currents, waves and other ocean information;
7. run analytical modules such as drift modelling without coupling them to one UI or provider;
8. publish selected data through privacy-aware public views while retaining private organisational views;
9. deploy and operate the stack independently on infrastructure controlled by the user or organisation.

## First reference deployment

Central Mediterranean research / SAR / civil-society monitoring remains a reference implementation because it exercises several difficult requirements at once:

- heterogeneous source ingestion;
- vessel tracking;
- incident lifecycle;
- incomplete or uncertain coordinates;
- source provenance;
- environmental enrichment;
- privacy and publication boundaries;
- time-sensitive drift analysis.

Mediterranean-specific concepts must not leak into the generic domain model unless they are genuinely maritime concepts.

Examples:

GOOD generic concepts:

```text
Fleet
Vessel
VesselObservation
Track
MaritimeEvent
Incident
Source
EnvironmentSnapshot
DerivedProduct
PublicationPolicy
```

Deployment-specific concepts that should stay outside the core:

```text
Alarm Phone account rules
specific NGO account lists
Central Mediterranean bounding boxes
Malta/Italy SAR-specific UI presets
specific campaign or research taxonomies
```

These belong in adapters, configuration or reference deployments.

## Core architecture

```text
                    ORGANISATION / DEPLOYMENT
                              │
                       Fleet Registry
                              │
                  ┌───────────┴───────────┐
                  ▼                       ▼
               Vessel                  Vessel
                  │                       │
          observations/providers          │
                  └───────────┬───────────┘
                              │
                              ▼
                     canonical maritime state
                              │
                 ┌────────────┼────────────┐
                 ▼            ▼            ▼
              events      environment    analysis
                 │            │            │
                 └────────────┼────────────┘
                              ▼
                         SeaCommons API
                    ┌─────────┼─────────┐
                    ▼         ▼         ▼
                 private     public   external
                 console      live     clients
```

## Funding-scope discipline

For an open-source grant in the approximate **€40k range**, SeaCommons should not attempt to become a full commercial maritime ERP, VMS, navigation suite or global AIS provider.

The funded scope should produce a convincing reusable substrate with a reference implementation.

### In scope

- fleet model;
- vessel identity model;
- provider-independent vessel observations;
- one working real-time AIS connector;
- canonical maritime event schema;
- public-source adapter contract;
- environment/provider contract;
- source health and freshness;
- live state API;
- privacy/publication projection;
- provenance metadata;
- working web reference client;
- deployment documentation;
- tests and CI;
- one reproducible drift workflow if feasible within the work package.

### Explicitly not required for this funding phase

- worldwide proprietary AIS coverage purchased by the project;
- billing/CRM;
- crew payroll;
- maintenance ERP;
- voyage optimisation suite;
- electronic chart replacement;
- regulatory compliance suite;
- full port-management system;
- enterprise multi-region orchestration;
- dozens of data providers;
- mobile applications for every platform;
- rebuilding mature external tools that can instead be integrated.

The core should make those future integrations possible without attempting them now.

## Fleet as a first-class domain

Fleet management should be simple and useful.

Minimum model:

```text
Fleet
  id
  name
  description
  owner/organisation

Vessel
  id
  name
  mmsi optional
  imo optional
  callsign optional
  type optional
  metadata

FleetMembership
  fleet_id
  vessel_id
  active_from
  active_to optional

VesselObservation
  vessel_id
  observed_at
  received_at
  geometry
  speed optional
  course optional
  heading optional
  navigation_status optional
  source
  provenance
```

Do not bind `Vessel` to AISStream. AISStream is one observation provider.

This allows future adapters for:

```text
AIS provider
NMEA receiver
GPS tracker
satellite tracker
partner API
manual position
research sensor
```

without changing the vessel domain.

## Maritime events remain a second first-class domain

SeaCommons should not collapse every source into vessel state.

A maritime event can exist without a known vessel and a vessel can exist without an incident.

Examples:

```text
public report
navigation warning
distress report
weather alert
SAR area
sensor observation
port event
environmental observation
research annotation
```

The generic event contract should support these while deployment-specific parsers interpret particular sources such as Alarm Phone.

## Source strategy

Adapters are replaceable transports.

Examples:

```text
AISStream -> VesselObservation
Twikit/X -> RawPublicPost -> MaritimeEvent
official X API -> RawPublicPost -> MaritimeEvent
CMEMS -> EnvironmentSnapshot
NMEA -> VesselObservation
partner webhook -> MaritimeEvent or VesselObservation
```

A transport must never define the domain model.

For X specifically, free/session-based acquisition may remain useful for the reference deployment, but Alarm Phone parsing is a deployment adapter, not a foundational SeaCommons concept.

## Foundation / ecosystem role

A foundation or broader institutional layer can support SeaCommons as an open-source cluster by coordinating:

- stewardship;
- documentation;
- contributor onboarding;
- partnerships and deployments;
- research pilots;
- funding applications;
- interoperability work;
- governance;
- public-interest use cases.

This institutional role should remain separate from the software architecture. SeaCommons must remain deployable and forkable independently of any single foundation.

## Success criterion for the preparation phase

A technically competent external reviewer should be able to understand this proposition from the repository alone:

> SeaCommons is a reusable open maritime platform. I can create a fleet, register vessels, connect a live position source, consume canonical maritime events and environmental data, run the reference web client, and extend the system through documented adapters. The Central Mediterranean deployment demonstrates the architecture but does not constrain it.

If the repository communicates only SAR/Mediterranean monitoring, the refactor is not complete.
