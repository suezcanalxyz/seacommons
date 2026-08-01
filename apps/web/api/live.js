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

function alertFallback() {
  const features = [];
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

function driftFallback(payload) {
  const features = (payload?.features || [])
    .filter((feature) => ['LineString', 'Polygon', 'Point'].includes(feature?.geometry?.type))
    .map((feature) => ({
      type: 'Feature',
      geometry: feature.geometry,
      properties: {
        type: feature.properties?.type || null,
        intel_severity: 'medium',
        intel_source: 'SeaCommons engine',
        auto_drift: true,
        compatibility_mode: true,
      },
    }));
  return {
    type: 'FeatureCollection',
    features,
    meta: {
      schema: 'org.seacommons.live-drift/v1',
      drifts: features.filter((feature) => feature.geometry.type === 'LineString').length,
      generated_at: new Date().toISOString(),
      compatibility_mode: true,
    },
  };
}

function emptyDriftFallback() {
  return {
    type: 'FeatureCollection',
    features: [],
    meta: {
      schema: 'org.seacommons.live-drift/v1',
      drifts: 0,
      generated_at: new Date().toISOString(),
      compatibility_mode: true,
      visibility: 'play_only',
    },
  };
}

function archiveFallback(payload) {
  const archives = (Array.isArray(payload) ? payload : [])
    .filter((alert) => alert?.status === 'completed')
    .slice(0, 8)
    .map((alert) => ({
      id: alert.event_id,
      timestamp: alert.event?.timestamp || null,
      lat: Number(alert.event?.lat),
      lon: Number(alert.event?.lon),
      vessel_type: alert.event?.vessel_type || 'case',
      persons: Number(alert.event?.persons || 1),
    }));
  return { archives, generated_at: new Date().toISOString(), compatibility_mode: true };
}

function sourceFallback(summary) {
  const configured = {
    twitter: Boolean(summary?.channels?.twitter?.configured),
    whatsapp: Boolean(summary?.channels?.whatsapp?.configured),
    telegram: Boolean(summary?.channels?.telegram?.configured),
    partner: Boolean(summary?.channels?.partner_webhook?.configured),
  };
  const definitions = [
    ['X / Twitter', 'twitter', configured.twitter],
    ['WhatsApp intake', 'whatsapp', configured.whatsapp],
    ['Telegram intake', 'telegram', configured.telegram],
    ['Partner webhook', 'partner', configured.partner],
  ];
  const sources = definitions.map(([name, type, active]) => ({
    name,
    type,
    status: active ? 'active' : 'offline',
    last_poll_at: active ? summary?.generated_at || null : null,
    events_last_hour: 0,
    total_events: 0,
    consecutive_errors: 0,
  }));
  const active = sources.filter((source) => source.status === 'active').length;
  return {
    sources,
    summary: {
      total: sources.length,
      active,
      degraded: 0,
      offline: sources.length - active,
    },
    channels: {
      twitter: configured.twitter,
      whatsapp: configured.whatsapp,
      telegram: configured.telegram,
      partner_webhook: configured.partner,
    },
    collector: {
      mode: 'continuous',
      browser_independent: true,
      persistence: 'server',
      supervisor: 'systemd',
    },
    generated_at: new Date().toISOString(),
    compatibility_mode: true,
  };
}

export default async function handler(req, res) {
  res.setHeader('cache-control', 'no-store');
  res.setHeader('content-type', 'application/json; charset=utf-8');
  res.setHeader('x-seacommons-live-version', '2026-08-01.2');
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    res.setHeader('allow', 'GET, HEAD');
    return res.status(405).json({ detail: 'Method not allowed' });
  }

  const resource = Array.isArray(req.query.resource) ? req.query.resource[0] : req.query.resource;
  const eventId = Array.isArray(req.query.event_id) ? req.query.event_id[0] : req.query.event_id;
  const safeEventId = typeof eventId === 'string' && /^[a-zA-Z0-9-]{6,80}$/.test(eventId)
    ? eventId
    : '';
  const requestedLimit = Math.min(500, Math.max(1, Number.parseInt(req.query.limit, 10) || 500));
  const requestedDays = Math.min(365, Math.max(1, Number.parseInt(req.query.days, 10) || 30));
  const upstreamPath = resource === 'sources'
    ? '/api/v1/live/sources'
    : resource === 'drifts'
      ? '/api/v1/live/drifts?limit=100'
      : resource === 'archives'
        ? '/api/v1/live/archives?limit=8'
        : resource === 'archive' && safeEventId
          ? `/api/v1/live/archives/${safeEventId}/geojson`
          : `/api/v1/live/signals?limit=${requestedLimit}&days=${requestedDays}`;
  try {
    const upstream = await requestJson(upstreamPath);
    if (upstream.status === 200 && upstream.data) {
      res.setHeader('x-seacommons-live-source', 'engine');
      return res.status(200).json(upstream.data);
    }

    let fallback;
    if (resource === 'sources') {
      fallback = sourceFallback((await requestJson('/api/v1/ops/summary')).data);
    } else if (resource === 'drifts') {
      fallback = emptyDriftFallback();
    } else if (resource === 'archives') {
      fallback = archiveFallback((await requestJson('/api/v1/alerts')).data);
    } else if (resource === 'archive' && safeEventId) {
      fallback = driftFallback((await requestJson(`/api/v1/alert/${safeEventId}/geojson`)).data);
    } else {
      fallback = alertFallback();
    }
    res.setHeader('x-seacommons-live-source', 'compatibility');
    return res.status(200).json(fallback);
  } catch {
    return res.status(502).json({ detail: 'SeaCommons live feed unavailable' });
  }
}

export const config = {
  maxDuration: 30,
};
