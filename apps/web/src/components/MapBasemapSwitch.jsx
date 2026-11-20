import React from 'react';

/** Single, keyboard-friendly basemap control used by LIVE and PLAY. */
export default function MapBasemapSwitch({ mode, onChange, panelOpen = false }) {
  const satellite = mode === 'satellite';
  return (
    <div className={`sc-basemap-switch${panelOpen ? ' has-open-panel' : ''}`} role="group" aria-label="Map background">
      <button type="button" className={satellite ? '' : 'is-active'} aria-pressed={!satellite}
        onClick={() => onChange('standard')} title="Dark bathymetric chart">
        <span className="sc-basemap-switch__preview sc-basemap-switch__preview--ocean" aria-hidden="true" />
        <span>Map</span>
      </button>
      <button type="button" className={satellite ? 'is-active' : ''} aria-pressed={satellite}
        onClick={() => onChange('satellite')} title="Satellite imagery mosaic">
        <span className="sc-basemap-switch__preview sc-basemap-switch__preview--satellite" aria-hidden="true" />
        <span>Satellite</span>
      </button>
    </div>
  );
}
