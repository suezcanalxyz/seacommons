import http from 'node:http';

import {
  ALLOWED_UPSTREAMS,
  API_VHOST,
  DEMO_VHOST,
  LIVE_HOSTS,
  UPSTREAM_HOST,
  UPSTREAM_PORT,
} from './_upstream.js';
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
  if (first(query.ready) === '1') return '/ready';
  const rootPath = first(query.root);
  if (rootPath === 'docs') return '/docs';
  if (rootPath === 'redoc') return '/redoc';
  if (rootPath === 'openapi') return '/openapi.json';

  const path = String(first(query.path) || '').replace(/^\/+/, '');
  const search = new URLSearchParams();
  for (const [name, value] of Object.entries(query)) {
    if (name === 'path' || name === 'health' || name === 'ready' || name === 'root') continue;
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

export function selectUpstream(headers) {
  // Futures must always target the operational origin, not a demo override.
  if (requestHostname(headers) === 'futures.seacommons.org') return API_VHOST;
  const configured = process.env.SEACOMMONS_UPSTREAM_VIRTUAL_HOST;
  if (configured && ALLOWED_UPSTREAMS.has(configured)) return configured;
  const hostname = requestHostname(headers);
  return LIVE_HOSTS.has(hostname) ? API_VHOST : DEMO_VHOST;
}

// Only explicitly published, anonymous read contracts may be cached.
// Futures/operator data and all mutations must pass through uncached.
export function publicProxyCacheSeconds(headers, method, path, status = 200, upstreamHeaders = {}) {
  if (!['GET', 'HEAD'].includes(method) || status !== 200) return 0;
  if (headers.authorization || headers.cookie || headers['x-api-key']) return 0;
  if (upstreamHeaders['set-cookie']) return 0;
  if (String(upstreamHeaders.vary || '').split(',').some(item => ['authorization', 'cookie', '*'].includes(item.trim().toLowerCase()))) return 0;
  const host = requestHostname(headers);
  const pathname = String(path).split('?')[0];
  if (['seacommons.org', 'play.seacommons.org'].includes(host)) {
    if (pathname === '/api/v1/play/counts') return 45;
    if (pathname === '/api/v1/play/incidents' || (pathname.startsWith('/api/v1/play/incidents/') && pathname.endsWith('/timeline') && pathname.split('/').length === 7)) return 30;
  }
  if (host === 'live.seacommons.org') {
    if (pathname === '/api/v1/live/pipeline') return 20;
    if (['/api/v1/live/platforms', '/api/v1/live/ngo-vessels', '/api/v1/live/sanctioned-vessels'].includes(pathname)) return 15;
  }
  return 0;
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
  // Server-side only — the browser never sees this. Interim compensating
  // control while the backend has no OIDC provider deployed yet: without
  // it, every operator-only route (case data, intel writes, forensic
  // records) is reachable by anyone who curls the API IP directly, since
  // AUTH_ENABLED is fail-open by design for local dev. Unset in Vercel env
  // (or on the backend) disables the check entirely.
  if (process.env.SEACOMMONS_INTERNAL_PROXY_SECRET) {
    forwarded['x-seacommons-internal'] = process.env.SEACOMMONS_INTERNAL_PROXY_SECRET;
  }
  return forwarded;
}

export default function handler(req, res) {
  const upstreamVirtualHost = selectUpstream(req.headers);
  const path = upstreamPath(req.query || {});
  const upstream = http.request(
    {
      hostname: UPSTREAM_HOST,
      port: UPSTREAM_PORT,
      method: req.method,
      path,
      headers: requestHeaders(req.headers, upstreamVirtualHost),
    },
    (response) => {
      res.statusCode = response.statusCode || 502;
      for (const [name, value] of Object.entries(response.headers)) {
        const lower = name.toLowerCase();
        if (['cache-control', 'cdn-cache-control', 'vercel-cdn-cache-control'].includes(lower)) continue; // never trust upstream cache directives
        if (!HOP_BY_HOP_HEADERS.has(lower) && value !== undefined) {
          res.setHeader(name, value);
        }
      }
      const seconds = publicProxyCacheSeconds(req.headers, req.method, path, res.statusCode, response.headers);
      if (seconds) {
        res.setHeader('cache-control', 'public, max-age=0, must-revalidate');
        res.setHeader('cdn-cache-control', `public, s-maxage=${seconds}, stale-while-revalidate=${Math.min(seconds, 30)}`);
        res.setHeader('x-seacommons-public-cache', `${seconds}s`);
      } else {
        res.setHeader('cache-control', 'no-store');
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
