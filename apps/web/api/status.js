import http from 'node:http';
import https from 'node:https';

import {
  API_VHOST,
  UPSTREAM_HOST,
  UPSTREAM_PORT,
} from './_upstream.js';

const EDGE_HOST = 'seacommons-edge.seacommons.workers.dev';
const RESPONSE_LIMIT = 1024 * 1024;

function requestJson({
  transport,
  hostname,
  port,
  path,
  headers = {},
  timeoutMs = 5000,
}) {
  const client = transport === 'https' ? https : http;
  const startedAt = performance.now();
  return new Promise((resolve) => {
    const request = client.request(
      { hostname, port, path, method: 'GET', headers },
      (response) => {
        const chunks = [];
        let size = 0;
        response.on('data', (chunk) => {
          size += chunk.length;
          if (size <= RESPONSE_LIMIT) chunks.push(chunk);
        });
        response.on('end', () => {
          const latencyMs = Math.round(performance.now() - startedAt);
          if (size > RESPONSE_LIMIT) {
            resolve({ ok: false, statusCode: response.statusCode, latencyMs, error: 'response too large' });
            return;
          }
          try {
            const data = JSON.parse(Buffer.concat(chunks).toString('utf8'));
            resolve({
              ok: response.statusCode >= 200 && response.statusCode < 300,
              statusCode: response.statusCode,
              latencyMs,
              data,
            });
          } catch {
            resolve({ ok: false, statusCode: response.statusCode, latencyMs, error: 'invalid JSON' });
          }
        });
      },
    );
    request.setTimeout(timeoutMs, () => request.destroy(new Error('timeout')));
    request.on('error', (error) => {
      resolve({
        ok: false,
        statusCode: null,
        latencyMs: Math.round(performance.now() - startedAt),
        error: error.message === 'timeout' ? 'timeout' : 'connection failed',
      });
    });
    request.end();
  });
}

function originRequest(path) {
  return requestJson({
    transport: 'http',
    hostname: UPSTREAM_HOST,
    port: UPSTREAM_PORT,
    path,
    headers: {
      host: API_VHOST,
      'x-forwarded-host': 'status.seacommons.org',
      'x-forwarded-proto': 'https',
    },
  });
}

function publicApiRequest() {
  return requestJson({
    transport: 'https',
    hostname: API_VHOST,
    port: 443,
    path: '/health',
    timeoutMs: 3500,
  });
}

function edgeRequest() {
  return requestJson({
    transport: 'https',
    hostname: EDGE_HOST,
    port: 443,
    path: '/v1/live/status',
  });
}

function check(id, status, latencyMs, detail) {
  return { id, status, latency_ms: latencyMs, detail };
}

export async function buildStatusSnapshot() {
  const [publicApi, health, ready, modes, sources, edge] = await Promise.all([
    publicApiRequest(),
    originRequest('/health'),
    originRequest('/ready'),
    originRequest('/api/v1/live/signals?limit=500&days=30&mode=all'),
    originRequest('/api/v1/live/sources'),
    edgeRequest(),
  ]);

  const counts = modes.data?.meta?.mode_counts || {};
  const sourceRows = Array.isArray(sources.data?.sources) ? sources.data.sources : [];
  const sourceSummary = sources.data?.summary || {};
  const edgeLive = edge.ok && edge.data?.status === 'live';
  const sourceDegraded = Number(sourceSummary.degraded || 0) > 0
    || Number(sourceSummary.offline || 0) > 0;

  const checks = [
    check(
      'public_api',
      publicApi.ok ? 'live' : 'down',
      publicApi.latencyMs,
      publicApi.ok
        ? 'DNS, TLS and public proxy are reachable'
        : `Public DNS/TLS path unavailable (${publicApi.error || `HTTP ${publicApi.statusCode}`})`,
    ),
    check(
      'origin',
      health.ok ? 'live' : 'down',
      health.latencyMs,
      health.ok ? `Oracle ${UPSTREAM_HOST} is operational` : 'Oracle API origin is unavailable',
    ),
    check(
      'database',
      ready.ok && ready.data?.database === 'ok' ? 'live' : 'down',
      ready.latencyMs,
      ready.ok ? 'API readiness and database check passed' : 'Readiness check failed',
    ),
    check(
      'edge',
      edgeLive ? 'live' : edge.ok ? 'degraded' : 'down',
      edge.latencyMs,
      edgeLive
        ? `Cloudflare heartbeat fresh · ${Number(edge.data?.event_count || 0)} retained events`
        : edge.ok ? `Cloudflare reports ${edge.data?.status || 'degraded'}` : 'Cloudflare Live edge unavailable',
    ),
    check(
      'modes',
      modes.ok && Number.isFinite(Number(counts.humanitarian))
        && Number.isFinite(Number(counts.security)) ? 'live' : 'down',
      modes.latencyMs,
      modes.ok
        ? `${Number(counts.humanitarian || 0)} humanitarian · ${Number(counts.security || 0)} security`
        : 'Mode-aware Live feed unavailable',
    ),
    check(
      'sources',
      sources.ok ? sourceDegraded ? 'degraded' : 'live' : 'down',
      sources.latencyMs,
      sources.ok
        ? `${Number(sourceSummary.active || 0)} active · ${Number(sourceSummary.degraded || 0)} degraded · ${Number(sourceSummary.offline || 0)} offline`
        : 'Source registry unavailable',
    ),
  ];

  const criticalDown = checks.some((item) => (
    ['origin', 'database', 'edge', 'modes'].includes(item.id) && item.status === 'down'
  ));
  const degraded = checks.some((item) => item.status !== 'live');

  return {
    status: criticalDown ? 'down' : degraded ? 'degraded' : 'live',
    generated_at: new Date().toISOString(),
    checks,
    mode_counts: {
      humanitarian: Number(counts.humanitarian || 0),
      security: Number(counts.security || 0),
    },
    sources: sourceRows.map((source) => ({
      name: source.name,
      type: source.type,
      status: source.status,
      pipeline_status: source.pipeline_status,
      source_status: source.source_status,
      configured: Number(source.configured || 0),
      reachable: Number(source.reachable || 0),
      events_last_hour: Number(source.events_last_hour || 0),
      handles: Array.isArray(source.handles)
        ? source.handles.map((handle) => ({ name: handle.name, status: handle.status }))
        : [],
    })),
  };
}

export default async function handler(req, res) {
  res.setHeader('cache-control', 'no-store');
  res.setHeader('content-type', 'application/json; charset=utf-8');
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    res.setHeader('allow', 'GET, HEAD');
    return res.status(405).json({ detail: 'Method not allowed' });
  }
  const snapshot = await buildStatusSnapshot();
  return res.status(200).json(snapshot);
}

export const config = { maxDuration: 15 };
