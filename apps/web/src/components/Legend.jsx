import React, { useState } from 'react';

import { SIGNAL_CATEGORIES } from '../features/intel/categories.js';
import { DOMAIN_COLORS } from './IntelDashboard.jsx';

const INFO_ICON = (
  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="9" />
    <path d="M12 11v5" />
    <path d="M12 8h.01" />
  </svg>
);

function Swatch({ shape, color, border }) {
  const style = {
    width: 12, height: 12, flex: '0 0 auto',
    background: shape === 'ring' ? 'transparent' : color,
    border: `1.5px solid ${border || color}`,
    borderRadius: shape === 'square' ? 2 : '50%',
  };
  return <span style={style} />;
}

// Base map furniture (not signal categories).
const BASE_ROWS = [
  { shape: 'circle', color: '#22c55e', label: 'Resolved incident' },
  { shape: 'circle', color: '#9aa0ab', label: 'Archived incident' },
  { shape: 'circle', color: '#38bdf8', label: 'NGO SAR vessel' },
  { shape: 'square', color: '#ffb454', label: 'Oil / gas platform' },
  { shape: 'ring',   color: '#8bf0c5', label: 'Drift projection' },
];

const DOMAIN_ROWS = [
  ['sar', 'Alert · search & rescue', 'A distress report corroborated by more than one source.'],
  ['sanctions', 'Alert · sanctions / dark fleet', 'Spoofing, dark ship-to-ship transfer, or identity fraud tied to sanctions exposure.'],
  ['grey_zone', 'Alert · grey-zone / infrastructure', 'Proximity to subsea cables/pipelines/platforms, or a warfare/grey-zone context match.'],
  ['safety', 'Alert · vessel safety', 'A vessel casualty (collision, fire, damage) or a natural-hazard overlap with a vessel.'],
];

export default function Legend() {
  const [open, setOpen] = useState(false);
  return (
    <div className="legend-control">
      <button
        type="button"
        className={`legend-fab${open ? ' is-open' : ''}`}
        onClick={() => setOpen((v) => !v)}
        title="Map legend"
        aria-expanded={open}
      >
        {INFO_ICON}
      </button>
      {open && (
        <div className="legend-panel">
          <div className="legend-panel-title">OSINT signals</div>
          {SIGNAL_CATEGORIES.filter((c) => c.key !== 'other').map((cat) => (
            <div key={cat.key} className="legend-row legend-row--defined" title={cat.description}>
              <Swatch shape={cat.key === 'fused' ? 'ring' : 'circle'} color={cat.color} />
              <span>
                <strong>{cat.label}</strong>
                <small>{cat.description}</small>
              </span>
            </div>
          ))}
          <div className="legend-panel-title">Correlated alert domain</div>
          {DOMAIN_ROWS.map(([key, label, description]) => (
            <div key={key} className="legend-row legend-row--defined" title={description}>
              <Swatch shape="ring" color={DOMAIN_COLORS[key]} />
              <span>
                <strong>{label}</strong>
                <small>{description}</small>
              </span>
            </div>
          ))}
          <div className="legend-panel-title">Map</div>
          {BASE_ROWS.map((row) => (
            <div key={row.label} className="legend-row">
              <Swatch shape={row.shape} color={row.color} />
              <span>{row.label}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
