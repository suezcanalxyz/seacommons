import React, { useState } from 'react';

import { INTEL_MAP_CATEGORIES } from '../features/intel/categories.js';

/**
 * Map layer visibility control.
 * Each group maps to the MapLibre layer ids registered in main.jsx — toggling
 * sets `visibility` layout on every layer in the group (sources stay loaded,
 * so re-enabling is instant).
 */
const INTEL_CATEGORY_GROUPS = INTEL_MAP_CATEGORIES.map((c) => ({
  key: `intel_${c.key}`,
  label: c.label,
  indent: true,
  layers: [`intel-cat-${c.key}`, `intel-cat-${c.key}-halo`],
}));

export const LAYER_GROUPS = [
  { key: 'nautical',    label: 'Nautical charts', layers: ['seamarks-layer'] },
  { key: 'vessels',     label: 'AIS vessels',    layers: ['vessels-layer', 'vessels-stationary'] },
  { key: 'ngo_vessels', label: 'NGO SAR fleet',  layers: ['vessels-ngo', 'vessels-ngo-stationary'] },
  { key: 'weather',     label: 'Weather grid',   layers: ['weather-vectors', 'weather-points'] },
  { key: 'sar',         label: 'Distress & drift', layers: ['intel-events-layer', 'intel-events-halo', 'intel-distress-core', 'intel-distress-pulse', 'intel-distress-area', 'intel-distress-polygon-fill', 'intel-distress-polygon-outline', 'intel-drift-cone', 'intel-drift-line', 'intel-drift-point', 'live-nearby-vessels-layer', 'live-nearby-vessels-halo', 'ngo-response-lines-layer', 'ngo-response-points-layer'] },
  { key: 'fused',       label: 'Correlated alerts', layers: ['intel-fused-core', 'intel-fused-pulse'] },
  ...INTEL_CATEGORY_GROUPS,
  { key: 'spikes',      label: 'AIS anomalies',  layers: ['intel-spike-layer'], defaultOff: true },
  { key: 'mda_anomaly', label: 'MDA · dark-vessel signals', layers: ['mda-anomaly-layer'], defaultOff: true },
  { key: 'mda_infra',   label: 'MDA · cables / pipelines / STS zones', layers: ['mda-infra-lines', 'mda-infra-points', 'mda-sts-zones'], defaultOff: true },
  { key: 'mda_jamming', label: 'MDA · GNSS jamming', layers: ['mda-jamming-fill'], defaultOff: true },
  { key: 'platforms',   label: 'Platforms',      layers: ['platforms-layer', 'platforms-halo'] },
  { key: 'alerts',      label: 'Past SAR cones', layers: ['alerts-cone', 'alerts-layer'] },
];

const LAYERS_ICON = (
  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="m12 3 9 5-9 5-9-5 9-5z" />
    <path d="m3 13 9 5 9-5" />
  </svg>
);

export default function LayerToggles({ visibility, onToggle, allowed = null, labelOverrides = null }) {
  const [open, setOpen] = useState(false);
  const groups = allowed ? LAYER_GROUPS.filter((g) => allowed.has(g.key)) : LAYER_GROUPS;
  const isOn = (g) => (g.defaultOff ? visibility[g.key] === true : visibility[g.key] !== false);
  const offCount = groups.filter((g) => !isOn(g)).length;

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
          {groups.map((g) => (
            <React.Fragment key={g.key}>
              {g.key === 'intel_social' && <div className="layer-panel-sub">OSINT signal types</div>}
              <label className={`layer-row${g.indent ? ' is-indent' : ''}`}>
                <input
                  type="checkbox"
                  checked={isOn(g)}
                  onChange={() => onToggle(g.key)}
                />
                <span>{labelOverrides?.[g.key] || g.label}</span>
              </label>
            </React.Fragment>
          ))}
        </div>
      )}
    </div>
  );
}
