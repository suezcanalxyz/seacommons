import React, { useState } from 'react';

const SCENARIO_TYPES = [
  { value: 'distress',       label: 'Distress',       icon: '🆘' },
  { value: 'engine_failure', label: 'Engine failure',  icon: '⚙️' },
  { value: 'man_overboard',  label: 'Man overboard',   icon: '🏊' },
  { value: 'fire',           label: 'Fire',            icon: '🔥' },
  { value: 'medical',        label: 'Medical',         icon: '🏥' },
  { value: 'sinking',        label: 'Sinking',         icon: '⚓' },
  { value: 'search_area',    label: 'Search area',     icon: '🔍' },
  { value: 'unknown',        label: 'Unknown',         icon: '❓' },
];

const VESSEL_TYPES = [
  { value: 'rubber_boat',    label: 'Rubber boat' },
  { value: 'life_raft',      label: 'Life raft' },
  { value: 'fishing_vessel', label: 'Fishing vessel' },
  { value: 'wooden_boat',    label: 'Wooden boat' },
  { value: 'sailboat',       label: 'Sailboat' },
  { value: 'motorboat',      label: 'Motorboat' },
  { value: 'container_ship', label: 'Cargo / container' },
  { value: 'unknown',        label: 'Unknown' },
];

const RISK_LEVELS = [
  { value: 'high',   label: 'High' },
  { value: 'medium', label: 'Medium' },
  { value: 'low',    label: 'Low' },
];

export default function ScenarioModal({ lat, lon, form, onFormChange, onConfirm, onClose }) {
  const [scenarioType, setScenarioType] = useState('distress');

  function handleConfirm() {
    onConfirm({ scenarioType });
  }

  return (
    <div className="scenario-backdrop" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="scenario-modal">
        <div className="scenario-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <span className="section-kicker">New SAR case</span>
            <strong style={{ display: 'block', fontSize: 14, marginTop: 2 }}>
              {Number(lat).toFixed(4)}, {Number(lon).toFixed(4)}
            </strong>
          </div>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', color: '#9cb5b0', cursor: 'pointer', fontSize: 18, lineHeight: 1, padding: 0 }}
          >×</button>
        </div>

        <p className="section-kicker" style={{ marginBottom: 6 }}>Emergency type</p>
        <div className="scenario-types">
          {SCENARIO_TYPES.map((s) => (
            <button
              key={s.value}
              className={`scenario-type-btn${scenarioType === s.value ? ' is-active' : ''}`}
              onClick={() => setScenarioType(s.value)}
              type="button"
            >
              <span className="scenario-icon">{s.icon}</span>
              {s.label}
            </button>
          ))}
        </div>

        <div className="scenario-vessel">
          <p className="section-kicker" style={{ marginBottom: 6 }}>Vessel &amp; persons</p>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
            <label className="field-block">
              Vessel type
              <select value={form.vessel_type} onChange={(e) => onFormChange('vessel_type', e.target.value)}>
                {VESSEL_TYPES.map((v) => <option key={v.value} value={v.value}>{v.label}</option>)}
              </select>
            </label>
            <label className="field-block">
              Persons aboard
              <input type="number" min="1" value={form.persons} onChange={(e) => onFormChange('persons', e.target.value)} />
            </label>
          </div>
        </div>

        <div className="scenario-params" style={{ borderBottom: 'none', marginBottom: 0 }}>
          <p className="section-kicker" style={{ marginBottom: 6 }}>Risk level</p>
          <div style={{ display: 'flex', gap: 6 }}>
            {RISK_LEVELS.map((r) => (
              <button
                key={r.value}
                type="button"
                onClick={() => onFormChange('risk_level', r.value)}
                style={{
                  flex: 1, padding: '6px 0', borderRadius: 3, fontSize: 11, fontWeight: 600, cursor: 'pointer',
                  border: form.risk_level === r.value ? '1px solid rgba(131,244,223,0.5)' : '1px solid rgba(255,255,255,0.09)',
                  background: form.risk_level === r.value ? 'rgba(131,244,223,0.12)' : 'rgba(255,255,255,0.04)',
                  color: form.risk_level === r.value ? '#cffffa' : '#c8dfd9',
                }}
              >
                {r.label}
              </button>
            ))}
          </div>
        </div>

        <div style={{ marginTop: 14, display: 'flex', gap: 7 }}>
          <button
            type="button"
            onClick={handleConfirm}
            style={{
              flex: 1, padding: '9px 0', borderRadius: 3, border: 0,
              background: 'linear-gradient(135deg,#83f4df,#70a2ff)',
              color: '#061015', fontWeight: 700, fontSize: 12, cursor: 'pointer',
            }}
          >
            Compute drift
          </button>
          <button
            type="button"
            onClick={onClose}
            style={{
              padding: '9px 14px', borderRadius: 3, fontSize: 11, cursor: 'pointer',
              border: '1px solid rgba(255,255,255,0.1)',
              background: 'rgba(255,255,255,0.04)', color: '#9cb5b0',
            }}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
