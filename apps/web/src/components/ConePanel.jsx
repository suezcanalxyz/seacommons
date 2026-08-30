import React, { useEffect, useMemo, useState } from 'react';

import { descriptionOf } from '../features/intel/categories.js';

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

const AIS_NAV_STATUS = {
  0: 'under way using engine',
  1: 'at anchor',
  2: 'not under command',
  3: 'restricted manoeuvrability',
  5: 'moored',
  6: 'aground',
  8: 'under way sailing',
};

function normalizeEventId(value) {
  return String(value || '').replace(/^intel:/, '');
}

function featurePosition(feature) {
  if (feature?.geometry?.type === 'Point') return feature.geometry.coordinates;
  const ring = feature?.geometry?.type === 'Polygon' ? feature.geometry.coordinates?.[0] : null;
  if (!Array.isArray(ring) || ring.length === 0) return null;
  const sum = ring.reduce((acc, point) => [acc[0] + Number(point[0]), acc[1] + Number(point[1])], [0, 0]);
  return [sum[0] / ring.length, sum[1] / ring.length];
}

function TrackGraphic({ feature, driftFeature, dossier }) {
  const props = feature?.properties || {};
  const publicTrack = Array.isArray(props.observed_track) ? props.observed_track : [];
  const dossierTrack = Array.isArray(dossier?.track_points) ? dossier.track_points : [];
  const observed = (publicTrack.length >= 2 ? publicTrack : dossierTrack)
    .map((point) => ({ lat: Number(point?.lat), lon: Number(point?.lon) }))
    .filter((point) => Number.isFinite(point.lat) && Number.isFinite(point.lon));
  const forecast = driftFeature?.geometry?.type === 'LineString'
    ? driftFeature.geometry.coordinates
      .map((point) => ({ lon: Number(point?.[0]), lat: Number(point?.[1]) }))
      .filter((point) => Number.isFinite(point.lat) && Number.isFinite(point.lon))
    : [];
  const position = featurePosition(feature);
  const fallback = position ? [{ lon: Number(position[0]), lat: Number(position[1]) }] : [];
  const all = [...observed, ...forecast, ...fallback];
  if (all.length === 0) return null;

  const width = 320;
  const height = 170;
  const pad = 18;
  const lats = all.map((point) => point.lat);
  const lons = all.map((point) => point.lon);
  const minLat = Math.min(...lats);
  const maxLat = Math.max(...lats);
  const minLon = Math.min(...lons);
  const maxLon = Math.max(...lons);
  const spanLat = maxLat - minLat || 0.01;
  const spanLon = maxLon - minLon || 0.01;
  const xy = (point) => [
    pad + ((point.lon - minLon) / spanLon) * (width - pad * 2),
    height - pad - ((point.lat - minLat) / spanLat) * (height - pad * 2),
  ];
  const path = (points) => points.map((point, index) => {
    const [x, y] = xy(point);
    return `${index === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  const current = xy(observed.at(-1) || forecast.at(-1) || fallback[0]);

  return (
    <div className="intel-report-graphic">
      <div className="intel-report-graphic__head">
        <strong>AIS movement reconstruction</strong>
        <span>observed track and model products</span>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="AIS track reconstruction">
        <defs>
          <pattern id="intel-report-grid" width="32" height="32" patternUnits="userSpaceOnUse">
            <path d="M 32 0 L 0 0 0 32" fill="none" stroke="rgba(120,190,205,.12)" strokeWidth="1" />
          </pattern>
        </defs>
        <rect width={width} height={height} fill="url(#intel-report-grid)" />
        {forecast.length >= 2 && <path className="intel-report-track intel-report-track--forecast" d={path(forecast)} />}
        {observed.length >= 2 && <path className="intel-report-track intel-report-track--observed" d={path(observed)} />}
        <circle cx={current[0]} cy={current[1]} r="11" className="intel-report-vessel-pulse" />
        <polygon
          points="0,-9 6,7 0,4 -6,7"
          transform={`translate(${current[0]} ${current[1]})`}
          className="intel-report-vessel"
        />
      </svg>
      <div className="intel-report-legend">
        {observed.length >= 2 && <span><i className="is-observed" /> AIS observed · {observed.length} fixes</span>}
        {forecast.length >= 2 && <span><i className="is-forecast" /> simulated drift · {forecast.length} steps</span>}
        {observed.length < 2 && forecast.length < 2 && <span>Latest reported position</span>}
      </div>
    </div>
  );
}

function EvidenceSources({ props }) {
  const records = Array.isArray(props.source_records) && props.source_records.length
    ? props.source_records
    : [{
      source: props.source,
      title: props.title,
      url: props.url,
      timestamp_utc: props.timestamp_utc,
      verification_status: props.verification_status,
    }];
  const sources = records.filter((record) => record?.source || record?.url);
  if (!sources.length) return null;
  return (
    <details className="intel-evidence-sources" open={sources.length === 1}>
      <summary>Evidence sources ({sources.length})</summary>
      <div className="intel-evidence-sources__list">
        {sources.map((record, index) => (
          <article key={`${record.source}-${record.url}-${index}`}>
            <div>
              <strong>{record.source || 'Source'}</strong>
              <span>{String(record.verification_status || 'provenance recorded').replace(/_/g, ' ')}</span>
            </div>
            <p>{record.title || 'Maritime observation'}</p>
            {record.timestamp_utc && <time>{new Date(record.timestamp_utc).toLocaleString('it-IT')}</time>}
            {record.url && <a href={record.url} target="_blank" rel="noopener noreferrer">Open original ↗</a>}
          </article>
        ))}
      </div>
    </details>
  );
}

function IntelView({ panel, apiBase, publicMode, intelDrifts }) {
  const props = panel.feature?.properties || {};
  const mmsi = props.linked_mmsi || props.mmsi;
  const [dossier, setDossier] = useState(null);
  const [dossierLoading, setDossierLoading] = useState(false);
  const driftFeature = useMemo(() => {
    const features = Array.isArray(intelDrifts?.features) ? intelDrifts.features : [];
    const eventId = normalizeEventId(props.drift_event_id || props.id);
    return features.find((feature) => (
      feature.geometry?.type === 'LineString'
      && normalizeEventId(feature.properties?.intel_event_id) === eventId
    ));
  }, [intelDrifts, props.drift_event_id, props.id]);

  useEffect(() => {
    let alive = true;
    if (!mmsi) {
      setDossier(null);
      return undefined;
    }
    setDossier(null);
    setDossierLoading(true);
    const path = publicMode
      ? `/api/v1/live/vessels/${mmsi}/context?hours=168`
      : `/api/v1/mda/vessel/${mmsi}?hours=168`;
    fetch(`${apiBase}${path}`)
      .then((response) => response.ok ? response.json() : null)
      .then((data) => { if (alive) setDossier(data); })
      .catch(() => { if (alive) setDossier(null); })
      .finally(() => { if (alive) setDossierLoading(false); });
    return () => { alive = false; };
  }, [apiBase, mmsi, publicMode]);

  const lifecycle = props.incident_lifecycle
    || (['resolved', 'needs_review', 'archived'].includes(props.kind) ? props.kind : 'active');
  const color = lifecycle === 'archived'
    ? INTEL_KIND_COLOR.archived
    : lifecycle === 'resolved'
    ? INTEL_KIND_COLOR.resolved
    : lifecycle === 'needs_review' || props.severity === 'medium'
      ? INTEL_KIND_COLOR.needs_review
      : ['critical', 'high'].includes(props.severity) || props.sanctions_matched
        ? INTEL_KIND_COLOR.distress
        : INTEL_KIND_COLOR.resolved;
  const when = props.timestamp_utc || props.source_timestamp_utc;
  const coords = featurePosition(panel.feature);
  const eventType = (
    (Array.isArray(props.anomaly_types) && props.anomaly_types[0])
    || props.anomaly_type
    || props.ais_nav_status_kind
    || props.alert_type
    || props.type
    || 'maritime signal'
  ).replace(/_/g, ' ');
  const sanctions = dossier?.identity?.sanctions || [];

  return (
    <>
      <div className="cone-section">
        <div className="intel-report-title">
          <span style={{ background: color }} />
          <strong>{props.vessel_name || props.ship_name || dossier?.static?.name || props.title || 'Maritime signal'}</strong>
        </div>
        {props.text && <p className="intel-report-summary">{props.text}</p>}
        <Row label="Event" value={eventType} />
        <Row label="Status" value={lifecycle} color={color} />
        {props.verification_status && <Row label="Verification" value={String(props.verification_status).replace(/_/g, ' ')} />}
        {props.severity && <Row label="Severity" value={props.severity} />}
        <Row label="Reported" value={when ? new Date(when).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' }) : '—'} />
        {coords && <Row label="Coordinates" value={`${Number(coords[1]).toFixed(5)}, ${Number(coords[0]).toFixed(5)}`} mono />}
      </div>

      <div className="cone-section intel-report-visual">
        <TrackGraphic feature={panel.feature} driftFeature={driftFeature} dossier={dossier} />
      </div>

      <div className="cone-section">
        <SectionLabel>Professional vessel identity</SectionLabel>
        <Row label="Name" value={dossier?.static?.name || props.vessel_name || props.ship_name || '—'} />
        <Row label="MMSI" value={mmsi || '—'} mono />
        <Row label="IMO" value={dossier?.static?.imo || props.imo || '—'} mono />
        <Row label="Flag" value={dossier?.static?.flag || dossier?.identity?.mid_flag || props.flag || '—'} />
        {props.ship_type != null && <Row label="AIS ship type" value={props.ship_type} />}
        {props.latest_nav_status != null && <Row label="Navigation" value={AIS_NAV_STATUS[props.latest_nav_status] || `status ${props.latest_nav_status}`} />}
        {Number.isFinite(Number(props.latest_sog)) && <Row label="Speed" value={`${Number(props.latest_sog).toFixed(1)} kn`} />}
        {dossierLoading && <div className="intel-report-loading">Loading vessel registry and sanctions…</div>}
      </div>

      <div className="cone-section">
        <SectionLabel>Why this was flagged</SectionLabel>
        <p className="intel-report-note">{props.detection_reason || props.detail || descriptionOf(props.type)}</p>
        {props.infrastructure && (
          <div className="intel-report-warning">
            <strong>Infrastructure proximity context</strong>
            <span>
              {Number.isFinite(Number(props.infrastructure.distance_km)) ? `${Number(props.infrastructure.distance_km).toFixed(1)} km from ` : ''}
              {props.infrastructure.name || props.infrastructure.kind}.
            </span>
            <small>Proximity and loitering are anomaly context, not proof of interference or intent.</small>
          </div>
        )}
        {props.status_note && <p className="intel-report-note">{props.status_note}</p>}
      </div>

      {(props.sanctions_matched || sanctions.length > 0) && (
        <div className="cone-section">
          <SectionLabel>Sanctions screening</SectionLabel>
          {sanctions.length === 0 ? <p className="intel-report-warning">Sanctions match recorded; detailed list record unavailable.</p> : sanctions.map((sanction, index) => (
            <article className="mda-sanctions" key={`${sanction.list}-${index}`}>
              <strong>{sanction.list}{sanction.program ? ` · ${sanction.program}` : ''}</strong>
              {sanction.reason && <span>{sanction.reason}</span>}
              {sanction.description && <span>{sanction.description}</span>}
              {sanction.listed_on && <span>listed {sanction.listed_on}</span>}
              {sanction.source_url && <a href={sanction.source_url} target="_blank" rel="noopener noreferrer">Official/list source ↗</a>}
            </article>
          ))}
        </div>
      )}

      {Array.isArray(props.updates) && props.updates.length > 0 && (
        <div className="cone-section">
          <SectionLabel>Episode updates</SectionLabel>
          <ol className="intel-report-updates">
            {props.updates.map((update) => (
              <li key={`${update.id}-${update.timestamp_utc}`}>
                <time>{update.timestamp_utc ? new Date(update.timestamp_utc).toLocaleString('it-IT') : '—'}</time>
                <span>{String(update.anomaly_type || update.type || 'signal').replace(/_/g, ' ')}</span>
              </li>
            ))}
          </ol>
        </div>
      )}

      <div className="cone-section" style={{ borderBottom: 'none' }}>
        <EvidenceSources props={props} />
      </div>
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

export default function MapFloatingPanel({ panel, onClose, onComputeDrift, apiBase, publicMode, intelDrifts }) {
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
    <div className={`cone-panel${panel.type === 'intel' ? ' cone-panel--intel' : ''}`}>
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
        <IntelView panel={panel} apiBase={apiBase} publicMode={publicMode} intelDrifts={intelDrifts} />
      )}
    </div>
  );
}
