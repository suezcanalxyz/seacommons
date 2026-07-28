import http from 'node:http';

const UPSTREAM_HOST = '204.216.210.155';
const ALLOWED_UPSTREAMS = new Set(['api.seacommons.org', 'demo-api.seacommons.org']);
const LIVE_HOSTS = new Set(['live.seacommons.org', 'console.seacommons.org']);
const PLAY_HOSTS = new Set(['play.seacommons.org', 'demo.seacommons.org']);
const HOP_BY_HOP_HEADERS = new Set([
  'connection',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'te',
  'trailer',
  'transfer-encoding',
  'upgrade',
]);

function first(value) {
  return Array.isArray(value) ? value[0] : value;
}

function upstreamPath(query) {
  if (first(query.health) === '1') return '/health';

  const path = String(first(query.path) || '').replace(/^\/+/, '');
  const search = new URLSearchParams();
  for (const [name, value] of Object.entries(query)) {
    if (name === 'path' || name === 'health') continue;
    for (const item of Array.isArray(value) ? value : [value]) {
      if (item !== undefined) search.append(name, String(item));
    }
  }
  const suffix = search.toString();
  return `/api/${path}${suffix ? `?${suffix}` : ''}`;
}

function requestHostname(headers) {
  return String(headers.host || '').split(':')[0].trim().toLowerCase();
}

function selectUpstream(headers, query) {
  const configured = process.env.SEACOMMONS_UPSTREAM_VIRTUAL_HOST;
  if (configured && ALLOWED_UPSTREAMS.has(configured)) return configured;
  const hostname = requestHostname(headers);
  const path = String(first(query?.path) || '').replace(/^\/+/, '');
  const isPlaySimulation = PLAY_HOSTS.has(hostname)
    && (path === 'v1/alert' || path.startsWith('v1/alert/'));
  return LIVE_HOSTS.has(hostname) || isPlaySimulation
    ? 'api.seacommons.org'
    : 'demo-api.seacommons.org';
}

function requestHeaders(headers, upstreamVirtualHost) {
  const forwarded = {};
  for (const [name, value] of Object.entries(headers)) {
    const lower = name.toLowerCase();
    if (lower === 'host' || HOP_BY_HOP_HEADERS.has(lower)) continue;
    if (value !== undefined) forwarded[name] = value;
  }
  forwarded.host = upstreamVirtualHost;
  forwarded['x-forwarded-host'] = headers.host || 'seacommons.vercel.app';
  forwarded['x-forwarded-proto'] = 'https';
  return forwarded;
}

export default function handler(req, res) {
  const upstreamVirtualHost = selectUpstream(req.headers, req.query || {});
  const upstream = http.request(
    {
      hostname: UPSTREAM_HOST,
      port: 80,
      method: req.method,
      path: upstreamPath(req.query || {}),
      headers: requestHeaders(req.headers, upstreamVirtualHost),
    },
    (response) => {
      res.statusCode = response.statusCode || 502;
      for (const [name, value] of Object.entries(response.headers)) {
        if (!HOP_BY_HOP_HEADERS.has(name.toLowerCase()) && value !== undefined) {
          res.setHeader(name, value);
        }
      }
      res.setHeader('x-seacommons-proxy', upstreamVirtualHost);
      response.pipe(res);
    },
  );

  upstream.setTimeout(28_000, () => {
    upstream.destroy(new Error('SeaCommons API timed out'));
  });
  upstream.on('error', (error) => {
    if (res.headersSent) {
      res.destroy(error);
      return;
    }
    res.status(502).json({ detail: 'SeaCommons API unavailable' });
  });
  req.pipe(upstream);
}

export const config = {
  api: {
    bodyParser: false,
  },
  maxDuration: 30,
};
