import { useEffect, useRef, useState } from 'react';

import { edgeSnapshotIsUsable } from '../simulation/liveTracking.js';
import { fetchJson } from '../services/api/client.js';
import {
  edgeSnapshotToFeatures,
  receivedSignalFeatures,
} from '../features/live/normalize.js';

const PUBLIC_CACHE_KEY = 'seacommons_live_signal_cache_v2';
const OPERATOR_CACHE_KEY = 'seacommons_intel_cache';

function cacheKey(isPublicLiveHost, liveMode = 'humanitarian') {
  return isPublicLiveHost ? `${PUBLIC_CACHE_KEY}_${liveMode}` : OPERATOR_CACHE_KEY;
}

function loadCachedEvents(isPublicLiveHost, liveMode = 'humanitarian') {
  try {
    const cached = window.localStorage.getItem(cacheKey(isPublicLiveHost, liveMode));
    if (!cached) return [];
    const parsed = JSON.parse(cached);
    if (!Array.isArray(parsed)) return [];
    const cutoff = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString();
    const recent = parsed.filter((event) => (event?.properties?.timestamp_utc || '') >= cutoff);
    const normalized = isPublicLiveHost ? receivedSignalFeatures(recent) : recent;
    return isPublicLiveHost && liveMode === 'humanitarian'
      ? alarmPhoneOnly(normalized)
      : normalized;
  } catch {
    return [];
  }
}

function storeCachedEvents(isPublicLiveHost, features, liveMode = 'humanitarian') {
  try {
    window.localStorage.setItem(cacheKey(isPublicLiveHost, liveMode), JSON.stringify(features));
  } catch {
    // The live in-memory state remains authoritative when storage is unavailable/full.
  }
}

/** Own the Live/Intel transport lifecycle while exposing only UI-facing state. */
export function useLiveFeed({
  apiBase,
  edgeBase,
  isPublicLiveHost,
  liveMode = 'humanitarian',
  onCriticalDistress,
  onDriftUpdate,
}) {
  const [intelEvents, setIntelEvents] = useState(
    () => loadCachedEvents(isPublicLiveHost, liveMode),
  );
  const [liveModeCounts, setLiveModeCounts] = useState({ humanitarian: null, security: null });
  const [intelConnected, setIntelConnected] = useState(false);
  const [intelMode, setIntelMode] = useState('offline');
  const edgeLiveActiveRef = useRef(false);
  const onCriticalDistressRef = useRef(onCriticalDistress);
  const onDriftUpdateRef = useRef(onDriftUpdate);

  useEffect(() => {
    onCriticalDistressRef.current = onCriticalDistress;
    onDriftUpdateRef.current = onDriftUpdate;
  }, [onCriticalDistress, onDriftUpdate]);

  useEffect(() => {
    if (isPublicLiveHost) setIntelEvents(loadCachedEvents(true, liveMode));
  }, [isPublicLiveHost, liveMode]);

  // VM-hosted Intel/Live transport: polling starts immediately and WebSocket
  // takes over when a direct backend origin supports upgrades.
  useEffect(() => {
    if (isPublicLiveHost && edgeBase && liveMode === 'humanitarian') return undefined;
    const wsBase = apiBase.replace(/^http/, 'ws');
    const feedPath = isPublicLiveHost
      ? `/api/v1/live/signals?limit=150&days=30&mode=${encodeURIComponent(liveMode)}`
      : '/api/v1/intel?limit=200&days=30';
    const streamPath = isPublicLiveHost
      ? `/api/v1/live/stream?mode=${encodeURIComponent(liveMode)}`
      : '/ws/intel';
    const pollIntervalMs = isPublicLiveHost ? 10000 : 30000;
    let ws = null;
    let pollTimer = null;
    let wsAlive = true;
    let polling = false;
    let alive = true;

    function handleWsMessage(event) {
      if (edgeLiveActiveRef.current) return;
      try {
        const message = JSON.parse(event.data);
        if (message.type === 'ping') return;
        if (message.type === 'snapshot') {
          setIntelEvents(
            isPublicLiveHost
              ? receivedSignalFeatures(message.features)
              : Array.isArray(message.features) ? message.features : [],
          );
        } else if (message.type === 'Feature') {
          const incoming = isPublicLiveHost ? receivedSignalFeatures([message]) : [message];
          if (!incoming.length) return;
          setIntelEvents((previous) => {
            const incomingIds = new Set(
              incoming.map((feature) => feature.properties?.id).filter(Boolean),
            );
            const withoutStale = previous.filter(
              (feature) => !incomingIds.has(feature.properties?.id),
            );
            return [...incoming, ...withoutStale].slice(0, 300);
          });
          const properties = message.properties || {};
          if ((properties.type === 'distress' || properties.type === 'correlated_alert')
            && ['critical', 'high'].includes(properties.severity)) {
            onCriticalDistressRef.current?.(properties);
          }
        } else if (!isPublicLiveHost
          && message.type === 'event_update'
          && message.drift?.trajectory) {
          onDriftUpdateRef.current?.(message);
        }
      } catch {
        // Malformed WebSocket messages never replace the last valid state.
      }
    }

    async function pollOnce() {
      try {
        const data = await fetchJson(apiBase, feedPath);
        if (!alive || edgeLiveActiveRef.current) return;
        if (Array.isArray(data.features)) {
          const features = isPublicLiveHost
            ? receivedSignalFeatures(data.features)
            : data.features;
          setIntelEvents(features);
          storeCachedEvents(isPublicLiveHost, features, liveMode);
          if (isPublicLiveHost) {
            const counts = data.meta?.mode_counts;
            setLiveModeCounts((previous) => ({
              ...previous,
              ...(counts || { [liveMode]: features.length }),
            }));
          }
          setIntelConnected(true);
          setIntelMode((previous) => previous === 'ws' ? 'ws' : 'poll');
        }
      } catch {
        if (!alive || edgeLiveActiveRef.current) return;
        setIntelConnected(false);
        setIntelMode((previous) => previous === 'ws' ? 'ws' : 'offline');
      }
    }

    async function pollLoop() {
      if (!alive || polling) return;
      polling = true;
      while (alive) {
        await pollOnce();
        if (!alive) break;
        await new Promise((resolve) => {
          pollTimer = window.setTimeout(resolve, pollIntervalMs);
        });
      }
      polling = false;
    }

    function tryWebSocket() {
      if (!alive || !wsAlive) return;
      const token = window.__SEACOMMONS_ACCESS_TOKEN__;
      ws = token
        ? new WebSocket(`${wsBase}${streamPath}`, ['bearer', token])
        : new WebSocket(`${wsBase}${streamPath}`);
      const openTimer = window.setTimeout(() => {
        if (ws && ws.readyState !== WebSocket.OPEN) ws.close();
      }, 4000);
      ws.onopen = () => {
        window.clearTimeout(openTimer);
        if (edgeLiveActiveRef.current) return;
        setIntelConnected(true);
        setIntelMode('ws');
      };
      ws.onclose = () => {
        window.clearTimeout(openTimer);
        if (alive) wsAlive = false;
      };
      ws.onerror = () => {
        window.clearTimeout(openTimer);
        ws?.close();
      };
      ws.onmessage = handleWsMessage;
    }

    pollLoop();
    const apiHost = apiBase.replace(/^https?:\/\//, '').split('/')[0];
    const isDirectBackend = apiBase !== window.location.origin
      || /^(localhost|127\.|192\.168\.|10\.|172\.(1[6-9]|2\d|3[01])\.)/.test(apiHost)
      || /^\d+\.\d+\.\d+\.\d+(:\d+)?$/.test(apiHost);
    if (isDirectBackend) tryWebSocket();

    return () => {
      alive = false;
      wsAlive = false;
      window.clearTimeout(pollTimer);
      ws?.close();
    };
  }, [apiBase, edgeBase, isPublicLiveHost, liveMode]);

  // Public Live is edge-first. Oracle is a rate-limited backup only after
  // repeated edge failures; cached edge state stays visible during failure.
  useEffect(() => {
    if (!isPublicLiveHost || !edgeBase || liveMode !== 'humanitarian') return undefined;
    let alive = true;
    let ws = null;
    let pollTimer = null;
    let reconnectTimer = null;
    let countTimer = null;
    let consecutiveFailures = 0;
    let lastBackupAttempt = 0;

    function applySnapshot(snapshot, transport = 'poll') {
      if (!alive || !edgeSnapshotIsUsable(snapshot)) return false;
      const features = alarmPhoneOnly(edgeSnapshotToFeatures(snapshot));
      setIntelEvents(features);
      storeCachedEvents(true, features, 'humanitarian');
      setLiveModeCounts((previous) => ({ ...previous, humanitarian: features.length }));
      setIntelConnected(true);
      setIntelMode(transport);
      edgeLiveActiveRef.current = true;
      consecutiveFailures = 0;
      return true;
    }

    async function loadOracleBackup() {
      const now = Date.now();
      if (now - lastBackupAttempt < 60000) return;
      lastBackupAttempt = now;
      try {
        const data = await fetchJson(
          apiBase,
          '/api/v1/live/signals?limit=150&days=30&mode=humanitarian',
          undefined,
          3000,
        );
        if (!alive || !Array.isArray(data.features)) return;
        const features = receivedSignalFeatures(data.features);
        setIntelEvents(features);
        storeCachedEvents(true, features, 'humanitarian');
        if (data.meta?.mode_counts) setLiveModeCounts(data.meta.mode_counts);
        setIntelConnected(true);
        setIntelMode('poll');
      } catch {
        // Preserve the last valid cached edge snapshot.
      }
    }

    async function refreshModeCounts() {
      window.clearTimeout(countTimer);
      try {
        const data = await fetchJson(
          apiBase,
          '/api/v1/live/signals?limit=20&days=30&mode=all',
          undefined,
          5000,
        );
        if (alive && data.meta?.mode_counts) setLiveModeCounts(data.meta.mode_counts);
      } catch {
        // The current edge snapshot remains usable even when count enrichment fails.
      }
      if (alive) countTimer = window.setTimeout(refreshModeCounts, 60000);
    }

    async function pollSnapshot() {
      window.clearTimeout(pollTimer);
      try {
        const snapshot = await fetchJson(edgeBase, '/v1/live/snapshot', undefined, 4000);
        const transport = ws?.readyState === WebSocket.OPEN ? 'ws' : 'poll';
        if (!applySnapshot(snapshot, transport)) throw new Error('edge snapshot is unusable');
      } catch {
        if (!alive) return;
        consecutiveFailures += 1;
        edgeLiveActiveRef.current = false;
        setIntelConnected(false);
        setIntelMode('offline');
        if (consecutiveFailures >= 3) await loadOracleBackup();
      }
      if (alive) pollTimer = window.setTimeout(pollSnapshot, 10000);
    }

    function connectWebSocket() {
      if (!alive) return;
      ws = new WebSocket(`${edgeBase.replace(/^http/, 'ws')}/v1/live/stream`);
      const openTimer = window.setTimeout(() => {
        if (ws && ws.readyState !== WebSocket.OPEN) ws.close();
      }, 4000);
      ws.onopen = () => {
        window.clearTimeout(openTimer);
        setIntelConnected(true);
        setIntelMode('ws');
      };
      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          if (message.type === 'snapshot') {
            if (!applySnapshot(message, 'ws')) edgeLiveActiveRef.current = false;
          } else if (['event', 'remove', 'source_health'].includes(message.type)) {
            pollSnapshot();
          }
        } catch {
          // Malformed messages never replace the last valid snapshot.
        }
      };
      ws.onclose = () => {
        window.clearTimeout(openTimer);
        if (alive) reconnectTimer = window.setTimeout(connectWebSocket, 5000);
      };
      ws.onerror = () => {
        window.clearTimeout(openTimer);
        ws?.close();
      };
    }

    pollSnapshot();
    refreshModeCounts();
    connectWebSocket();

    return () => {
      alive = false;
      edgeLiveActiveRef.current = false;
      window.clearTimeout(pollTimer);
      window.clearTimeout(reconnectTimer);
      window.clearTimeout(countTimer);
      ws?.close();
    };
  }, [apiBase, edgeBase, isPublicLiveHost, liveMode]);

  return {
    intelEvents,
    setIntelEvents,
    intelConnected,
    intelMode,
    liveModeCounts,
  };
}

function alarmPhoneOnly(features) {
  return features.filter((feature) => (
    String(feature?.properties?.source || '').toLowerCase().replace(/[^a-z0-9]/g, '') === 'alarmphone'
  ));
}
