import React from 'react';

const HORIZON = {
  cone_6h:  '6h drift zone',
  cone_12h: '12h drift zone',
  cone_18h: '18h drift zone',
  cone_24h: '24h drift zone',
};

function fmtVal(v) {
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toFixed(4);
  if (v == null) return '—';
  return String(v);
}

function LocationView({ panel, onComputeDrift }) {
  return (
    <>
      <div className="cone-section">
        <div className="cone-row">
          <span>Lat</span>
          <strong>{panel.lat}</strong>
        </div>
        <div className="cone-row">
          <span>Lon</span>
          <strong>{panel.lon}</strong>
        </div>
      </div>

      {panel.vessels && panel.vessels.length > 0 && (
        <div className="cone-section">
          <div style={{ fontSize: 9, color: '#87cabc', textTransform: 'uppercase', letterSpacing: '0.13em', marginBottom: 5 }}>
            Nearest vessels
          </div>
          {panel.vessels.slice(0, 3).map((v, i) => (
            <div className="cone-row" key={v.mmsi || i}>
              <span>{v.ship_name || v.mmsi || '—'}</span>
              <strong>{v.distance_nm ? v.distance_nm.toFixed(1) + ' nm' : '—'}</strong>
            </div>
          ))}
        </div>
      )}

      {panel.weather && (
        <div className="cone-section">
          <div style={{ fontSize: 9, color: '#87cabc', textTransform: 'uppercase', letterSpacing: '0.13em', marginBottom: 5 }}>
            Conditions
          </div>
          <div className="cone-row">
            <span>Wind</span>
            <strong>{panel.weather.wind?.speed_ms} m/s {panel.weather.wind?.direction_label}</strong>
          </div>
          <div className="cone-row">
            <span>Waves</span>
            <strong>{panel.weather.waves?.significant_height_m} m</strong>
          </div>
        </div>
      )}

      <div className="cone-section" style={{ borderBottom: 'none' }}>
        <button
          onClick={onComputeDrift}
          style={{
            width: '100%', border: 0, borderRadius: 3, padding: '7px 0',
            background: 'linear-gradient(135deg,#83f4df,#70a2ff)',
            color: '#061015', fontWeight: 700, fontSize: 11, cursor: 'pointer',
          }}
        >
          Compute drift here
        </button>
      </div>
    </>
  );
}

function ConeView({ panel }) {
  const props = panel.feature?.properties || {};
  const label = HORIZON[props.type] || props.type || 'Drift zone';
  const extra = Object.entries(props).filter(([k]) => k !== 'type');

  return (
    <>
      <div className="cone-section">
        <div className="cone-row">
          <span>Horizon</span>
          <strong>{label}</strong>
        </div>
        {panel.eventId && (
          <div className="cone-row">
            <span>Event</span>
            <strong>{panel.eventId.slice(0, 12)}…</strong>
          </div>
        )}
        {panel.caseStatus && (
          <div className="cone-row">
            <span>Status</span>
            <strong>{panel.caseStatus}</strong>
          </div>
        )}
      </div>

      {extra.length > 0 && (
        <div className="cone-section" style={{ borderBottom: 'none' }}>
          {extra.map(([k, v]) => (
            <div className="cone-row" key={k}>
              <span>{k.replace(/_/g, ' ')}</span>
              <strong>{fmtVal(v)}</strong>
            </div>
          ))}
        </div>
      )}
    </>
  );
}

export default function MapFloatingPanel({ panel, onClose, onComputeDrift }) {
  if (!panel) return null;

  const title = panel.type === 'cone' ? 'Drift projection' : 'Selected point';
  const kicker = panel.type === 'cone' ? 'SAR drift cone' : 'Map click';

  return (
    <div className="cone-panel">
      <div className="cone-panel-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <span className="section-kicker">{kicker}</span>
          <strong style={{ fontSize: 13, display: 'block', marginTop: 2 }}>{title}</strong>
        </div>
        <button className="cone-close-btn" onClick={onClose}>×</button>
      </div>

      {panel.type === 'location' && (
        <LocationView panel={panel} onComputeDrift={onComputeDrift} />
      )}
      {panel.type === 'cone' && (
        <ConeView panel={panel} />
      )}
    </div>
  );
}
