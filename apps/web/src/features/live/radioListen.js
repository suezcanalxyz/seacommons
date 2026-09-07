export function liveListenHttpUrl(apiBase, receiverId, locationLike = window.location) {
  const origin = locationLike?.origin || window.location.origin;
  const url = new URL(apiBase || origin, origin);
  url.pathname = `/api/v1/live/radio/listen/${encodeURIComponent(String(receiverId || ''))}`;
  url.search = '';
  url.hash = '';
  return url.toString();
}

export function liveListenWebSocketUrl(apiBase, receiverId, locationLike = window.location, routeBase = '/api/v1/live/radio/listen') {
  const origin = locationLike?.origin || window.location.origin;
  const url = new URL(apiBase || origin, origin);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  url.pathname = `${String(routeBase || '/api/v1/live/radio/listen').replace(/\/$/, '')}/${encodeURIComponent(String(receiverId || ''))}`;
  url.search = '';
  url.hash = '';
  return url.toString();
}

export function pcm16leToFloat32(payload) {
  const bytes = payload instanceof ArrayBuffer
    ? new Uint8Array(payload)
    : new Uint8Array(payload.buffer, payload.byteOffset, payload.byteLength);
  if (!bytes.byteLength || bytes.byteLength % 2) throw new Error('invalid PCM16 packet');
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const samples = new Float32Array(bytes.byteLength / 2);
  for (let index = 0; index < samples.length; index += 1) {
    samples[index] = view.getInt16(index * 2, true) / 32768;
  }
  return samples;
}
