import React, { useState } from 'react';

/**
 * Map layer visibility control.
 * Each group maps to the MapLibre layer ids registered in main.jsx — toggling
 * sets `visibility` layout on every layer in the group (sources stay loaded,
 * so re-enabling is instant).
 */
export const LAYER_GROUPS = [
  { key: 'vessels',   label: 'AIS vessels',    layers: ['vessels-layer', 'vessels-stationary', 'vessels-ngo', 'vessels-ngo-stationary'] },
  { key: 'weather',   label: 'Weather grid',   layers: ['weather-vectors', 'weather-points'] },
  { key: 'intel',     label: 'OSINT events',   layers: ['intel-events-layer', 'intel-events-halo', 'intel-distress-core', 'intel-distress-pulse', 'intel-drift-cone', 'intel-drift-line', 'intel-drift-point'] },
  { key: 'platforms', label: 'Platforms',      layers: ['platforms-layer', 'platforms-halo'] },
  { key: 'alerts',    label: 'Past SAR cones', layers: ['alerts-cone', 'alerts-layer'] },
];

const LAYERS_ICON = (
  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="m12 3 9 5-9 5-9-5 9-5z" />
    <path d="m3 13 9 5 9-5" />
  </svg>
);

export default function LayerToggles({ visibility, onToggle }) {
  const [open, setOpen] = useState(false);
  const offCount = LAYER_GROUPS.filter((g) => !visibility[g.key]).length;

  return (
    <div className="layer-control">
      <button
        type="button"
        className={`layer-fab${open ? ' is-open' : ''}`}
        onClick={() => setOpen((v) => !v)}
        title="Map layers"
        aria-expanded={open}
      >
        {LAYERS_ICON}
        {offCount > 0 && <span className="layer-fab-dot" title={`${offCount} hidden`} />}
      </button>
      {open && (
        <div className="layer-panel">
          <div className="layer-panel-title">Layers</div>
          {LAYER_GROUPS.map((g) => (
            <label key={g.key} className="layer-row">
              <input
                type="checkbox"
                checked={visibility[g.key] !== false}
                onChange={() => onToggle(g.key)}
              />
              <span>{g.label}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  );
}
