# Vessel Integration Plan

## Goal

Integrate PELAGO with existing shipboard equipment without taking control of critical systems.

The first production posture should be **read-only**:

- ingest NMEA 0183 from serial/TCP/UDP
- ingest AIS NMEA sentences from onboard receivers/transponders
- normalize all inputs to one internal event schema
- keep advisory and SAR decision-support separate from certified navigation equipment

## Product Split

### Edge Node

Runs on Raspberry Pi or other low-power onboard computer:

- local API
- local COP UI
- local event store
- sensor and vessel integrations
- optional cloud sync

### Cloud Dashboard

Runs online:

- multi-node overview
- fleet telemetry
- mission replay
- audit trail
- remote configuration and update workflows

## Integration Layers

1. Transport
- serial USB
- RS-422/RS-232 converters
- TCP listeners
- UDP listeners
- CAN/NMEA 2000 via gateway

2. Protocol adapters
- NMEA 0183
- AIS over NMEA
- NMEA 2000 gateway output
- vendor adapters where necessary

3. Normalization

Convert raw frames into shared events such as:

- `position_fix`
- `vessel_track`
- `distress_signal`
- `sensor_observation`
- `target_contact`

4. Core SAR services

- alerting
- drift computation
- forensic logging
- sync and replay

## Initial Scope

Start with these integrations first:

1. GPS / GNSS via NMEA 0183
2. AIS sentence ingest
3. manual operator event entry
4. optional NMEA 2000 through a gateway that exposes TCP/UDP/serial

Do not begin with direct write-back to bridge systems, autopilot, or vendor-locked radar controls.

## Current Scaffold In Repo

- `backend/domain/events.py`
- `backend/integrations/base.py`
- `backend/integrations/router.py`
- `backend/integrations/nmea0183/parser.py`
- `backend/integrations/ais/adapter.py`
- `backend/api/routes/integrations.py`

These files provide:

- a normalized onboard event model
- a basic routing layer for integration payloads
- minimal NMEA 0183 parsing for `RMC` and `GGA`
- minimal AIS sentence intake for raw AIVDM/AIVDO frames
- append-only local persistence in JSONL
- TCP/UDP listeners for shipboard integration feeds

## Suggested Next Steps

1. add serial/TCP/UDP listeners as daemon services
2. persist normalized events locally
3. expose a live vessel-state endpoint
4. decode AIS payloads into MMSI, course, speed, position
5. add NMEA 2000 gateway support
6. define cloud sync for append-only signed events

## Current Local Run Commands

Start a UDP listener:

```bash
python -m backend.cli integrations listen --transport udp --host 0.0.0.0 --port 10110
```

Start a TCP listener:

```bash
python -m backend.cli integrations listen --transport tcp --host 0.0.0.0 --port 10110
```

Start a serial listener:

```bash
python -m backend.cli integrations listen --transport serial --device /dev/ttyUSB0 --baudrate 38400
```

On Windows:

```bash
python -m backend.cli integrations listen --transport serial --device COM3 --baudrate 38400
```

Inspect recent stored integration events:

```bash
curl http://localhost:8000/api/v1/integrations/events
```

Inspect aggregated vessel state:

```bash
curl http://localhost:8000/api/v1/integrations/vessels
```

Get vessel positions as GeoJSON:

```bash
curl http://localhost:8000/api/v1/integrations/vessels/geojson
```
