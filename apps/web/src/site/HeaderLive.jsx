import React, { useEffect, useRef, useState } from 'react';
import { Ticker } from '../ui/index.js';
import { fetchJson } from '../services/api/client.js';
import { receivedSignalFeatures } from '../features/live/normalize.js';
import { resolveSiteApiBase, LIVE_HOST_URL } from './liveApi.js';

const POLL_MS = 20000;
const MAX_ITEMS_PER_CATEGORY = 16;

// Keep both evidence streams visible, with category sourced from the public API.
function signalCategory(properties) {
  const categories = [
    properties?.main_category, properties?.visual_category,
    properties?.maritime_domain, properties?.category_label,
  ].map(value => String(value || '').toLowerCase());
  return categories.some(value => /humanitarian|distress|search.and.rescue|sar.case/.test(value))
    ? 'humanitarian' : 'maritime';
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

/** Compact single-line live-signal ticker in the header, replacing the static tagline. */
export default function HeaderLive() {
  const [items, setItems] = useState(null); // null = loading, [] = confirmed empty
  const [failed, setFailed] = useState(false);
  const aliveRef = useRef(true);

  useEffect(() => {
    aliveRef.current = true;
    const apiBase = resolveSiteApiBase();
    let inFlight = false;

    async function poll() {
      if (document.visibilityState === 'hidden' || inFlight) return;
      inFlight = true;
      try {
        const data = await fetchJson(apiBase, '/api/v1/live/signals?limit=100&days=2', undefined, 6000);
        if (!aliveRef.current) return;
        const features = receivedSignalFeatures(data.features)
          .filter((f) => f.properties?.timestamp_utc)
          .sort((a, b) => Date.parse(b.properties.timestamp_utc) - Date.parse(a.properties.timestamp_utc))
          .slice(0, 100);
        setItems(features);
        setFailed(false);
      } catch {
        if (!aliveRef.current) return;
        setFailed(true);
      } finally {
        inFlight = false;
      }
    }

    poll();
    const onVisibility = () => {
      if (document.visibilityState === 'visible') poll();
    };
    document.addEventListener('visibilitychange', onVisibility);
    const timer = window.setInterval(poll, POLL_MS);
    return () => {
      aliveRef.current = false;
      document.removeEventListener('visibilitychange', onVisibility);
      window.clearInterval(timer);
    };
  }, []);

  const groups = [
    { key: 'maritime', label: 'MARITIME', color: 'sea' },
    { key: 'humanitarian', label: 'HUMANITARIAN', color: 'rose' },
  ];

  return (
    <div className="site-header__streams" aria-label="Latest public maritime and humanitarian signals">
      {groups.map(({ key, label, color }) => {
        const signals = items?.filter(f => signalCategory(f.properties) === key).slice(0, MAX_ITEMS_PER_CATEGORY);
        return (
          <a key={key} className="site-header__stream" href={LIVE_HOST_URL} aria-label={`Open LIVE — ${label.toLowerCase()} public observations`}>
            <i className={`site-header__live-dot is-${failed ? 'idle' : color}`} aria-hidden="true" />
            <span className="site-header__live-label">{label}</span>
            <span className="site-header__live-ticker">
              {failed && <span className="site-header__live-status">Feed unavailable</span>}
              {!failed && items === null && <span className="site-header__live-status">Connecting…</span>}
              {!failed && items && signals?.length === 0 && <span className="site-header__live-status">No recent public records</span>}
              {!failed && signals?.length > 0 && (
                <Ticker
                  duration={Math.max(20, signals.length * 4)}
                  separator="·"
                  items={signals.map(f => `${f.properties.title || 'Public observation'} — ${relativeTime(f.properties.timestamp_utc)}`)}
                />
              )}
            </span>
          </a>
        );
      })}
    </div>
  );
}
