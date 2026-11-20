const STYLES = new Set(['light_only_labels', 'dark_only_labels']);

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    res.setHeader('Allow', 'GET');
    return res.status(405).end();
  }
  const { style, z, x, y } = req.query;
  const coordinate = (value) => typeof value === 'string' && /^(0|[1-9]\d{0,5})$/.test(value);
  if (!STYLES.has(style) || ![z, x, y].every(coordinate)
    || Number(z) > 19 || Number(x) >= 2 ** Number(z) || Number(y) >= 2 ** Number(z)) {
    return res.status(400).end();
  }
  const key = process.env.CARTO_BASEMAPS_API_KEY?.trim();
  if (!key) return res.status(503).end();
  const url = new URL(`https://basemaps.cartocdn.com/rastertiles/${style}/${z}/${x}/${y}.png`);
  url.searchParams.set('key', key);
  try {
    const tile = await fetch(url, { redirect: 'error', signal: AbortSignal.timeout(8000) });
    if (!tile.ok || !tile.headers.get('content-type')?.startsWith('image/png')) {
      return res.status(502).end();
    }
    const image = Buffer.from(await tile.arrayBuffer());
    res.setHeader('Content-Type', 'image/png');
    res.setHeader('Cache-Control', 'public, max-age=86400');
    res.setHeader('Vercel-CDN-Cache-Control', 'public, s-maxage=604800, stale-while-revalidate=86400');
    return res.status(200).end(image);
  } catch {
    return res.status(502).end();
  }
}
