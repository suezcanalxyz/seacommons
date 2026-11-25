const { Buffer } = require('node:buffer');

const STYLES = new Set(['light_only_labels', 'dark_only_labels']);
const DIAGNOSTIC_INTERVAL_MS = 60_000;
const lastDiagnostic = new Map();

// Fixed categories only: never log the upstream URL, key, response body or exception message.
function upstreamFailure(res, category, upstreamStatus = null) {
  const code = `${category}:${upstreamStatus ?? 'none'}`;
  const now = Date.now();
  if (!lastDiagnostic.has(code) || now - lastDiagnostic.get(code) >= DIAGNOSTIC_INTERVAL_MS) {
    lastDiagnostic.set(code, now);
    console.warn('map-labels upstream failure', { category, upstreamStatus });
  }
  res.setHeader('Cache-Control', 'no-store');
  return send(res, category === 'missing_configuration' ? 503 : 502);
}

function send(res, status, body) {
  res.statusCode = status;
  res.end(body);
}

async function handler(req, res) {
  if (req.method !== 'GET') {
    res.setHeader('Allow', 'GET');
    return send(res, 405);
  }
  const { style, z, x, y } = req.query || Object.fromEntries(new URL(req.url, "http://localhost").searchParams);
  const coordinate = (value) => typeof value === 'string' && /^(0|[1-9]\d{0,5})$/.test(value);
  if (!STYLES.has(style) || ![z, x, y].every(coordinate)
    || Number(z) > 19 || Number(x) >= 2 ** Number(z) || Number(y) >= 2 ** Number(z)) {
    return send(res, 400);
  }
  const key = process.env.CARTO_BASEMAPS_API_KEY?.trim();
  if (!key) return upstreamFailure(res, 'missing_configuration');
  const url = new URL(`https://basemaps.cartocdn.com/rastertiles/${style}/${z}/${x}/${y}.png`);
  url.searchParams.set('key', key);
  try {
    const tile = await fetch(url, { redirect: 'error', signal: AbortSignal.timeout(8000) });
    if (!tile.ok) return upstreamFailure(res, 'upstream_http', tile.status);
    if (!tile.headers.get('content-type')?.startsWith('image/png')) {
      return upstreamFailure(res, 'unexpected_content_type', tile.status);
    }
    const image = Buffer.from(await tile.arrayBuffer());
    res.setHeader('Content-Type', 'image/png');
    res.setHeader('Cache-Control', 'public, max-age=86400');
    res.setHeader('Vercel-CDN-Cache-Control', 'public, s-maxage=604800, stale-while-revalidate=86400');
    return send(res, 200, image);
  } catch (error) {
    return upstreamFailure(res, error?.name === 'TimeoutError' || error?.name === 'AbortError'
      ? 'upstream_timeout' : 'upstream_transport');
  }
}

module.exports = handler;
