import React from 'react';

const HORIZON = {
  cone_6h:  '6 h drift zone',
  cone_12h: '12 h drift zone',
  cone_18h: '18 h drift zone',
  cone_24h: '24 h drift zone',
};

const OBLIGATION_COLOR = {
  critical: '#ff3b3b',
  high:     '#ff7b54',
  medium:   '#ffe07d',
  low:      '#8bf0c5',
};

const RISK_COLOR = {
  critical: '#ff3b3b',
  high:     '#f97316',
  medium:   '#ffe07d',
  low:      '#8bf0c5',
};

function SectionLabel({ children }) {
  return (
    <div style={{
      fontSize: 9, color: '#87cabc', textTransform: 'uppercase',
      letterSpacing: '0.13em', marginBottom: 5,
    }}>
      {children}
    </div>
  );
}

function Row({ label, value, color, mono }) {
  return (
    <div className="cone-row">
      <span>{label}</span>
      <strong style={color ? { color } : mono ? { fontFamily: 'monospace', fontSize: 10 } : {}}>
        {value ?? '—'}
      </strong>
    </div>
  );
}

function ZoneBadge({ zone }) {
  const col = OBLIGATION_COLOR[zone.obligation_level] || '#8bf0c5';
  return (
    <div style={{
      padding: '4px 8px', marginBottom: 4, borderRadius: 3,
      background: `${col}18`, border: `1px solid ${col}44`,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: 10, fontWeight: 700, color: col }}>{zone.name}</span>
        <span style={{
          fontSize: 9, background: `${col}30`, color: col,
          padding: '1px 5px', borderRadius: 2,
        }}>{zone.zone_type.replace(/_/g, ' ')}</span>
      </div>
      <div style={{ fontSize: 10, color: '#87cabc', marginTop: 2 }}>
        {zone.mrcc}
        {zone.mrcc_tel ? <span style={{ opacity: 0.7 }}> · {zone.mrcc_tel}</span> : null}
      </div>
      {zone.warning && (
        <div style={{ fontSize: 9, color: '#ff3b3b', marginTop: 3, fontWeight: 600 }}>
          ⚠ {zone.warning}
        </div>
      )}
    </div>
  );
}

function SurvivalBar({ pct, color }) {
  return (
    <div style={{ height: 4, background: 'rgba(255,255,255,0.08)', borderRadius: 2, margin: '4px 0 6px' }}>
      <div style={{ height: '100%', width: `${Math.min(100, pct)}%`, background: color, borderRadius: 2, transition: 'width 0.4s' }} />
    </div>
  );
}

function LegalNote({ note, idx }) {
  return (
    <div style={{
      fontSize: 10, color: '#a0c4bb', lineHeight: 1.45,
      padding: '3px 0 3px 10px',
      borderLeft: '2px solid rgba(139,240,197,0.2)',
      marginBottom: 3,
    }}>
      {note}
    </div>
  );
}

function LocationView({ panel, onComputeDrift }) {
  return (
    <>
      <div className="cone-section">
        <Row label="Lat" value={panel.lat} mono />
        <Row label="Lon" value={panel.lon} mono />
      </div>

      {panel.vessels && panel.vessels.length > 0 && (
        <div className="cone-section">
          <SectionLabel>Nearest vessels</SectionLabel>
          {panel.vessels.slice(0, 3).map((v, i) => (
            <Row key={v.mmsi || i}
              label={v.ship_name || v.mmsi || '—'}
              value={v.distance_nm ? v.distance_nm.toFixed(1) + ' nm' : '—'}
            />
          ))}
        </div>
      )}

      {panel.weather && (
        <div className="cone-section">
          <SectionLabel>Conditions</SectionLabel>
          <Row label="Wind" value={`${panel.weather.wind?.speed_ms} m/s ${panel.weather.wind?.direction_label}`} />
          <Row label="Waves" value={`${panel.weather.waves?.significant_height_m} m`} />
        </div>
      )}

      <div className="cone-section" style={{ borderBottom: 'none' }}>
        <button
          onClick={onComputeDrift}
          style={{
            width: '100%', border: 0, borderRadius: 3, padding: '7px 0',
            background: 'linear-gradient(135deg,#83f4df,#70a2ff)',
            color: '#061015', fontWeight: 700, fontSize: 11, cursor: 'pointer',
          }}
        >
          Compute drift here
        </button>
      </div>
    </>
  );
}

function ConeView({ panel }) {
  const props = panel.feature?.properties || {};
  const label = HORIZON[props.type] || props.type || 'Drift zone';
  const sim = panel.simParams || {};
  const law = panel.legalAnalysis;

  const survivalPct = law
    ? Math.min(100, (law.survival.estimated_survival_hours / (law.duration_h || 24)) * 100)
    : null;
  const survivalColor = law ? (RISK_COLOR[law.survival.risk_level] || '#8bf0c5') : '#8bf0c5';

  return (
    <>
      {/* ── Drift horizon & status ── */}
      <div className="cone-section">
        <Row label="Horizon" value={label} />
        {panel.eventId && <Row label="Event" value={panel.eventId.slice(0, 12) + '…'} />}
        {panel.caseStatus && <Row label="Status" value={panel.caseStatus} />}
        {law?.drift_nm != null && <Row label="Drift distance" value={`${law.drift_nm} nm`} />}
      </div>

      {/* ── Search area (probability of containment) ── */}
      {Number.isFinite(Number(props.area_km2)) && (
        <div className="cone-section">
          <SectionLabel>Search area · 90% containment</SectionLabel>
          <Row label="Area" value={`${Number(props.area_km2).toFixed(1)} km²`} />
          {Number.isFinite(Number(props.radius_p90_m)) && (
            <Row label="Radius (90%)" value={`${(Number(props.radius_p90_m) / 1000).toFixed(1)} km`} />
          )}
          {Number.isFinite(Number(props.radius_p50_m)) && (
            <Row label="Radius (50%)" value={`${(Number(props.radius_p50_m) / 1000).toFixed(1)} km`} />
          )}
          {Array.isArray(props.semi_axes_p90_m) && props.semi_axes_p90_m.length === 2 && (
            <Row
              label="Axes (90%)"
              value={`${(props.semi_axes_p90_m[0] / 1000).toFixed(1)} × ${(props.semi_axes_p90_m[1] / 1000).toFixed(1)} km`}
              mono
            />
          )}
          {props.particles && <Row label="Particles" value={props.particles} />}
        </div>
      )}

      {/* ── Simulation parameters ── */}
      {(sim.scenarioType || sim.vesselType || sim.persons) && (
        <div className="cone-section">
          <SectionLabel>Simulation</SectionLabel>
          {sim.scenarioType && <Row label="Emergency" value={sim.scenarioType.replace(/_/g, ' ')} />}
          {sim.vesselType  && <Row label="Vessel"    value={sim.vesselType.replace(/_/g, ' ')} />}
          {sim.persons     && <Row label="Persons"   value={sim.persons} />}
          {sim.riskLevel   && <Row label="Risk"      value={sim.riskLevel} />}
          {sim.lat && <Row label="Origin" value={`${Number(sim.lat).toFixed(4)}, ${Number(sim.lon).toFixed(4)}`} mono />}
        </div>
      )}

      {/* ── Survival estimate ── */}
      {law?.survival && (
        <div className="cone-section">
          <SectionLabel>Survival estimate</SectionLabel>
          <Row
            label="Risk level"
            value={law.survival.risk_level.toUpperCase()}
            color={RISK_COLOR[law.survival.risk_level]}
          />
          <Row label="Est. survival window" value={`${law.survival.estimated_survival_hours} h`} />
          {survivalPct !== null && (
            <SurvivalBar pct={survivalPct} color={survivalColor} />
          )}
          <Row label="Sea state" value={`Bf ${law.survival.beaufort} — ${law.survival.sea_state}`} />
          <Row label="Wave height" value={`${law.survival.wave_height_m} m`} />
          <Row label="Capsizing risk" value={`${law.survival.capsizing_risk_pct}%`}
            color={law.survival.capsizing_risk_pct > 60 ? '#ff3b3b' : undefined} />
          {law.warnings?.length > 0 && (
            <div style={{ marginTop: 4 }}>
              {law.warnings.map((w, i) => (
                <div key={i} style={{ fontSize: 9, color: '#ff3b3b', fontWeight: 700, marginBottom: 2 }}>
                  ⚠ {w}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── SAR zones ── */}
      {law?.origin_zones?.length > 0 && (
        <div className="cone-section">
          <SectionLabel>SAR zones (origin)</SectionLabel>
          {law.origin_zones.map((z) => <ZoneBadge key={z.id} zone={z} />)}
        </div>
      )}

      {/* ── Trajectory zones (if different from origin) ── */}
      {law?.trajectory_zones?.length > 0 && (() => {
        const originIds = new Set((law.origin_zones || []).map(z => z.id));
        const extra = law.trajectory_zones.filter(z => !originIds.has(z.id));
        return extra.length > 0 ? (
          <div className="cone-section">
            <SectionLabel>Zones entered during drift</SectionLabel>
            {extra.map((z) => <ZoneBadge key={z.id} zone={z} />)}
          </div>
        ) : null;
      })()}

      {/* ── MRCC contacts ── */}
      {law?.all_contacts?.length > 0 && (
        <div className="cone-section">
          <SectionLabel>MRCC contacts</SectionLabel>
          {law.all_contacts.map((c, i) => (
            <div key={i} className="cone-row" style={{ alignItems: 'flex-start' }}>
              <span style={{ flex: 1 }}>{c.name}</span>
              <strong style={{ fontFamily: 'monospace', fontSize: 10, color: '#8bf0c5' }}>{c.tel}</strong>
            </div>
          ))}
        </div>
      )}

      {/* ── Legal framework ── */}
      {law?.legal_notes?.length > 0 && (
        <div className="cone-section" style={{ borderBottom: 'none' }}>
          <SectionLabel>Legal framework</SectionLabel>
          {law.legal_notes.map((note, i) => <LegalNote key={i} note={note} idx={i} />)}
          <div style={{ fontSize: 9, color: '#4a6a64', marginTop: 6 }}>
            Sources: SOLAS V/33, UNCLOS Art. 98, IAMSAR Manual, IMO SAR Convention 1979
          </div>
        </div>
      )}
    </>
  );
}

const INTEL_KIND_COLOR = { distress: '#ff3b3b', resolved: '#22c55e', needs_review: '#f59e0b', archived: '#9aa0ab' };

function IntelView({ panel }) {
  const props = panel.feature?.properties || {};
  const lifecycle = props.incident_lifecycle
    || (['resolved', 'needs_review', 'archived'].includes(props.kind) ? props.kind : 'distress');
  const color = INTEL_KIND_COLOR[lifecycle] || INTEL_KIND_COLOR.distress;
  const when = props.timestamp_utc || props.source_timestamp_utc;
  return (
    <>
      <div className="cone-section">
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: color, flex: '0 0 auto' }} />
          <strong style={{ fontSize: 12, lineHeight: 1.35 }}>{props.title || 'Maritime signal'}</strong>
        </div>
        {props.text && (
          <p style={{ fontSize: 11, color: '#c9e3da', lineHeight: 1.5, margin: '4px 0 8px' }}>{props.text}</p>
        )}
        <Row label="Source" value={props.source || '—'} />
        <Row label="Status" value={lifecycle} color={color} />
        {props.verification_status && (
          <Row label="Verification" value={String(props.verification_status).replace(/_/g, ' ')} />
        )}
        {props.severity && <Row label="Severity" value={props.severity} />}
        <Row
          label="Reported"
          value={when ? new Date(when).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' }) : '—'}
        />
      </div>
      {props.url && (
        <div className="cone-section" style={{ borderBottom: 'none' }}>
          <a
            href={props.url}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              display: 'block', textAlign: 'center', padding: '7px 0', borderRadius: 3,
              background: 'rgba(131,244,223,0.12)', border: '1px solid rgba(131,244,223,0.35)',
              color: '#83f4df', fontWeight: 700, fontSize: 11, textDecoration: 'none',
            }}
          >
            Open source ↗
          </a>
        </div>
      )}
    </>
  );
}

function TrajectoryView({ panel }) {
  const props = panel.feature?.properties || {};
  const meanSpeed = Number(props.mean_speed_ms);
  const maxSpeed = Number(props.max_speed_ms);
  const distance = Number(props.distance_m);
  return (
    <>
      <div className="cone-section">
        <SectionLabel>Live model product</SectionLabel>
        <Row label="Signal" value={props.intel_title || props.intel_event_id || 'Published signal'} />
        <Row label="Source" value={props.intel_source || 'published feed'} />
        <Row label="Status" value={props.verification_status || 'modelled'} color="#8bf0c5" />
      </div>
      <div className="cone-section">
        <SectionLabel>Trajectory dynamics</SectionLabel>
        <Row
          label="Mean drift speed"
          value={Number.isFinite(meanSpeed)
            ? `${meanSpeed.toFixed(2)} m/s · ${(meanSpeed * 1.943844).toFixed(2)} kn`
            : '—'}
        />
        <Row
          label="Peak drift speed"
          value={Number.isFinite(maxSpeed)
            ? `${maxSpeed.toFixed(2)} m/s · ${(maxSpeed * 1.943844).toFixed(2)} kn`
            : '—'}
        />
        <Row label="Path distance" value={Number.isFinite(distance) ? `${(distance / 1000).toFixed(1)} km` : '—'} />
        <Row label="Samples" value={props.sample_count || '—'} />
        <Row label="Interval" value={props.sample_interval_s ? `${Number(props.sample_interval_s) / 60} min` : '—'} />
      </div>
      <div className="cone-section" style={{ borderBottom: 'none' }}>
        <SectionLabel>Provenance</SectionLabel>
        <Row label="Model" value={props.model || 'OpenDrift Leeway'} />
        <Row label="Forcing" value={props.forcing_resolution || '—'} />
        <div style={{ fontSize: 9, color: '#87cabc', lineHeight: 1.45, marginTop: 6 }}>
          Forecast trajectory from time-varying environmental forcing. It is not an observed GPS track.
        </div>
      </div>
    </>
  );
}

export default function MapFloatingPanel({ panel, onClose, onComputeDrift }) {
  if (!panel) return null;

  const title = panel.type === 'trajectory'
    ? 'Live drift trajectory'
    : panel.type === 'cone'
      ? 'Drift projection'
      : panel.type === 'intel'
        ? 'Signal'
        : 'Selected point';
  const kicker = panel.type === 'trajectory'
    ? 'OpenDrift forecast'
    : panel.type === 'cone'
      ? 'SAR drift cone'
      : panel.type === 'intel'
        ? 'Live report'
        : 'Map click';

  return (
    <div className="cone-panel">
      <div className="cone-panel-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <span className="section-kicker">{kicker}</span>
          <strong style={{ fontSize: 13, display: 'block', marginTop: 2 }}>{title}</strong>
        </div>
        <button className="cone-close-btn" onClick={onClose}>×</button>
      </div>

      {panel.type === 'location' && (
        <LocationView panel={panel} onComputeDrift={onComputeDrift} />
      )}
      {panel.type === 'cone' && (
        <ConeView panel={panel} />
      )}
      {panel.type === 'trajectory' && (
        <TrajectoryView panel={panel} />
      )}
      {panel.type === 'intel' && (
        <IntelView panel={panel} />
      )}
    </div>
  );
}
