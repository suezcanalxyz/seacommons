// Bundle MapLibre's module worker with Vite so its shared dependency is emitted
// and the worker URL is fingerprinted under the configured public base path.
// The upstream runtime guesses ./maplibre-gl-worker.mjs beside its own chunk;
// that file is not present in Vite production output without explicit bundling.
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';

export function configureMaplibreWorker(maplibregl) {
  maplibregl.setWorkerUrl(workerUrl);
}
