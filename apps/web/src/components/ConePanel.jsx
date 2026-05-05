import React from 'react';

const HORIZON_LABELS = {
  cone_6h:  '6-hour drift cone',
  cone_12h: '12-hour drift cone',
  cone_18h: '18-hour drift cone',
  cone_24h: '24-hour drift cone',
};

const SKIPPED_PROPS = new Set(['type']);

function fmtVal(v) {
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toFixed(4);
  if (typeof v === 'boolean') return v ? 'yes' : 'no';
  if (v == null) return '—';
  return String(v);
}

function fmtKey(k) {
  return k.replace(/_/g, ' ');
}

export default function ConePanel({ cone, eventId, caseStatus, onClose }) {
  if (!cone) return null;
  const props = cone.properties || {};
  const horizonKey = props.type || '';
  const label = HORIZON_LABELS[horizonKey] || (horizonKey ? horizonKey.replace('cone_', '') + ' drift zone' : 'Drift zone');

  const extraProps = Object.entries(props).filter(([k]) => !SKIPPED_PROPS.has(k));

  return (
    <div className="cone-panel">
      <div className="cone-panel-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <span className="section-kicker">SAR drift projection</span>
          <strong style={{ fontSize: 13, display: 'block', marginTop: 2 }}>{label}</strong>
        </div>
        <button className="cone-close-btn" onClick={onClose} title="Close">×</button>
      </div>

      <div className="cone-section">
        {eventId && (
          <div className="cone-row">
            <span>Event</span>
            <strong>{eventId.slice(0, 12)}…</strong>
          </div>
        )}
        <div className="cone-row">
          <span>Status</span>
          <strong>{caseStatus || '—'}</strong>
        </div>
        {horizonKey && (
          <div className="cone-row">
            <span>Horizon</span>
            <strong>{horizonKey.replace('cone_', '').toUpperCase()}</strong>
          </div>
        )}
      </div>

      {extraProps.length > 0 && (
        <div className="cone-section">
          {extraProps.map(([k, v]) => (
            <div className="cone-row" key={k}>
              <span>{fmtKey(k)}</span>
              <strong>{fmtVal(v)}</strong>
            </div>
          ))}
        </div>
      )}

      <div className="cone-section" style={{ borderBottom: 'none' }}>
        <p style={{ margin: 0, fontSize: 10, color: '#7aada5', lineHeight: 1.5 }}>
          Projection based on Open-Meteo wind + ocean current data.
          Click a different cone to compare horizons.
        </p>
      </div>
    </div>
  );
}
