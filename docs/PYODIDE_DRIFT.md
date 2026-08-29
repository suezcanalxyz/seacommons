# Client-side drift with Pyodide

SeaCommons now includes a standalone horizontal drift kernel at
`apps/web/public/pyodide/seacommons_drift.py`. Vite copies it to
`/pyodide/seacommons_drift.py`, so a browser worker can load it without calling
the SeaCommons API.

The kernel has no HTTP client, SQL/database integration, credential handling or
provider-specific code. Its numerical core uses the Python standard library.
Only the CF-NetCDF adapter imports `numpy` and `netcdf4`, both distributed as
pre-built Pyodide packages.

## Model boundary

The implementation extracts the minimal OpenDrift update loop:

1. sample current, wind and optional Stokes vectors at particle time/position;
2. compute OceanDrift windage or deterministic mean Leeway velocity;
3. add the velocity components;
4. advance the WGS84 position with a midpoint (RK2) step;
5. emit one sampled trajectory.

The Leeway formula and the bundled mean object coefficients follow OpenDrift's
Leeway model. Random coefficient perturbations are deliberately absent because
the output is one representative line, not an uncertainty ensemble.

This kernel does not implement coastline interaction, beaching, vertical
mixing, capsizing/jibing, diffusion or probability cones. The output therefore
sets `operational_use` to `false` and must not replace official SAR tooling.

## Input contract

The JavaScript caller passes one JSON object:

```json
{
  "lkp": { "lat": 35.5, "lon": 14.0 },
  "timestamp": "2026-08-20T12:00:00Z",
  "vessel_type": "rubber_boat",
  "model": "leeway",
  "duration_seconds": 86400,
  "time_step_seconds": 900,
  "output_interval_seconds": 3600,
  "leeway_side": "mean",
  "include_stokes": true,
  "netcdf": {
    "format": "netcdf-cf",
    "path": "/data/med-subset.nc",
    "variables": {
      "time": "time",
      "latitude": "latitude",
      "longitude": "longitude",
      "current_u": "uo",
      "current_v": "vo",
      "wind_u": "u10",
      "wind_v": "v10"
    },
    "dimension_indices": { "depth": 0 }
  }
}
```

Supported vessel names are `person_in_water`, `life_raft`, `rubber_boat`,
`motorboat`, `wooden_boat`, `fishing_vessel`, `sailboat` and `unknown`.

`oceandrift` ignores the Leeway profile and accepts a `wind_drift_factor`
between 0 and 0.2. Both modes always advect with `current_u/current_v` and add
`stokes_u/stokes_v` when present and enabled.

The subset must use one-dimensional, monotonic time/latitude/longitude axes.
Forcing variables may be `[time, lat, lon]` or contain extra dimensions such as
depth; extra dimensions default to index zero and can be selected explicitly
with `dimension_indices`. Velocity units may be `m/s`, `cm/s`, `km/h` or knots.

For tests or already-decoded browser data, replace the NetCDF descriptor with:

```json
{
  "format": "decoded-grid/v1",
  "source": "local-test-subset",
  "coordinates": {
    "time": ["2026-08-20T12:00:00Z", "2026-08-21T12:00:00Z"],
    "latitude": [34.0, 37.0],
    "longitude": [12.0, 17.0]
  },
  "variables": {
    "current_u": [[[0.2, 0.2], [0.2, 0.2]], [[0.2, 0.2], [0.2, 0.2]]],
    "current_v": [[[0.0, 0.0], [0.0, 0.0]], [[0.0, 0.0], [0.0, 0.0]]],
    "wind_u": [[[4.0, 4.0], [4.0, 4.0]], [[4.0, 4.0], [4.0, 4.0]]],
    "wind_v": [[[1.0, 1.0], [1.0, 1.0]], [[1.0, 1.0], [1.0, 1.0]]]
  }
}
```

## Pyodide worker integration

The browser owns all I/O. It fetches a deliberately small NetCDF subset,
mounts the bytes in Pyodide's filesystem, and calls the JSON bridge:

```js
const pyodide = await loadPyodide();
await pyodide.loadPackage(['numpy', 'netcdf4']);

const [kernelSource, netcdfBytes] = await Promise.all([
  fetch('/pyodide/seacommons_drift.py').then((response) => response.text()),
  fetch('/forcing/med-subset.nc').then((response) => response.arrayBuffer()),
]);

pyodide.FS.writeFile('/seacommons_drift.py', kernelSource);
pyodide.FS.mkdirTree('/data');
pyodide.FS.writeFile('/data/med-subset.nc', new Uint8Array(netcdfBytes));
pyodide.runPython("import sys; sys.path.insert(0, '/')");
pyodide.runPython('import seacommons_drift');

pyodide.globals.set('request_json', JSON.stringify(request));
const resultJson = pyodide.runPython('seacommons_drift.simulate_json(request_json)');
pyodide.globals.delete('request_json');
const trajectory = JSON.parse(resultJson);
```

Run this inside a dedicated Web Worker so NetCDF decoding and integration never
block the UI thread.

## NetCDF and HTTP Range

The Python kernel never makes a network request. A generic NetCDF4/HDF5 file is
not automatically random-access over browser HTTP Range: its internal chunks
and metadata must still be resolved. The safe serverless pattern is to publish
small, pre-cropped CF-NetCDF assets with temporal and spatial margin, then
materialise the selected asset locally before simulation. Range requests can be
used by the browser/hosting layer where the asset layout is known, but the
kernel must receive a complete readable local subset.

For truly chunk-addressable large public forcing archives, add a separate Zarr
adapter later; do not hide remote reads inside the numerical model.

## Output

The only result is a GeoJSON `Feature` with a WGS84 `LineString`, aligned UTC
timestamps and speeds. It validates against
`docs/contracts/drift-trajectory-v1.schema.json`.

The module can also run offline:

```bash
python apps/web/public/pyodide/seacommons_drift.py input.json trajectory.json
```
