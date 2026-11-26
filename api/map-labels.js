const { Buffer } = require('node:buffer');

const STYLES = new Set(['light_only_labels', 'dark_only_labels']);

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
  if (!key) {
    console.warn('map-labels: missing provider configuration');
    res.setHeader('Cache-Control', 'no-store');
    return send(res, 503);
  }
  const url = new URL(`https://basemaps.cartocdn.com/rastertiles/${style}/${z}/${x}/${y}.png`);
  url.searchParams.set('key', key);
  try {
    const tile = await fetch(url, { redirect: 'error', signal: AbortSignal.timeout(8000) });
    if (!tile.ok || !tile.headers.get('content-type')?.startsWith('image/png')) {
      console.warn('map-labels: upstream rejected tile', { status: tile.status, png: Boolean(tile.headers.get('content-type')?.startsWith('image/png')) });
      res.setHeader('Cache-Control', 'no-store');
      return send(res, 502);
    }
    const image = Buffer.from(await tile.arrayBuffer());
    res.setHeader('Content-Type', 'image/png');
    res.setHeader('Cache-Control', 'public, max-age=86400');
    res.setHeader('Vercel-CDN-Cache-Control', 'public, s-maxage=604800, stale-while-revalidate=86400');
    return send(res, 200, image);
  } catch (error) {
    console.warn('map-labels: upstream request failed', { timeout: error?.name === 'TimeoutError' });
    res.setHeader('Cache-Control', 'no-store');
    return send(res, 502);
  }
}

module.exports = handler;
