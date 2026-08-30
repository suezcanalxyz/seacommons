// SPDX-License-Identifier: AGPL-3.0-or-later
// Where the same-origin /api proxy forwards to. Every value is env-driven so
// this repo can be deployed by anyone; the defaults are the reference
// deployment (seacommons.org) and are overridden with Vercel project env
// vars (see vercel.json).
//
// Filename starts with "_" so Vercel does not expose it as a route.

const DEFAULTS = {
  // Frankfurt A1 (instance-1159) operational API. Overridable with the
  // SEACOMMONS_UPSTREAM_HOST / _PORT Vercel env vars.
  host: '152.70.182.58',
  port: '80',
  apiVhost: 'api.seacommons.org',
  demoVhost: 'demo-api.seacommons.org',
  liveHosts: 'live.seacommons.org,console.seacommons.org,api.seacommons.org',
};

export const UPSTREAM_HOST = process.env.SEACOMMONS_UPSTREAM_HOST || DEFAULTS.host;
export const UPSTREAM_PORT = Number(process.env.SEACOMMONS_UPSTREAM_PORT || DEFAULTS.port);
export const API_VHOST = process.env.SEACOMMONS_API_VHOST || DEFAULTS.apiVhost;
export const DEMO_VHOST = process.env.SEACOMMONS_DEMO_VHOST || DEFAULTS.demoVhost;

export const ALLOWED_UPSTREAMS = new Set([API_VHOST, DEMO_VHOST]);

export const LIVE_HOSTS = new Set(
  (process.env.SEACOMMONS_LIVE_HOSTS || DEFAULTS.liveHosts)
    .split(',')
    .map((h) => h.trim().toLowerCase())
    .filter(Boolean),
);
