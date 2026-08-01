import { computeDrift } from './driftEngine.js';

export function computeDriftInWorker(payload, onProgress = () => {}) {
  if (typeof Worker === 'undefined') {
    return Promise.resolve(computeDrift(payload, onProgress));
  }
  const requestId = globalThis.crypto?.randomUUID?.() || `sim-${Date.now()}`;
  const worker = new Worker(new URL('./drift.worker.js', import.meta.url), { type: 'module' });
  return new Promise((resolve, reject) => {
    worker.onmessage = (event) => {
      if (event.data?.requestId !== requestId) return;
      if (event.data.type === 'progress') {
        onProgress(Number(event.data.progress) || 0);
      } else if (event.data.type === 'complete') {
        worker.terminate();
        resolve(event.data.result);
      } else if (event.data.type === 'error') {
        worker.terminate();
        reject(new Error(event.data.error || 'Simulation worker failed'));
      }
    };
    worker.onerror = (event) => {
      worker.terminate();
      reject(new Error(event.message || 'Simulation worker crashed'));
    };
    worker.postMessage({ requestId, payload });
  });
}
