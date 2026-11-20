import React from 'react';

/** Same keyboard-accessible navigation grammar in LIVE and PLAY. */
export default function IntelligencePanelTabs({ options, value, onChange, label = 'Intelligence tools' }) {
  return <nav className="sc-intelligence-tabs" aria-label={label}>
    {options.map(({ id, label: title, count }) => (
      <button key={id} type="button" className={value === id ? 'is-active' : ''}
        aria-current={value === id ? 'page' : undefined}
        aria-pressed={value === id} onClick={() => onChange(id)}>
        <span>{title}</span>{Number.isFinite(count) ? <small>{count}</small> : null}
      </button>
    ))}
  </nav>;
}
