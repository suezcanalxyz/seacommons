import React, { useEffect, useRef, useState } from 'react';
import { fetchJson } from '../services/api/client.js';
import { receivedSignalFeatures } from '../features/live/normalize.js';
import { resolveSiteApiBase, LIVE_HOST_URL } from './liveApi.js';

const POLL_MS = 20000;

// Status-color mapping is fixed brand-wide (see ui/ui.css): rose = critical,
// amber = unconfirmed/uncertain, sea = nominal. Never a per-module color.
function severityToken(properties) {
  const severity = String(properties?.severity || '').toLowerCase();
  if (severity === 'critical' || severity === 'high') return 'rose';
  if (severity === 'medium') return 'amber';
  if (properties?.verification_status === 'unverified_public_source') return 'amber';
  return 'sea';
}

/** Compact live-signal indicator that sits inline in the header, replacing the static tagline. */
export default function HeaderLive() {
  const [latest, setLatest] = useState(null); // undefined = none yet, null = confirmed empty
  const [failed, setFailed] = useState(false);
  const aliveRef = useRef(true);

  useEffect(() => {
    aliveRef.current = true;
    const apiBase = resolveSiteApiBase();

    async function poll() {
      try {
        const data = await fetchJson(apiBase, '/api/v1/live/signals?limit=30&days=2', undefined, 6000);
        if (!aliveRef.current) return;
        const [top] = receivedSignalFeatures(data.features)
          .filter((f) => f.properties?.timestamp_utc)
          .sort((a, b) => Date.parse(b.properties.timestamp_utc) - Date.parse(a.properties.timestamp_utc));
        setLatest(top ?? null);
        setFailed(false);
      } catch {
        if (!aliveRef.current) return;
        setFailed(true);
      }
    }

    poll();
    const timer = window.setInterval(poll, POLL_MS);
    return () => {
      aliveRef.current = false;
      window.clearInterval(timer);
    };
  }, []);

  const properties = latest?.properties;
  const status = failed
    ? 'Live feed unavailable'
    : latest === undefined
      ? 'Connecting…'
      : properties
        ? properties.title
        : 'No active signals';

  return (
    <a className="site-header__live" href={LIVE_HOST_URL} aria-label="Open Live — latest public signal">
      <i className={`site-header__live-dot ${properties ? `is-${severityToken(properties)}` : 'is-idle'}`} aria-hidden="true" />
      <span className="site-header__live-label">Live</span>
      <span className="site-header__live-status">{status}</span>
    </a>
  );
}
