import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';

const ALARM_PHONE_SOURCE = 'Alarm Phone';
const SEV_ORDER = { critical: 0, high: 1, medium: 2, low: 3 };
const SEV_LABELS = ['critical', 'high', 'medium', 'low'];
const TYPE_ICONS = {
  distress:    '🆘',
  twitter:     '𝕏',
  mastodon:    '🐘',
  whatsapp:    'WA',
  telegram:    'TG',
  partner:     'P',
  news:        '📰',
  iom_incident:'🔴',
  ais_spike:   '📡',
  ngo_activity:'🚢',
  manual:      '✍️',
};

function statusTone(s) {
  if (s === 'active')  return '#22c55e';
  if (s === 'degraded') return '#f59e0b';
  if (s === 'offline') return '#ef4444';
  return '#6b7280';
}

function relativeTime(isoStr) {
  if (!isoStr) return '—';
  const diff = Math.floor((Date.now() - new Date(isoStr)) / 1000);
  if (diff < 60)   return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

// Operational tiers (mirrors IntelEvent.tier() on the backend).
const TIERS = [
  { key: 'operational', label: 'Operational', sub: 'Distress & SAR calls' },
  { key: 'news',        label: 'News & reports', sub: 'Situational updates' },
  { key: 'signal',      label: 'Signals',     sub: 'AIS & movement telemetry' },
];
const PUBLIC_TIERS = [
  { key: 'operational', label: 'Direct', sub: 'Published distress & partner reports' },
  { key: 'news', label: 'Public feeds', sub: 'Official API & first-party publications' },
  { key: 'signal', label: 'Partner ops', sub: 'Trusted operational observations' },
];

function eventTier(p) {
  // Backend supplies `tier`; fall back to type-based inference for cached/legacy events.
  if (p.tier) return p.tier;
  if (p.type === 'distress') return 'operational';
  if (p.type === 'ais_spike' || p.type === 'ngo_activity') return 'signal';
  return 'news';
}

const VERIF_LABEL = {
  unverified_public_source: 'unverified',
  operator_asserted: 'operator',
  derived: 'derived',
  confirmed: 'confirmed',
  user_reported: 'reported',
  partner_reported: 'partner',
};

// ── Source Health Bar ─────────────────────────────────────────────────────────
function SourceHealthBar({ sources, loaded = false }) {
  if (!loaded) {
    return (
      <div className="intel-sources-row intel-sources-row--empty">
        <span style={{ color: '#4a7a6e', fontSize: 11 }}>Source registry loading…</span>
      </div>
    );
  }
  if (!sources || sources.length === 0) {
    return (
      <div className="intel-sources-row intel-sources-row--empty">
        <span style={{ color: '#78998f', fontSize: 11 }}>No approved collector is configured.</span>
      </div>
    );
  }
  return (
    <div className="intel-sources-row">
      {sources.map((src) => (
        <div key={src.name} className="intel-source-chip" title={`Last poll: ${src.last_poll_at ? relativeTime(src.last_poll_at) : 'never'}\nEvents/h: ${src.events_last_hour}\nErrors: ${src.consecutive_errors}${src.last_error ? '\n' + src.last_error : ''}`}>
          <span className="intel-source-dot" style={{ background: statusTone(src.status) }} />
          <span className="intel-source-chip-name">{src.name}</span>
          {src.events_last_hour > 0 && (
            <span className="intel-source-chip-count">{src.events_last_hour}/h</span>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Manual Injection Form ─────────────────────────────────────────────────────
function ManualInjectForm({ apiBase, onClose, onSuccess }) {
  const [form, setForm] = useState({
    title: '',
    text: '',
    source: 'manual',
    severity: 'high',
    type: 'manual',
    lat: '',
    lon: '',
    url: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  function setField(k, v) {
    setForm((cur) => ({ ...cur, [k]: v }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!form.title.trim()) { setError('Title is required'); return; }
    setSubmitting(true);
    setError('');
    try {
      const body = {
        title: form.title.trim(),
        text: form.text.trim(),
        source: form.source.trim() || 'manual',
        severity: form.severity,
        type: form.type,
        url: form.url.trim(),
        lat: form.lat !== '' ? parseFloat(form.lat) : null,
        lon: form.lon !== '' ? parseFloat(form.lon) : null,
      };
      const resp = await fetch(`${apiBase}/api/v1/intel/manual`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!resp.ok) {
        const txt = await resp.text().catch(() => '');
        const msg = txt && !txt.trimStart().startsWith('<')
          ? txt
          : `HTTP ${resp.status} — backend unavailable`;
        throw new Error(msg);
      }
      onSuccess?.();
      onClose?.();
    } catch (err) {
      setError(err.message || 'Submission failed');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="intel-inject-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose?.(); }}>
      <div className="intel-inject-modal">
        <div className="intel-inject-header">
          <strong>Inject intel event</strong>
          <button className="intel-inject-close" onClick={onClose}>✕</button>
        </div>
        <form onSubmit={handleSubmit} className="intel-inject-form">
          <label>
            Title *
            <input value={form.title} onChange={(e) => setField('title', e.target.value)} placeholder="Brief description of the event" />
          </label>
          <label>
            Details
            <textarea value={form.text} onChange={(e) => setField('text', e.target.value)} rows={3} placeholder="Additional context, quotes, source details…" />
          </label>
          <div className="intel-inject-row">
            <label>
              Severity
              <select value={form.severity} onChange={(e) => setField('severity', e.target.value)}>
                {SEV_LABELS.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </label>
            <label>
              Type
              <select value={form.type} onChange={(e) => setField('type', e.target.value)}>
                {['manual', 'distress', 'news', 'iom_incident'].map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </label>
          </div>
          <div className="intel-inject-row">
            <label>
              Lat
              <input type="number" step="any" value={form.lat} onChange={(e) => setField('lat', e.target.value)} placeholder="e.g. 35.8" />
            </label>
            <label>
              Lon
              <input type="number" step="any" value={form.lon} onChange={(e) => setField('lon', e.target.value)} placeholder="e.g. 13.4" />
            </label>
          </div>
          <label>
            Source
            <input value={form.source} onChange={(e) => setField('source', e.target.value)} placeholder="e.g. phone call, email, partner org" />
          </label>
          <label>
            URL
            <input value={form.url} onChange={(e) => setField('url', e.target.value)} placeholder="https://…" />
          </label>
          {error && <p className="intel-inject-error">{error}</p>}
          <div className="intel-inject-actions">
            <button type="submit" disabled={submitting}>{submitting ? 'Saving…' : 'Save event'}</button>
            <button type="button" onClick={onClose}>Cancel</button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Timeline grouping ────────────────────────────────────────────────────────
function groupByHour(events) {
  const groups = [];
  let currentKey = null;
  let currentGroup = null;
  for (const ev of events) {
    const ts = ev.properties?.timestamp_utc;
    if (!ts) continue;
    const d = new Date(ts);
    const key = `${d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' })} ${d.getHours().toString().padStart(2, '0')}:00`;
    if (key !== currentKey) {
      if (currentGroup) groups.push(currentGroup);
      currentKey = key;
      currentGroup = { key, events: [] };
    }
    currentGroup.events.push(ev);
  }
  if (currentGroup) groups.push(currentGroup);
  return groups;
}

// ── Main component ───────────────────────────────────────────────────────────
export default function IntelDashboard({
  apiBase,
  publicMode = false,
  intelEvents,
  intelDrifts,
  intelStats,
  intelFilter,
  setIntelFilter,
  intelMode,
  showAisAlerts,
  setShowAisAlerts,
  triggeringDrift,
  triggerIntelDrift,
  mapRef,
  setSidebarOpen,
}) {
  const [sources, setSources] = useState([]);
  const [sourcesLoaded, setSourcesLoaded] = useState(false);
  const [search, setSearch] = useState('');
  const [channelFilter, setChannelFilter] = useState('all');
  const [sourceFilter, setSourceFilter] = useState('all');
  const [tierFilter, setTierFilter] = useState('all');   // 'all' | operational | news | signal
  const [viewMode, setViewMode] = useState('list');   // 'list' | 'timeline'
  const [showInject, setShowInject] = useState(false);
  const [injectSuccess, setInjectSuccess] = useState(false);
  const pollRef = useRef(null);

  // Poll source registry
  useEffect(() => {
    let alive = true;
    async function loadSources() {
      try {
        const endpoint = publicMode ? '/api/v1/live/sources' : '/api/v1/intel/sources';
        const resp = await fetch(`${apiBase}${endpoint}`);
        if (resp.ok) {
          const data = await resp.json();
          if (alive) setSources(data.sources || []);
        }
      } catch { /* silent */ }
      if (alive) setSourcesLoaded(true);
      if (alive) pollRef.current = window.setTimeout(loadSources, 30000);
    }
    loadSources();
    return () => {
      alive = false;
      window.clearTimeout(pollRef.current);
    };
  }, [apiBase, publicMode]);

  // Filtered + searched events
  const filteredEvents = useMemo(() => {
    let evs = showAisAlerts ? intelEvents : intelEvents.filter((f) => f.properties?.type !== 'ais_spike');

    if (tierFilter !== 'all') evs = evs.filter((f) => eventTier(f.properties || {}) === tierFilter);
    if (intelFilter !== 'all') evs = evs.filter((f) => f.properties?.severity === intelFilter);
    if (channelFilter !== 'all') evs = evs.filter((f) => f.properties?.type === channelFilter);
    if (sourceFilter !== 'all') evs = evs.filter((f) => f.properties?.source === sourceFilter);

    if (search.trim()) {
      const q = search.trim().toLowerCase();
      evs = evs.filter((f) => {
        const p = f.properties || {};
        return (
          (p.title || '').toLowerCase().includes(q) ||
          (p.text  || '').toLowerCase().includes(q) ||
          (p.source || '').toLowerCase().includes(q)
        );
      });
    }
    return [...evs].sort((left, right) => (
      Date.parse(right.properties?.timestamp_utc || 0)
      - Date.parse(left.properties?.timestamp_utc || 0)
    ));
  }, [intelEvents, intelFilter, channelFilter, sourceFilter, tierFilter, showAisAlerts, search]);

  // Group the visible events by operational tier (operational pinned on top).
  const tierGroups = useMemo(() => {
    const g = { operational: [], news: [], signal: [] };
    for (const f of filteredEvents) {
      const t = eventTier(f.properties || {});
      (g[t] || g.news).push(f);
    }
    return g;
  }, [filteredEvents]);

  const visibleTiers = publicMode ? PUBLIC_TIERS : TIERS;

  // Available channel types
  const channelTypes = useMemo(() => {
    const types = new Set(intelEvents.map((f) => f.properties?.type).filter(Boolean));
    return Array.from(types).sort();
  }, [intelEvents]);

  const timelineGroups = useMemo(
    () => viewMode === 'timeline' ? groupByHour(filteredEvents) : [],
    [filteredEvents, viewMode],
  );

  const handleInjectSuccess = useCallback(() => {
    setInjectSuccess(true);
    window.setTimeout(() => setInjectSuccess(false), 3000);
  }, []);

  function flyTo(coords) {
    if (coords && mapRef?.current) {
      mapRef.current.flyTo({ center: coords, zoom: 9, duration: 800 });
    }
  }

  function renderEvent(feat) {
    const p = feat.properties || {};
    const coords = feat.geometry?.coordinates;
    const ts = p.timestamp_utc ? new Date(p.timestamp_utc) : null;
    const driftFeat = intelDrifts.features.find(
      (f) => String(f.properties?.intel_event_id || '').replace(/^intel:/, '')
        === String(p.id || '').replace(/^intel:/, '')
        && f.geometry?.type === 'LineString',
    );
    const currentEstimate = intelDrifts.features.find(
      (f) => String(f.properties?.intel_event_id || '').replace(/^intel:/, '')
        === String(p.id || '').replace(/^intel:/, '')
        && f.properties?.type === 'current_estimate'
        && f.geometry?.type === 'Point',
    );
    const currentCoords = currentEstimate?.geometry?.coordinates;
    const hasDrift = p.drift_status === 'completed' || Boolean(driftFeat);
    const tier = eventTier(p);
    const isDistress = tier === 'operational';
    const icon = TYPE_ICONS[p.type] || '•';
    const verif = p.verification_status || 'unverified_public_source';

    return (
      <li
        key={p.id || p.title}
        className={`intel-event${isDistress ? ' intel-event--distress' : ''}`}
        onClick={() => { flyTo(coords); if (coords) setSidebarOpen?.(false); }}
      >
        <div className="intel-event-header">
          <span className={`intel-sev intel-sev--${p.severity || 'low'}`}>{p.severity || 'low'}</span>
          <span className="intel-type-icon" title={p.type}>{icon}</span>
          <span className={`intel-verif intel-verif--${verif}`} title={`Verification: ${verif.replace(/_/g, ' ')}`}>
            {VERIF_LABEL[verif] || 'unverified'}
          </span>
          {ts && (
            <time title={ts.toISOString()}>
              {ts.toLocaleString('it-IT', {
                timeZone: 'Europe/Rome',
                day: '2-digit',
                month: 'short',
                hour: '2-digit',
                minute: '2-digit',
                hour12: false,
                timeZoneName: 'short',
              })}
            </time>
          )}
          {hasDrift ? (
            <button
              className="intel-drift-btn intel-drift-btn--ready"
              onClick={(e) => {
                e.stopPropagation();
                const target = currentCoords || (driftFeat
                  ? driftFeat.geometry.coordinates[Math.floor(driftFeat.geometry.coordinates.length / 2)]
                  : coords);
                flyTo(target);
                setSidebarOpen?.(false);
              }}
            >Map</button>
          ) : coords && (p.drift_status === 'computing' || triggeringDrift?.has(p.id)) ? (
            <button className="intel-drift-btn intel-drift-btn--computing" disabled>…</button>
          ) : coords && p.drift_status === 'failed' ? (
            <button
              className="intel-drift-btn intel-drift-btn--retry"
              onClick={(e) => { e.stopPropagation(); triggerIntelDrift?.(p.id, coords[1], coords[0]); }}
            >Retry</button>
          ) : publicMode && coords ? (
            <button className="intel-drift-btn intel-drift-btn--computing" disabled>Auto</button>
          ) : coords && p.drift_status !== 'completed' ? (
            <button
              className="intel-drift-btn intel-drift-btn--trigger"
              onClick={(e) => { e.stopPropagation(); triggerIntelDrift?.(p.id, coords[1], coords[0]); }}
            >Drift</button>
          ) : null}
        </div>
        <strong className="intel-title">{p.title}</strong>
        <span className="intel-source">
          <span>{p.source}</span>
          <span style={{ opacity: 0.45 }}>·</span>
          <span>{(p.type || '').replace(/_/g, ' ')}</span>
          {coords && (
            <span style={{ opacity: 0.45 }}>
              · {p.coordinate_source === 'place_centroid' ? 'zona' : 'segnalata'}{' '}
              {coords[1]?.toFixed(3)}, {coords[0]?.toFixed(3)}
            </span>
          )}
          {p.url && (
            <a className="intel-source-link" href={p.url} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()}>↗</a>
          )}
        </span>
        {currentCoords && (
          <span className="intel-source" style={{ color: '#ffe06d' }}>
            Stimata ora · {currentCoords[1]?.toFixed(4)}, {currentCoords[0]?.toFixed(4)}
            {Number.isFinite(Number(currentEstimate.properties?.elapsed_hours))
              ? ` · ${Number(currentEstimate.properties.elapsed_hours).toFixed(1)}h`
              : ''}
          </span>
        )}
        {p.text && (
          <p className="intel-text">{p.text.slice(0, 200)}{p.text.length > 200 ? '…' : ''}</p>
        )}
      </li>
    );
  }

  return (
    <div className="panel-stack">

      {/* Source health */}
      <section className="panel-block" style={{ paddingBottom: 8 }}>
        <div className="osint-feed-header" style={{ marginBottom: 6 }}>
          <span className="section-kicker" style={{ margin: 0 }}>Source health</span>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <span
              className={intelMode === 'ws' ? 'intel-connected' : intelMode === 'poll' ? 'intel-connected-poll' : 'intel-offline'}
              title={intelMode === 'ws' ? 'Live WebSocket' : intelMode === 'poll' ? 'Polling every 30s' : 'Connecting…'}
            >●</span>
            {!publicMode ? (
              <button className="intel-inject-trigger" onClick={() => setShowInject(true)} title="Inject manual event">
                + Manual
              </button>
            ) : null}
          </div>
        </div>
        <SourceHealthBar sources={sources} loaded={sourcesLoaded} />
        {injectSuccess && <p style={{ color: '#22c55e', fontSize: 11, margin: '4px 0 0' }}>Event saved and broadcast.</p>}
      </section>

      {/* Stats row */}
      <section className="panel-block" style={{ paddingTop: 0, paddingBottom: 8 }}>
        <div className="osint-stats-row">
          <div className="osint-stat">
            <strong>{intelStats.total}</strong><span>events</span>
          </div>
          <div className="osint-stat osint-stat--critical">
            <strong>{intelStats.by_sev?.critical || 0}</strong><span>critical</span>
          </div>
          <div className="osint-stat osint-stat--high">
            <strong>{intelStats.by_sev?.high || 0}</strong><span>high</span>
          </div>
          <div className="osint-stat">
            <strong>{filteredEvents.length}</strong><span>shown</span>
          </div>
        </div>
      </section>

      {/* Controls */}
      <section className="panel-block" style={{ paddingTop: 0, paddingBottom: 0 }}>
        {/* Search */}
        <div className="intel-search-row">
          <input
            className="intel-search-input"
            type="search"
            placeholder="Search title, text, source…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        {/* Tier filter — primary operational control */}
        <div className="intel-tier-row">
          <button
            className={`intel-tier-btn ${tierFilter === 'all' ? 'is-active' : ''}`}
            onClick={() => setTierFilter('all')}
          >All</button>
          {visibleTiers.map((t) => (
            <button
              key={t.key}
              className={`intel-tier-btn intel-tier-btn--${t.key} ${tierFilter === t.key ? 'is-active' : ''}`}
              onClick={() => setTierFilter((cur) => cur === t.key ? 'all' : t.key)}
              title={t.sub}
            >
              {t.key === 'operational' && <span className="intel-tier-dot" />}
              {t.label}
              <span className="intel-tier-count">{tierGroups[t.key].length}</span>
            </button>
          ))}
        </div>

        {/* Severity filter */}
        <div className="intel-filter-row" style={{ marginTop: 6 }}>
          {['all', 'critical', 'high', 'medium', 'low'].map((f) => (
            <button
              key={f}
              className={`intel-filter-btn ${intelFilter === f ? 'is-active' : ''}`}
              onClick={() => setIntelFilter(f)}
            >{f}</button>
          ))}
          {!publicMode ? (
            <button
              className={`intel-filter-btn ${showAisAlerts ? 'is-active' : ''}`}
              onClick={() => setShowAisAlerts((v) => !v)}
              title="Toggle AIS loitering alerts"
            >AIS</button>
          ) : null}
          <button
            className={`intel-filter-btn ${sourceFilter === ALARM_PHONE_SOURCE ? 'is-active' : ''}`}
            onClick={() => setSourceFilter((cur) => cur === ALARM_PHONE_SOURCE ? 'all' : ALARM_PHONE_SOURCE)}
            title="Show only Alarm Phone reports"
          >📞 Alarm Phone</button>
        </div>

        {/* Channel filter */}
        {channelTypes.length > 0 && (
          <div className="intel-filter-row" style={{ marginTop: 4 }}>
            <button
              className={`intel-filter-btn intel-filter-btn--channel ${channelFilter === 'all' ? 'is-active' : ''}`}
              onClick={() => setChannelFilter('all')}
            >all channels</button>
            {channelTypes.map((t) => (
              <button
                key={t}
                className={`intel-filter-btn intel-filter-btn--channel ${channelFilter === t ? 'is-active' : ''}`}
                onClick={() => setChannelFilter((cur) => cur === t ? 'all' : t)}
              >{TYPE_ICONS[t] || ''} {t.replace(/_/g, ' ')}</button>
            ))}
          </div>
        )}

        {/* View toggle */}
        <div style={{ display: 'flex', gap: 6, marginTop: 6, marginBottom: 2 }}>
          <button
            className={`intel-filter-btn ${viewMode === 'list' ? 'is-active' : ''}`}
            onClick={() => setViewMode('list')}
          >List</button>
          <button
            className={`intel-filter-btn ${viewMode === 'timeline' ? 'is-active' : ''}`}
            onClick={() => setViewMode('timeline')}
          >Timeline</button>
        </div>
      </section>

      {/* Event list / timeline */}
      <section className="panel-block" style={{ padding: 0 }}>
        {viewMode === 'list' ? (
          filteredEvents.length === 0 ? (
            <ul className="intel-list">
              <li className="intel-empty">
                {publicMode && intelMode !== 'offline' && tierFilter === 'all' && intelFilter === 'all' && channelFilter === 'all' && !search ? (
                  <div className="intel-live-empty">
                    <i />
                    <strong>No live signal received</strong>
                    <span>Listening to official APIs and explicitly published partner channels.</span>
                  </div>
                ) : intelMode !== 'offline'
                  ? `No events${tierFilter !== 'all' || intelFilter !== 'all' || channelFilter !== 'all' || search ? ' matching filters' : ''}`
                  : 'Connecting to live feed…'}
              </li>
            </ul>
          ) : (
            // Grouped by tier — operational (distress) always pinned on top.
            visibleTiers.map((t) => {
              const group = tierGroups[t.key];
              if (!group.length) return null;
              return (
                <div key={t.key} className={`intel-tier-group intel-tier-group--${t.key}`}>
                  <div className="intel-tier-head">
                    {t.key === 'operational' && <span className="intel-tier-dot" />}
                    <span className="intel-tier-head-label">{t.label}</span>
                    <span className="intel-tier-head-sub">{t.sub}</span>
                    <span className="intel-tier-head-count">{group.length}</span>
                  </div>
                  <ul className="intel-list" style={{ margin: 0 }}>
                    {group.map(renderEvent)}
                  </ul>
                </div>
              );
            })
          )
        ) : (
          <div className="intel-timeline">
            {timelineGroups.length === 0 ? (
              <div className="intel-empty">No events matching filters</div>
            ) : timelineGroups.map((group) => (
              <div key={group.key} className="intel-timeline-group">
                <div className="intel-timeline-hour">{group.key}</div>
                <ul className="intel-list" style={{ margin: 0 }}>
                  {group.events.map(renderEvent)}
                </ul>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Channel breakdown */}
      {Object.keys(intelStats.by_type || {}).length > 0 && (
        <section className="panel-block">
          <p className="section-kicker">By channel</p>
          <ul className="signal-list" style={{ marginTop: 4 }}>
            {Object.entries(intelStats.by_type).sort((a, b) => b[1] - a[1]).map(([type, count]) => (
              <li
                key={type}
                style={{ cursor: 'pointer' }}
                onClick={() => setChannelFilter((cur) => cur === type ? 'all' : type)}
                className={channelFilter === type ? 'is-active' : ''}
              >
                <strong>{TYPE_ICONS[type] || ''} {type.replace(/_/g, ' ')}</strong>
                <span>{count}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Manual injection modal */}
      {!publicMode && showInject && (
        <ManualInjectForm
          apiBase={apiBase}
          onClose={() => setShowInject(false)}
          onSuccess={handleInjectSuccess}
        />
      )}
    </div>
  );
}
