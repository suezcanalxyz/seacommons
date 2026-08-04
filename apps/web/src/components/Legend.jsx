import React, { useState } from 'react';

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

const ROWS = [
  { shape: 'circle', color: '#ff3b3b', label: 'Active distress' },
  { shape: 'circle', color: '#22c55e', label: 'Resolved' },
  { shape: 'circle', color: '#9aa0ab', label: 'Archived' },
  { shape: 'circle', color: '#38bdf8', label: 'NGO SAR vessel' },
  { shape: 'square', color: '#ffb454', label: 'Oil / gas platform' },
  { shape: 'ring',   color: '#8bf0c5', label: 'Drift projection' },
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
          <div className="legend-panel-title">Legend</div>
          {ROWS.map((row) => (
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
