import { computeDrift } from './driftEngine.js';

self.onmessage = (event) => {
  const { requestId, payload } = event.data || {};
  try {
    const result = computeDrift(payload, (progress) => {
      self.postMessage({ requestId, type: 'progress', progress });
    });
    self.postMessage({ requestId, type: 'complete', result });
  } catch (error) {
    self.postMessage({
      requestId,
      type: 'error',
      error: error instanceof Error ? error.message : String(error),
    });
  }
};
