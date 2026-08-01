# SeaCommons Immersive

Unreal Engine 5.2 renderer for `drift-scene/v1`. The scene may contain either
an OpenDrift validation product or the public deterministic browser result.
Unreal renders the ocean, weather, vessel response and camera experience; it
never changes the persisted horizontal path.

## Local baseline

- Unreal Engine 5.2
- Cesium for Unreal 2.11.1
- Water and Pixel Streaming engine plugins
- Windows development target: 1280x720 at 30 fps

The native `SeaCommonsImmersive Win64 Development` and
`SeaCommonsImmersiveEditor Win64 Development` targets compile and link
successfully with the installed UE 5.2 toolchain. Visual Studio Build Tools now
includes the .NET Framework 4.8 SDK and Targeting Pack required by the Editor
target. The cooked Windows build is written to `Packaged/Windows`; it has been
runtime-smoke-tested offscreen against the included demo scene.

## Ocean level

`/Game/Maps/SeaCommonsOcean` is generated and validated. It contains the
Cesium georeference, atmosphere, cloud, fog and lighting actors, an Unreal
Water ocean, an anonymous physics raft with four pontoons and a cine camera.
Regenerate and validate it with the editor scripts in `Scripts/` when the
level recipe changes.

The game mode automatically spawns `ASeaCommonsSceneController`. It loads
`Content/Scenarios/demo-scene.json`, or a file passed as:

```powershell
SeaCommonsImmersive.exe -SeaCommonsScene="D:\scene.json"
```

The controller turns the persisted significant wave height, period and
direction into a deterministic 32-wave Gerstner spectrum. It also accepts a
Pixel Streaming UI interaction:

```json
{
  "type": "seacommons.scene",
  "payload": {
    "schema_version": "drift-scene/v1"
  }
}
```

The full `payload` must validate against
`docs/contracts/drift-scene-v1.schema.json`.

When embedded by the public Play application, configure
`VITE_UNREAL_PIXEL_STREAM_URL` with the signalling frontend URL and install
`Web/SeaCommonsPixelStreamingBridge.js` in that frontend. The bridge must use
an explicit allow-list containing `https://play.seacommons.org`; it forwards
only `seacommons.scene` envelopes to Pixel Streaming's `emitUIInteraction`.

## Pixel Streaming prototype

The official Pixel Streaming Infrastructure `UE5.2` branch can be installed
locally with:

```powershell
cd .\Samples\PixelStreaming\WebServers
.\get_ps_servers.bat /v 5.2
cd .\SignallingWebServer\platform_scripts\cmd
.\setup.bat --build
```

The downloaded server, Node runtime and generated frontend are ignored by Git.
The signalling server has been smoke-tested locally with an HTTP 200 response.
The launch script provides conservative desktop and mobile WebRTC profiles:

```powershell
.\Scripts\launch_pixel_streaming.ps1 -Profile Desktop
.\Scripts\launch_pixel_streaming.ps1 -Profile Mobile
```

The mobile profile renders at 960x540 and 30 fps with a 5.5 Mbps ceiling,
maintaining frame rate when the connection degrades. The desktop profile uses
1280x720 at 30 fps with a 12 Mbps ceiling. Unreal still runs on the GPU host:
phones receive the stream and send touch/pointer input, so no UE mobile package
is required. Both profiles select D3D11: it completed a clean offscreen
signalling handshake on the current NVIDIA host, while UE 5.2's D3D12 viewport
raised a non-fatal swap-chain ensure in the same test.

Do not enable `-AllowPixelStreamingCommands`. Public inputs must be limited to
camera controls and `seacommons.scene` payloads issued by the session broker.
The legacy UE 5.2 infrastructure includes end-of-life Node 16 dependencies with
known audit findings. Do not expose the reference server directly to the
internet: put it behind TLS, authentication and network controls, or upgrade
Unreal and Pixel Streaming Infrastructure before production.

## Known compatibility note

Cesium for Unreal 2.11.1 loads an unused three-overlay water material that
exceeds the SM5 16-sampler limit. The ocean level contains no Cesium tileset
and renders the sea with Unreal Water, so the packaged runtime falls back for
that unused material without affecting the simulation. Resolve this before
adding terrain tiles by using shared texture samplers, fewer overlays or a
newer Unreal/Cesium baseline.

## Realism boundary

The Unreal Water plugin supplies the tiled ocean, physically based
SingleLayerWater material, Gerstner waves and buoyancy sampling. Niagara should
add bow spray, wake foam and rain only after the base sea state is calibrated.
`rendering.vertical_motion_physical` stays `false` until vessel mass, centre of
gravity, pontoon positions and damping have been validated.
