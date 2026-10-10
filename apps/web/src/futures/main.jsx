import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './futures.css';
const ENDPOINTS = { summary: '/api/v1/ops/summary', stats: '/api/v1/ops/stats', data: '/api/v1/ops/data-status' };
const entries = (obj, prefix = '') => Object.entries(obj || {}).flatMap(([key, value]) => {
  const name = prefix ? `${prefix} / ${key.replaceAll('_', ' ')}` : key.replaceAll('_', ' ');
  if (value && typeof value === 'object' && !Array.isArray(value)) return entries(value, name);
  if (Array.isArray(value)) return [{ name, value: `${value.length} records` }];
  if (value == null || typeof value === 'object') return [];
  return [{ name, value: String(value) }];
});
function App() {
  const [snapshot, setSnapshot] = useState({});
  const [updated, setUpdated] = useState(null);
  const [tab, setTab] = useState('Metrics');
  useEffect(() => {
    let active = true;
    async function refresh() {
      const results = await Promise.all(Object.entries(ENDPOINTS).map(async ([name, path]) => {
        try {
          const response = await fetch(path, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          return [name, { data: await response.json(), error: null }];
        } catch (error) { return [name, { data: null, error: error.message }]; }
      }));
      if (active) { setSnapshot(Object.fromEntries(results)); setUpdated(new Date()); }
    }
    refresh(); const interval = setInterval(refresh, 60000);
    return () => { active = false; clearInterval(interval); };
  }, []);
  const data = snapshot.data?.data || {};
  const summary = snapshot.summary?.data || {};
  const stats = snapshot.stats?.data || {};
  const sections = tab === 'Operations'
    ? [['Backend', summary.backend], ['Scheduler', summary.scheduler], ['Sources', summary.channels], ['Cost profile', summary.cost_profile]]
    : [['Ingestion', data.ingestion], ['Forensic record', data.intel_record], ['Drift', data.drift], ['Compute', data.compute], ['SAR', stats.sar], ['Signals', stats.signals]];
  return <main className="futures"><header><div><small>SEA COMMONS / FUTURES</small><h1>Operations intelligence</h1><p>Measured system data, refreshed every 60 seconds. Missing values are never inferred.</p></div><nav><a href="https://live.seacommons.org">Live ↗</a><a href="https://play.seacommons.org">Play ↗</a><a href="https://seacommons.org/docs">Docs ↗</a></nav></header><div className="futures-toolbar"><div>{['Metrics', 'Operations', 'Documents'].map(name => <button key={name} className={tab === name ? 'selected' : ''} onClick={() => setTab(name)}>{name}</button>)}</div><span>{updated ? `Last checked ${updated.toLocaleTimeString()}` : 'Connecting…'}</span></div>{tab === 'Documents' ? <section className="futures-card"><h2>Document workspace</h2><p>Document production and native editors are not enabled in this release. Use the existing technical documentation while DOCX, XLSX and PPTX rendering is being implemented and validated.</p><a href="https://seacommons.org/docs">Open technical documentation ↗</a></section> : <><div className="futures-health">{Object.entries(ENDPOINTS).map(([name]) => <div key={name}><strong>{name === 'data' ? 'Data status' : name}</strong><span className={snapshot[name]?.error ? 'bad' : 'good'}>{!snapshot[name] ? 'Checking' : snapshot[name].error || 'Connected'}</span></div>)}</div><div className="futures-grid">{sections.map(([name, values]) => <section key={name} className="futures-card"><h2>{name}</h2>{values && Object.keys(values).length ? <dl>{entries(values).slice(0,90).map(item => <div key={item.name}><dt>{item.name}</dt><dd>{item.value}</dd></div>)}</dl> : <p>Not reported by the API.</p>}</section>)}</div></>}</main>;
}
createRoot(document.getElementById('futures-root')).render(<App />);
