import React from 'react';

export function ReportRow({ label, value, color, mono }) {
  return (
    <div className="cone-row">
      <span>{label}</span>
      <strong style={color ? { color } : mono ? { fontFamily: 'monospace', fontSize: 10 } : {}}>
        {value ?? '—'}
      </strong>
    </div>
  );
}

export function ReportPanelHeader({ kicker, title, onClose, children }) {
  return (
    <div className="cone-panel-header report-panel-header">
      <div>
        <span className="section-kicker">{kicker}</span>
        <strong>{title}</strong>
      </div>
      {children}
      <button className="cone-close-btn" type="button" aria-label="Close report" onClick={onClose}>×</button>
    </div>
  );
}
