import React, { useEffect, useRef, useState } from 'react';
import { fetchJson } from '../services/api/client.js';

const POLL_MS = 20000;

// Every check below goes through apps/web/api/live.js, which always dials the
// operational backend by its direct IP (apps/web/api/_upstream.js) regardless
// of which host served this page — the same route the public Live feed and
// the marketing site's header ticker use. api.seacommons.org's DNS record
// points at a dead address; this page never touches it, so it reflects the
// real backend, not a routing artifact.
const ENDPOINTS = [
  {
    id: 'signals',
    method: 'GET',
    path: '/api/v1/live/signals?limit=1&days=2',
    label: 'Distress & maritime signals',
    description: 'Public, privacy-filtered feed of maritime distress and correlated alert signals. Powers live.seacommons.org and the homepage live strip.',
  },
  {
    id: 'sources',
    method: 'GET',
    path: '/api/v1/live/sources',
    label: 'Source health',
    description: 'Per-channel intake status (X/Twitter, WhatsApp, Telegram, partner webhook) — which public sources are currently configured and active.',
  },
  {
    id: 'drifts',
    method: 'GET',
    path: '/api/v1/live/drifts?limit=1',
    label: 'Drift trajectories',
    description: 'Computed drift trajectories and uncertainty envelopes for active cases, as GeoJSON.',
  },
  {
    id: 'archives',
    method: 'GET',
    path: '/api/v1/live/archives?limit=1',
    label: 'Resolved case archive',
    description: 'Read-only archive of resolved/closed cases, stripped of live positional detail.',
  },
];

function useEndpointStatus(endpoint) {
  const [state, setState] = useState({ status: 'checking', latencyMs: null, checkedAt: null, detail: '' });
  const aliveRef = useRef(true);

  useEffect(() => {
    aliveRef.current = true;

    async function check() {
      const startedAt = performance.now();
      try {
        const data = await fetchJson('', endpoint.path, undefined, 8000);
        if (!aliveRef.current) return;
        const latencyMs = Math.round(performance.now() - startedAt);
        const isFallback = data?.meta?.compatibility_mode === true;
        setState({
          status: isFallback ? 'degraded' : 'live',
          latencyMs,
          checkedAt: new Date(),
          detail: isFallback ? 'Responding with fallback data — operational engine unreachable' : 'Live, from the operational engine',
        });
      } catch (error) {
        if (!aliveRef.current) return;
        setState({
          status: 'down',
          latencyMs: null,
          checkedAt: new Date(),
          detail: error?.message || 'Request failed',
        });
      }
    }

    check();
    const timer = window.setInterval(check, POLL_MS);
    return () => {
      aliveRef.current = false;
      window.clearInterval(timer);
    };
  }, [endpoint.path]);

  return state;
}

function StatusRow({ endpoint }) {
  const { status, latencyMs, checkedAt, detail } = useEndpointStatus(endpoint);
  return (
    <div className="status-row">
      <div className="status-row__head">
        <span className={`status-dot is-${status}`} aria-hidden="true" />
        <span className="status-row__label">{endpoint.label}</span>
        <span className="status-row__state">{status === 'checking' ? 'Checking…' : status}</span>
      </div>
      <p className="status-row__desc">{endpoint.description}</p>
      <div className="status-row__meta">
        <code>{endpoint.method} {endpoint.path}</code>
        <span>{detail}</span>
        {latencyMs !== null && <span>{latencyMs} ms</span>}
        {checkedAt && <span className="mono">Checked {checkedAt.toISOString().slice(11, 19)} UTC</span>}
      </div>
    </div>
  );
}

export default function StatusApp() {
  return (
    <main className="status-page">
      <header className="status-header">
        <a className="status-brand" href="/">SEA COMMONS</a>
        <h1>API status</h1>
        <p>
          Real-time checks against the public Live API, run from your browser on every load and every 20s after.
          Each row below is also the endpoint documentation — method, path, and what it returns.
        </p>
      </header>

      <section className="status-list" aria-label="Endpoint status">
        {ENDPOINTS.map((endpoint) => <StatusRow endpoint={endpoint} key={endpoint.id} />)}
      </section>

      <section className="status-legend">
        <span><i className="status-dot is-live" /> Live — served by the operational engine</span>
        <span><i className="status-dot is-degraded" /> Degraded — responding, but with fallback data</span>
        <span><i className="status-dot is-down" /> Down — request failed or timed out</span>
      </section>

      <footer className="status-footer">
        <a href="/">← Back to SeaCommons</a>
      </footer>
    </main>
  );
}
