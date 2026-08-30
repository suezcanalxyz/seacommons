import React, { useEffect, useState } from 'react';
import { fetchJson } from '../services/api/client.js';

const POLL_MS = 20000;

const CHECK_COPY = {
  public_api: {
    label: 'Public API hostname',
    endpoint: 'https://api.seacommons.org/health',
    description: 'Authoritative DNS, TLS certificate and the public reverse-proxy path.',
  },
  origin: {
    label: 'Operational API origin',
    endpoint: 'Oracle /health',
    description: 'FastAPI, monitors and scheduler on the canonical Oracle node.',
  },
  database: {
    label: 'Database readiness',
    endpoint: 'Oracle /ready',
    description: 'Application readiness including a real database connectivity check.',
  },
  edge: {
    label: 'Public Live edge',
    endpoint: 'Cloudflare /v1/live/status',
    description: 'Durable Live distribution, publisher heartbeat and retained-event state.',
  },
  modes: {
    label: 'Live data modes',
    endpoint: 'GET /api/v1/live/signals?mode=all',
    description: 'Canonical Humanitarian and Maritime Security projections.',
  },
  sources: {
    label: 'OSINT source availability',
    endpoint: 'GET /api/v1/live/sources',
    description: 'Collector pipelines and individual source/handle reachability.',
  },
};

function relativeTime(value) {
  if (!value) return 'never';
  const seconds = Math.max(0, Math.round((Date.now() - Date.parse(value)) / 1000));
  if (seconds < 10) return 'just now';
  if (seconds < 60) return `${seconds}s ago`;
  return `${Math.floor(seconds / 60)}m ago`;
}

function StatusRow({ item }) {
  const copy = CHECK_COPY[item.id] || { label: item.id, endpoint: '', description: '' };
  return (
    <article className="status-row">
      <div className="status-row__head">
        <span className={`status-dot is-${item.status}`} aria-hidden="true" />
        <span className="status-row__label">{copy.label}</span>
        <span className="status-row__state">{item.status}</span>
      </div>
      <p className="status-row__desc">{copy.description}</p>
      <div className="status-row__meta">
        <code>{copy.endpoint}</code>
        <span>{item.detail}</span>
        {Number.isFinite(item.latency_ms) && <span>{item.latency_ms} ms</span>}
      </div>
    </article>
  );
}

function SourceCard({ source }) {
  const handles = Array.isArray(source.handles) ? source.handles : [];
  return (
    <article className="status-source-card">
      <div className="status-source-card__head">
        <span className={`status-dot is-${source.status === 'active' ? 'live' : source.status}`} />
        <strong>{source.name}</strong>
        <span>{source.status}</span>
      </div>
      <div className="status-source-card__metrics">
        <span>pipeline <b>{source.pipeline_status || source.status}</b></span>
        <span>sources <b>{source.source_status || 'unknown'}</b></span>
        {source.configured > 0 && <span>reachable <b>{source.reachable}/{source.configured}</b></span>}
        <span>events/h <b>{source.events_last_hour}</b></span>
      </div>
      {handles.length > 0 && (
        <div className="status-source-card__handles">
          {handles.map((handle) => (
            <span key={handle.name}>
              <i className={`status-dot is-${handle.status === 'healthy' ? 'live' : handle.status === 'unavailable' ? 'down' : 'degraded'}`} />
              {handle.name} · {handle.status}
            </span>
          ))}
        </div>
      )}
    </article>
  );
}

export default function StatusApp() {
  const [snapshot, setSnapshot] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let alive = true;
    async function refresh() {
      try {
        const next = await fetchJson('', '/api/status', undefined, 12000);
        if (alive) {
          setSnapshot(next);
          setError('');
        }
      } catch (requestError) {
        if (alive) setError(requestError?.message || 'Status service unavailable');
      }
    }
    refresh();
    const timer = window.setInterval(refresh, POLL_MS);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, []);

  const overall = error ? 'down' : snapshot?.status || 'checking';
  const checks = Array.isArray(snapshot?.checks) ? snapshot.checks : [];
  const sources = Array.isArray(snapshot?.sources) ? snapshot.sources : [];

  return (
    <main className="status-page">
      <header className="status-header">
        <a className="status-brand" href="/">SEA COMMONS</a>
        <div className="status-overall">
          <span className={`status-dot is-${overall}`} />
          <span>System status</span>
          <strong>{overall}</strong>
        </div>
        <h1>Infrastructure status</h1>
        <p>
          Independent checks of the public hostname, Oracle origin, database,
          Cloudflare Live edge and OSINT acquisition. Refreshed every 20 seconds.
        </p>
        <div className="status-updated">
          {error || (snapshot ? `Updated ${relativeTime(snapshot.generated_at)}` : 'Running checks…')}
        </div>
      </header>

      <section className="status-mode-grid" aria-label="Live mode counts">
        <div><span>Humanitarian</span><strong>{snapshot?.mode_counts?.humanitarian ?? '—'}</strong></div>
        <div><span>Maritime security</span><strong>{snapshot?.mode_counts?.security ?? '—'}</strong></div>
      </section>

      <section className="status-section">
        <div className="status-section__head"><span>Services</span><small>REAL-TIME</small></div>
        <div className="status-list" aria-label="Service status">
          {checks.length > 0
            ? checks.map((item) => <StatusRow item={item} key={item.id} />)
            : <div className="status-row status-row--loading">Checking infrastructure…</div>}
        </div>
      </section>

      <section className="status-section">
        <div className="status-section__head"><span>Source health</span><small>PIPELINE / AVAILABILITY</small></div>
        <div className="status-source-grid">
          {sources.map((source) => <SourceCard source={source} key={source.name} />)}
        </div>
      </section>

      <section className="status-legend">
        <span><i className="status-dot is-live" /> Live</span>
        <span><i className="status-dot is-degraded" /> Degraded</span>
        <span><i className="status-dot is-down" /> Down</span>
      </section>

      <footer className="status-footer">
        <a href="/">← Back to SeaCommons</a>
        <a href="https://github.com/suezcanalxyz/seacommons">Source code</a>
      </footer>
    </main>
  );
}
