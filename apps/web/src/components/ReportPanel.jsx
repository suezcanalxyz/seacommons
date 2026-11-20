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

export function CaseReportOverview({ title, summary, category, color, event, status, evidence = {}, children }) {
  return (
    <>
      <div className="intel-report-title">
        <span style={{ background: color }} />
        <strong>{title}</strong>
      </div>
      {summary && (
        <p className="intel-report-summary">{summary}</p>
      )}
      <ReportRow label="Category" value={category} color={color} />
      <ReportRow label="Event" value={event} />
      <ReportRow label="Status" value={status} color={color} />
      {evidence.verification_status && <ReportRow label="Verification" value={String(evidence.verification_status).replace(/_/g, ' ')} />}
      {typeof evidence.corroborated === 'boolean' && <ReportRow label="Independent corroboration" value={evidence.corroborated ? 'YES' : 'NO'} />}
      {Array.isArray(evidence.independence_groups) && evidence.independence_groups.length > 0 && <ReportRow label="Evidence lineages" value={evidence.independence_groups.join(' · ')} />}
      {children}
    </>
  );
}
