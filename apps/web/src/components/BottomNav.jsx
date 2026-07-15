import React from 'react';

/* Inline SVG icons — no icon library needed, consistent rendering everywhere. */
const ICONS = {
  map: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2z" />
      <path d="M9 4v14M15 6v14" />
    </svg>
  ),
  sim: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="3.5" />
      <path d="M12 3v3.5M12 17.5V21M3 12h3.5M17.5 12H21" />
    </svg>
  ),
  live: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 14a8 8 0 0 1 16 0" />
      <path d="M7.5 14a4.5 4.5 0 0 1 9 0" />
      <circle cx="12" cy="14" r="1.4" fill="currentColor" stroke="none" />
      <path d="M12 15.4V19" />
    </svg>
  ),
  osint: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="6.5" />
      <path d="m20 20-4.4-4.4" />
    </svg>
  ),
  settings: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 7h10M18 7h2M4 17h2M10 17h10" />
      <circle cx="16" cy="7" r="2.2" />
      <circle cx="8" cy="17" r="2.2" />
    </svg>
  ),
  cases: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 7h16v13H4zM8 7V4h8v3"/><path d="M4 12h16"/></svg>
  ),
};

const TABS = [
  { id: 'map',      label: 'Map',    icon: 'map' },
  { id: 'cases',    label: 'Cases',  icon: 'cases' },
  { id: 'sim',      label: 'SAR',    icon: 'sim' },
  { id: 'live',     label: 'Live',   icon: 'live' },
  { id: 'osint',    label: 'OSINT',  icon: 'osint' },
  { id: 'settings', label: 'Config', icon: 'settings' },
];

/**
 * Mobile-only bottom tab bar.
 * - "Map" dismisses the panel sheet and shows the full-screen map.
 * - Other tabs open the corresponding panel as a bottom sheet.
 * - Tapping the already-active tab toggles its sheet closed (back to map).
 */
export default function BottomNav({ activePanel, sheetOpen, badgeCounts = {}, onSelect }) {
  return (
    <nav className="bottom-nav" aria-label="Main sections">
      {TABS.map((tab) => {
        const isMap = tab.id === 'map';
        const isActive = isMap ? !sheetOpen : sheetOpen && activePanel === tab.id;
        const badge = badgeCounts[tab.id];
        return (
          <button
            key={tab.id}
            type="button"
            className={`bottom-nav-tab${isActive ? ' is-active' : ''}`}
            aria-pressed={isActive}
            onClick={() => onSelect(tab.id)}
          >
            <span className="bottom-nav-icon">
              {ICONS[tab.icon]}
              {badge > 0 && <span className="bottom-nav-badge">{badge > 99 ? '99+' : badge}</span>}
            </span>
            <span className="bottom-nav-label">{tab.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
