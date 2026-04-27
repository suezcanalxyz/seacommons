# Simulation Scenarios — SuezCanal Watch

Scenario files are JSON replays used in **demo** and **sim** mode.
Each scenario walks through a historical or plausible event step-by-step,
injecting sensor events into the AnomalyEngine as if they were live.

---

## Nord Stream (2022)

**File:** `watch/frontend/src/simulation/scenarios/nordstream.json`

Reconstructed timeline of the 2022 Nord Stream sabotage event based on open-source data:
- EMSC seismic events (ML 2.1 + ML 2.3 in Baltic Sea)
- AIS track anomalies (vessels near Bornholm with transponder gaps)
- Infrasound detections reported by Nordic monitoring stations
- Hydrophone detections via CTBTO auxiliary network

Key classification sequence:
1. `seismic` event detected → weight 0.22
2. `infrasound` event detected → cumulative 0.50
3. `ais_anomaly` (dark period) → pushes to 0.60
4. Classification: `physical_threat_candidate` → upgrades to `ballistic_confirmed` with ionospheric TEC spike

Use this scenario to test:
- Multi-sensor correlation convergence
- Forensic packet chain generation
- Alert banner escalation (urgent=true)

---

## Freedom Flotilla (2025)

**File:** `watch/frontend/src/simulation/scenarios/flotilla.json`

Simulated SAR scenario based on the May 2024 Gaza Freedom Flotilla events:
- Multiple vessel tracks approaching exclusion zone
- GNSS jamming / spoofing detected across fleet
- AIS discrepancies between declared and actual position
- SAR weather deterioration (Beaufort 6+)
- Drift simulation for assumed MOB (Man Overboard) event

Key classification sequence:
1. `gnss_spoof` detected → weight 0.07
2. `ais_anomaly` detected → cumulative 0.15
3. Weather SAR condition triggered
4. Classification: `vessel_spoofing_confirmed`
5. Drift cone generated from estimated last known position

Use this scenario to test:
- Lagrangian drift simulation activation
- Search area calculation (IAMSAR method)
- Multi-vessel coordination display

---

## Custom Scenarios

Create a JSON file with the following structure:

```json
{
  "id": "my-scenario",
  "title": "My Custom Scenario",
  "description": "Description shown in UI",
  "steps": [
    {
      "t_offset_s": 0,
      "event": {
        "sensor_source": "seismic",
        "anomaly_type": "explosion",
        "timestamp_utc": "2025-01-01T00:00:00Z",
        "location_lat": 35.0,
        "location_lon": 14.0,
        "raw_value": 3.2,
        "unit": "ml",
        "confidence": 0.85,
        "platform_id": "sim"
      }
    }
  ]
}
```

Import and add to `App.tsx`:
```tsx
import myScenario from './simulation/scenarios/my-scenario.json';
// Then wire it to a button in Sidebar
```

---

## Running Scenarios

1. Switch to **SIM** or **DEMO** mode in the sidebar
2. Click the scenario button
3. `ScenarioPlayer` replays events at accelerated time (10× real-time)
4. Watch the AnomalyEngine accumulate sensor detections
5. Observe the AlertBanner escalate when threshold crossed
6. Drift cone appears if a MOB/distress event is included

Press **Stop** or switch to **LIVE** mode to abort playback.
