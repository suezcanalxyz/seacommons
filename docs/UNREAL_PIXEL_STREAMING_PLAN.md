# SeaCommons immersive lab

## Decision

The public `play.seacommons.org` experience uses CesiumJS in the browser. It is
available without a GPU server and consumes the same scenario data as the 2D
operational map.

Unreal Engine is an optional high-fidelity renderer for a later `Immersive`
view. It does not calculate drift and it is not an independent source of
environmental truth.

```
environmental feeds ─┐
                     ├─ OpenDrift/API ─ scene contract v1 ─┬─ CesiumJS
case parameters ─────┘                                     └─ Unreal Engine
                                                                  │
                                                        Pixel Streaming/WebRTC
                                                                  │
                                                               browser
```

OpenDrift remains authoritative for horizontal translation and uncertainty.
Wave height, period and direction come from the environmental product declared
in the scenario. Visual heave, roll, pitch, foam and interpolation are renderer
effects and must be labelled as such.

## Verified local baseline

- Unreal Engine 5.2 editor: installed.
- Cesium for Unreal for UE 5.2: installed.
- Pixel Streaming for UE 5.2: installed.
- NVIDIA GTX 1650 4 GB and 16 GB RAM: suitable for one development stream at
  conservative quality, not a multi-user public service.

Use UE 5.2 for the first prototype to avoid mixing plugin versions. Upgrade the
engine and Cesium plugin together only after the scene is reproducible.

## Scene

The initial level opens over the scenario origin and contains:

1. a Cesium georeference and sea-level surface;
2. one anonymous low-poly vessel, with no identifying marks;
3. person units represented as cubes, capped at 24 rendered cubes, with a
   declared `people_per_cube` value when aggregation is required;
4. a trajectory spline generated from `trajectory.positions`;
5. an uncertainty footprint or ensemble cloud when present;
6. environmental vectors for wind, surface current and wave direction;
7. a camera with `overview`, `sea` and `vessel` modes.

The vessel position is interpolated along the returned timestamps. Renderer
interpolation must never write back to the evidence record.

## Runtime contract

Both renderers consume `docs/contracts/drift-scene-v1.schema.json`.

- `simulation.engine` declares whether the result is OpenDrift or a degraded
  estimate.
- `environment.waves.direction_source` prevents a wind proxy being presented as
  measured wave direction.
- `rendering.vertical_motion_physical` is false until a validated six-degree
  vessel model is supplied.
- coordinates use WGS84 longitude, latitude, altitude.

The browser can pass the contract to Unreal through the Pixel Streaming data
channel. Do not expose Unreal Remote Control to the public internet.

## Prototype phases

### Phase A — local single session

1. Create a Blueprint-only UE 5.2 project outside the web build.
2. Enable `CesiumForUnreal`, `PixelStreaming`, `Water` and JSON support.
3. Build the scene above and load a static contract fixture.
4. Package for Windows at 1280×720, 30 fps.
5. Run the local signalling stack and open the stream on the local network.

Target GPU settings: DX11 or DX12 after measurement, medium shadows, no Lumen,
no hardware ray tracing, temporal upscaling at balanced quality.

### Phase B — controlled remote preview

- Oracle hosts the API, authenticated session broker, signaling and CoTURN.
- The local workstation runs the packaged Unreal application and initiates the
  stream. It must remain powered on and connected.
- Access is limited to one short-lived authenticated session.
- TURN credentials are ephemeral; the API and TURN ports are rate-limited.

Oracle Always Free does not include a GPU. It must not be represented as the
Unreal render host.

### Phase C — public capacity

Move rendering to a paid GPU instance only after measuring:

- encoder utilization and end-to-end latency;
- bandwidth per 720p/30 stream;
- session concurrency and queue time;
- cost per completed research session;
- failure and privacy behaviour.

The public CesiumJS renderer remains the fallback when the GPU pool is
unavailable or full.

## Security boundary

- Vercel serves only the web client and same-origin proxy.
- API-issued session tokens are short-lived and scoped to a scenario.
- Unreal receives no primary account credentials.
- Scenario payloads are pseudonymous and omit vessel identity unless explicitly
  authorized.
- Pixel Streaming input is allow-listed; arbitrary console commands and file
  access are disabled.
- Live distress data is never used in the public demo.

## Acceptance test

- The same scenario ID produces the same horizontal path in 2D, CesiumJS and
  Unreal within the declared interpolation tolerance.
- The UI always displays engine, data timestamp and degradation state.
- Changing wave height changes visual heave but not the OpenDrift path.
- Changing current or wind and rerunning the model changes the returned path.
- A stream failure returns the user to CesiumJS without losing the scenario.
- No public endpoint exposes Unreal Remote Control.
