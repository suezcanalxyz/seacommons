import React, { useMemo, useState } from 'react';

import { DOMAIN_COLORS } from './IntelDashboard.jsx';

const SEV_ORDER = { critical: 0, high: 1, medium: 2, low: 3 };

function relative(iso) {
  if (!iso) return '';
  const s = Math.floor((Date.now() - new Date(iso)) / 1000);
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
}

/**
 * Correlated-alert rail — the operator-facing view of the OSINT fusion engine.
 * Lists every `correlated_alert` intel event (most severe / newest first) with
 * its maritime domain, confidence, and contributing sources. "On map" recentres
 * the map; "Open case" jumps to the auto-opened case.
 *
 * Reads straight from the same `intelEvents` feature array the map uses — no
 * extra fetch. Not rendered on the public Live host.
 */
export default function AlertRail({ intelEvents = [], onFocus, onOpenCase }) {
  const [collapsed, setCollapsed] = useState(false);

  const alerts = useMemo(() => {
    return intelEvents
      .filter((f) => f.properties?.type === 'correlated_alert')
      .map((f) => {
        const p = f.properties || {};
        const [lon, lat] = f.geometry?.coordinates || [];
        return {
          id: p.id,
          lat, lon,
          alertType: p.alert_type || 'correlated_alert',
          domain: p.maritime_domain || 'sar',
          severity: p.severity || 'high',
          confidence: typeof p.confidence === 'number' ? p.confidence : null,
          sources: Array.isArray(p.contributing_sources) ? p.contributing_sources : [],
          caseId: p.case_id || null,
          title: p.title || '',
          ts: p.timestamp_utc,
        };
      })
      .sort((a, b) => (SEV_ORDER[a.severity] - SEV_ORDER[b.severity])
        || (new Date(b.ts) - new Date(a.ts)));
  }, [intelEvents]);

  if (!alerts.length) return null;

  return (
    <div className={`alert-rail ${collapsed ? 'is-collapsed' : ''}`}>
      <button type="button" className="alert-rail__head" onClick={() => setCollapsed((v) => !v)}>
        <span className="alert-rail__dot" />
        <strong>Correlated alerts</strong>
        <span className="alert-rail__count">{alerts.length}</span>
        <span className="alert-rail__chev">{collapsed ? '▸' : '▾'}</span>
      </button>
      {!collapsed && (
        <ul className="alert-rail__list">
          {alerts.map((a) => (
            <li key={a.id} className="alert-rail__item">
              <div className="alert-rail__row">
                <span
                  className="alert-rail__domain"
                  style={{ background: DOMAIN_COLORS[a.domain] || '#ff3b3b' }}
                >
                  {a.domain}
                </span>
                <span className="alert-rail__type">{a.alertType.replace(/_/g, ' ')}</span>
                <span className="alert-rail__age">{relative(a.ts)}</span>
              </div>
              {a.confidence != null && (
                <div className="alert-rail__conf">
                  <span style={{ width: `${Math.round(a.confidence * 100)}%` }} />
                  <b>{Math.round(a.confidence * 100)}%</b>
                </div>
              )}
              {a.sources.length > 0 && (
                <div className="alert-rail__sources">{a.sources.join(' · ')}</div>
              )}
              <div className="alert-rail__actions">
                {Number.isFinite(a.lat) && (
                  <button type="button" onClick={() => onFocus?.(a.lat, a.lon)}>On map</button>
                )}
                {a.caseId && (
                  <button type="button" onClick={() => onOpenCase?.(a.caseId)}>Open case</button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
