import React, { useMemo, useState } from 'react';

const TYPE_LABEL = {
  ais_rendezvous: 'STS rendezvous',
  vessel_identity: 'Identity / sanctions',
  ais_anomaly: 'AIS anomaly',
  dark_candidate: 'Dark candidate (VIIRS)',
  conflict_event: 'Conflict event',
  navwarning: 'Nav warning',
  correlated_alert: 'Correlated alert',
};
const TYPE_COLOR = {
  ais_rendezvous: '#f472b6', vessel_identity: '#ef4444', ais_anomaly: '#60a5fa',
  dark_candidate: '#4ade80', conflict_event: '#f97316', navwarning: '#eab308',
  correlated_alert: '#ffb347',
};

function rel(iso) {
  if (!iso) return '';
  const s = Math.floor((Date.now() - new Date(iso)) / 1000);
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
}

/**
 * Operator MDA / dark-vessel console. Lists the anomalies the MDA engine has
 * raised (STS rendezvous, spoofing, identity fraud, dark candidates, conflict
 * events, correlated alerts) and a per-MMSI lookup that pulls the identity
 * screen + track from /api/v1/mda/vessel/{mmsi}.
 */
export default function MdaPanel({ apiBase, fetchJson, anomalies = [], onFocus, onOpenCase }) {
  const [filter, setFilter] = useState('all');
  const [mmsi, setMmsi] = useState('');
  const [vessel, setVessel] = useState(null);
  const [status, setStatus] = useState(null);

  const types = useMemo(() => {
    const c = {};
    for (const a of anomalies) c[a.type] = (c[a.type] || 0) + 1;
    return c;
  }, [anomalies]);

  const shown = useMemo(() => {
    const list = filter === 'all' ? anomalies : anomalies.filter((a) => a.type === filter);
    return [...list].sort((a, b) => new Date(b.timestamp_utc) - new Date(a.timestamp_utc));
  }, [anomalies, filter]);

  const lookup = async () => {
    const m = mmsi.trim();
    if (!/^\d{7,9}$/.test(m)) return;
    try {
      setVessel(await fetchJson(apiBase, `/api/v1/mda/vessel/${m}?hours=168`));
    } catch { setVessel({ error: true }); }
  };

  React.useEffect(() => {
    fetchJson(apiBase, '/api/v1/mda/status').then(setStatus).catch(() => {});
  }, [apiBase, fetchJson]);

  return (
    <div className="panel-stack mda-panel">
      <section className="panel-block">
        <p className="section-kicker">Maritime domain awareness</p>
        <h3>Dark-vessel console</h3>
        {status && (
          <div className="info-grid">
            <div className="info-box"><strong>{status.track_store?.mmsi ?? '—'}</strong><span>MMSIs tracked</span></div>
            <div className="info-box"><strong>{status.track_store?.rows ?? '—'}</strong><span>track points</span></div>
            <div className="info-box"><strong>{status.sanctioned_vessels ?? '—'}</strong><span>sanctioned vessels</span></div>
            <div className="info-box"><strong>{status.jamming_as_of ? '✓' : '—'}</strong><span>jamming layer</span></div>
          </div>
        )}
      </section>

      <section className="panel-block">
        <div className="mda-vessel-lookup">
          <input value={mmsi} onChange={(e) => setMmsi(e.target.value)} placeholder="MMSI lookup…"
                 onKeyDown={(e) => e.key === 'Enter' && lookup()} />
          <button type="button" onClick={lookup}>Screen</button>
        </div>
        {vessel && !vessel.error && (
          <div className="mda-vessel-card">
            <strong>{vessel.static?.name || vessel.mmsi}</strong>
            <span>IMO {vessel.static?.imo || '—'} · flag {vessel.static?.flag || vessel.identity?.mid_flag || '—'}
              {' · '}{vessel.track_points?.length ?? 0} recent fixes</span>
            {vessel.identity?.risk_flags?.length > 0 && (
              <div className="mda-risk">{vessel.identity.risk_flags.map((f) => (
                <span key={f} className="mda-risk-flag">{f.replace(/_/g, ' ')}</span>
              ))}</div>
            )}
            {vessel.identity?.sanctions?.length > 0 && (
              <div className="mda-sanctions">⚠ {vessel.identity.sanctions[0].list}: {vessel.identity.sanctions[0].program}</div>
            )}
            {vessel.track_points?.length >= 2 && (
              <button type="button" className="mda-mini-btn"
                onClick={() => onFocus?.(vessel.track_points.at(-1).lat, vessel.track_points.at(-1).lon)}>
                Last position on map
              </button>
            )}
          </div>
        )}
        {vessel?.error && <p className="mda-hint">No data for that MMSI.</p>}
      </section>

      <section className="panel-block">
        <div className="mda-filter-row">
          <button className={filter === 'all' ? 'is-active' : ''} onClick={() => setFilter('all')}>
            all {anomalies.length}
          </button>
          {Object.entries(types).map(([t, n]) => (
            <button key={t} className={filter === t ? 'is-active' : ''} onClick={() => setFilter(t)}
              style={{ borderColor: TYPE_COLOR[t] }}>
              {TYPE_LABEL[t] || t} {n}
            </button>
          ))}
        </div>
        {shown.length === 0 && <p className="mda-hint">No dark-vessel signals in the last 72 h.</p>}
        <ul className="mda-list">
          {shown.map((a) => (
            <li key={a.id} className="mda-item">
              <div className="mda-item-head">
                <span className="mda-dot" style={{ background: TYPE_COLOR[a.type] || '#60a5fa' }} />
                <span className="mda-item-type">{TYPE_LABEL[a.type] || a.type}</span>
                {a.severity && <span className={`mda-sev mda-sev--${a.severity}`}>{a.severity}</span>}
                <span className="mda-age">{rel(a.timestamp_utc)}</span>
              </div>
              <div className="mda-item-title">{a.title}</div>
              {a.metadata?.contributing_sources && (
                <div className="mda-sources">{a.metadata.contributing_sources.join(' · ')}</div>
              )}
              {a.metadata?.darkship_cue && (
                <div className="mda-cue">🛰 search area {a.metadata.darkship_cue.radius_km} km ·
                  next S1 pass ~{Math.round(a.metadata.darkship_cue.next_s1_pass_estimate_hours)} h</div>
              )}
              <div className="mda-item-actions">
                {Number.isFinite(a.lat) && (
                  <button type="button" onClick={() => onFocus?.(a.lat, a.lon)}>On map</button>
                )}
                {a.mmsi && (
                  <button type="button" onClick={() => { setMmsi(a.mmsi); }}>Screen {a.mmsi}</button>
                )}
                {a.metadata?.case_id && (
                  <button type="button" onClick={() => onOpenCase?.(a.metadata.case_id)}>Case</button>
                )}
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
