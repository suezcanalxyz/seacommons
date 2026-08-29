import React, { useEffect, useRef, useState } from 'react';
import { fetchJson } from '../services/api/client.js';
import { receivedSignalFeatures } from '../features/live/normalize.js';
import { resolveSiteApiBase, LIVE_HOST_URL } from './liveApi.js';

const POLL_MS = 20000;
const MAX_ITEMS = 5;

// Status-color mapping is fixed brand-wide (see ui/ui.css): rose = critical,
// amber = unconfirmed/uncertain, sea = nominal. Never a per-module color.
function severityToken(properties) {
  const severity = String(properties?.severity || '').toLowerCase();
  if (severity === 'critical' || severity === 'high') return 'rose';
  if (severity === 'medium') return 'amber';
  if (properties?.verification_status === 'unverified_public_source') return 'amber';
  return 'sea';
}

function relativeTime(isoString) {
  const then = Date.parse(isoString);
  if (!Number.isFinite(then)) return '';
  const minutes = Math.max(0, Math.round((Date.now() - then) / 60000));
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export default function LiveSignalStrip() {
  const [items, setItems] = useState(null); // null = loading, [] = confirmed empty
  const [failed, setFailed] = useState(false);
  const aliveRef = useRef(true);

  useEffect(() => {
    aliveRef.current = true;
    const apiBase = resolveSiteApiBase();

    async function poll() {
      try {
        const data = await fetchJson(apiBase, '/api/v1/live/signals?limit=30&days=2', undefined, 6000);
        if (!aliveRef.current) return;
        const features = receivedSignalFeatures(data.features)
          .filter((f) => f.properties?.timestamp_utc)
          .sort((a, b) => Date.parse(b.properties.timestamp_utc) - Date.parse(a.properties.timestamp_utc))
          .slice(0, MAX_ITEMS);
        setItems(features);
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

  const showEmpty = items !== null && items.length === 0 && !failed;

  return (
    <div className="live-strip" aria-label="Live distress signals">
      <span className="live-strip__label">
        <i className={`live-strip__pulse is-${failed ? 'idle' : 'live'}`} aria-hidden="true" />
        Live signals
      </span>
      <ul className="live-strip__items">
        {items === null && !failed && (
          <li className="live-strip__note">Connecting to the public feed…</li>
        )}
        {failed && (
          <li className="live-strip__note">Live feed unavailable — try live.seacommons.org directly.</li>
        )}
        {showEmpty && (
          <li className="live-strip__note">No active signals right now.</li>
        )}
        {items?.map((feature) => {
          const properties = feature.properties;
          return (
            <li key={properties.id}>
              <a href={LIVE_HOST_URL} className="live-strip__item">
                <i className={`live-strip__dot is-${severityToken(properties)}`} aria-hidden="true" />
                <span className="live-strip__title">{properties.title}</span>
                <span className="live-strip__time mono">{relativeTime(properties.timestamp_utc)}</span>
              </a>
            </li>
          );
        })}
      </ul>
      <a className="live-strip__cta" href={LIVE_HOST_URL}>
        Open Live <span aria-hidden="true">↗</span>
      </a>
    </div>
  );
}
