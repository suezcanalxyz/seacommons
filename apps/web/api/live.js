import http from 'node:http';

const UPSTREAM_HOST = '204.216.210.155';
const UPSTREAM_VIRTUAL_HOST = 'api.seacommons.org';

function requestJson(path) {
  return new Promise((resolve, reject) => {
    const request = http.get(
      {
        hostname: UPSTREAM_HOST,
        port: 80,
        path,
        headers: {
          host: UPSTREAM_VIRTUAL_HOST,
          accept: 'application/json',
          'user-agent': 'SeaCommons-Vercel-Live/1.0',
        },
      },
      (response) => {
        const chunks = [];
        response.on('data', (chunk) => chunks.push(chunk));
        response.on('end', () => {
          const body = Buffer.concat(chunks).toString('utf8');
          let data = null;
          try { data = body ? JSON.parse(body) : null; } catch { /* handled below */ }
          resolve({ status: response.statusCode || 502, data });
        });
      },
    );
    request.setTimeout(24_000, () => request.destroy(new Error('SeaCommons API timed out')));
    request.on('error', reject);
  });
}

function alertFallback(payload) {
  const seen = new Set();
  const features = [];
  for (const feature of payload?.features || []) {
    const geometry = feature?.geometry;
    if (geometry?.type !== 'LineString' || !Array.isArray(geometry.coordinates?.[0])) continue;
    const [lon, lat] = geometry.coordinates[0];
    const key = `${Number(lon).toFixed(4)}:${Number(lat).toFixed(4)}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const id = `sar:${key}`;
    features.push({
      type: 'Feature',
      id,
      geometry: { type: 'Point', coordinates: [Number(lon), Number(lat)] },
      properties: {
        schema: 'org.seacommons.live-signal/v1',
        id,
        type: 'sar_model',
        kind: 'context',
        severity: 'medium',
        tier: 'signal',
        priority: 22,
        verification_status: 'derived',
        publication_status: 'published',
        drift_ready: false,
        title: 'Computed SAR drift product',
        text: '',
        source: 'SeaCommons engine',
        url: '',
        timestamp_utc: feature.properties?.timestamp_utc || new Date().toISOString(),
      },
    });
  }
  return {
    type: 'FeatureCollection',
    features,
    meta: {
      schema: 'org.seacommons.live-feed/v1',
      total: features.length,
      with_coords: features.length,
      generated_at: new Date().toISOString(),
      compatibility_mode: true,
      privacy: 'published signals only; private identifiers and raw messages excluded',
    },
  };
}

function sourceFallback(summary) {
  const aisActive = Boolean(summary?.backend?.aisstream_connected);
  const cmemsReady = Boolean(summary?.backend?.cmems_configured);
  const vessels = summary?.traffic?.registry || {};
  return {
    sources: [
      {
        name: 'AIS',
        type: 'ais',
        status: aisActive ? 'active' : 'offline',
        last_poll_at: summary?.generated_at || null,
        events_last_hour: 0,
        total_events: Number(summary?.backend?.aisstream_messages || 0),
        consecutive_errors: aisActive ? 0 : 1,
      },
      {
        name: 'CMEMS',
        type: 'environment',
        status: cmemsReady ? 'active' : 'offline',
        last_poll_at: summary?.generated_at || null,
        events_last_hour: 0,
        total_events: 0,
        consecutive_errors: cmemsReady ? 0 : 1,
      },
    ],
    summary: {
      total: 2,
      active: Number(aisActive) + Number(cmemsReady),
      degraded: 0,
      offline: Number(!aisActive) + Number(!cmemsReady),
      vessels,
    },
    channels: {
      whatsapp: Boolean(summary?.channels?.whatsapp?.configured),
      telegram: Boolean(summary?.channels?.telegram?.configured),
      partner_webhook: Boolean(summary?.channels?.partner_webhook?.configured),
    },
    generated_at: new Date().toISOString(),
    compatibility_mode: true,
  };
}

export default async function handler(req, res) {
  res.setHeader('cache-control', 'no-store');
  res.setHeader('content-type', 'application/json; charset=utf-8');
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    res.setHeader('allow', 'GET, HEAD');
    return res.status(405).json({ detail: 'Method not allowed' });
  }

  const resource = Array.isArray(req.query.resource) ? req.query.resource[0] : req.query.resource;
  const upstreamPath = resource === 'sources'
    ? '/api/v1/live/sources'
    : '/api/v1/live/signals?limit=300&days=30';
  try {
    const upstream = await requestJson(upstreamPath);
    if (upstream.status === 200 && upstream.data) {
      res.setHeader('x-seacommons-live-source', 'engine');
      return res.status(200).json(upstream.data);
    }

    const fallback = resource === 'sources'
      ? sourceFallback((await requestJson('/api/v1/ops/summary')).data)
      : alertFallback((await requestJson('/api/v1/alerts/geojson')).data);
    res.setHeader('x-seacommons-live-source', 'compatibility');
    return res.status(200).json(fallback);
  } catch {
    return res.status(502).json({ detail: 'SeaCommons live feed unavailable' });
  }
}

export const config = {
  maxDuration: 30,
};
