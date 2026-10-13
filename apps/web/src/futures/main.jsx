import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './futures.css';
const ENDPOINTS = { summary: '/api/v1/ops/summary', stats: '/api/v1/ops/stats', data: '/api/v1/ops/data-status', play: '/api/v1/play/counts', cache: '/api/v1/play/cache-status' };
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
  const [tab, setTab] = useState('Dashboard');
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
  const play = snapshot.play?.data || {};
  const cache = snapshot.cache?.data || {};
  const snapshotAge = play.generated_at ? Math.max(0, Math.round((Date.now() - Date.parse(play.generated_at)) / 60000)) : null;
  const criticalities = [
    { title: 'PLAY snapshot freshness', level: snapshot.play?.error ? 'Unavailable' : snapshotAge == null ? 'Unknown' : snapshotAge > 5 ? 'Delayed' : 'Within threshold', detail: snapshotAge == null ? 'Snapshot age cannot be established.' : `Snapshot age: ${snapshotAge} min. Configured cache TTL: 60 seconds. HTTP success does not prove freshness.`, action: 'Isolate catalog computation from HTTP, implement single-flight persistent snapshots and alert on age.', evidence: play.generated_at || 'No timestamp reported' },
    { title: 'Cache refresh diagnostics', level: snapshot.cache?.error ? 'Not deployed / unavailable' : cache.catalog?.refreshing ? 'Refreshing' : 'Observed', detail: snapshot.cache?.error ? `Cache diagnostics: ${snapshot.cache.error}. Endpoint must be deployed before refresh health can be verified.` : `Catalog age: ${cache.catalog?.age_seconds ?? 'unknown'} s; refreshing: ${String(cache.catalog?.refreshing ?? 'unknown')}; last error: ${cache.catalog?.last_error || 'none reported'}.`, action: 'Deploy tested cache diagnostics and measure refresh completion, not only endpoint latency.', evidence: 'API /api/v1/play/cache-status' },
    { title: 'Darkship scheduler overlap', level: 'Previously observed', detail: '13 Oct: repeated _job_darkship_cue_refresh runs skipped because the previous execution was still active. Historical observation, not a live alarm.', action: 'Bound job runtime and concurrency; move heavy analysis to a resource-limited worker.', evidence: 'Operational checks, 13 Oct 2026' },
    { title: 'Distress drift isolation', level: 'Implementation required', detail: 'Drift evidence is already linked to PLAY. Automatic pending drift scheduling was disabled in inspected source; do not equate predicted drift with observed vessel position.', action: 'Use a dedicated prioritized, deduplicated drift queue with provenance, uncertainty and resource budgets.', evidence: 'core/scheduler.py and PLAY evidence projection' }
  ];
  const dashboard = [
    {title:'Operational health', description:'Live API, source health and processing status.', value: snapshot.summary?.error ? 'Unavailable' : snapshot.summary ? 'Connected' : 'Checking', target:'Operations'},
    {title:'PLAY archive', description:'Public catalog and snapshot freshness.', value: play.total_count != null ? `${Number(play.total_count).toLocaleString()} records` : 'Not reported', target:'Intelligence'},
    {title:'Data ingestion', description:'Source ingestion and evidence processing.', value: data.ingestion ? 'Metrics available' : 'Not reported', target:'Intelligence'},
    {title:'Drift intelligence', description:'Model-derived drift evidence and computational needs.', value: data.drift ? 'Metrics available' : 'Not reported', target:'Intelligence'},
    {title:'Scheduled operations', description:'Job execution and monitoring signals.', value: summary.scheduler ? 'Scheduler status available' : 'Not reported', target:'Operations'},
    {title:'Partner Hub', description:'Collaboration, infrastructure support and member requests.', value:'Collaboration', target:'Partner Hub'},
    {title:'Documents', description:'Architecture, methodology, partner materials and technical references.', value:'Reference library', target:'Documents'},
  ];
  const sections = tab === 'Operations'
    ? [['Backend', summary.backend], ['Scheduler', summary.scheduler], ['Sources', summary.channels], ['Cost profile', summary.cost_profile]]
    : [['Ingestion', data.ingestion], ['Forensic record', data.intel_record], ['Drift', data.drift], ['Compute', data.compute], ['SAR', stats.sar], ['Signals', stats.signals]];
  return <main className="futures"><header><div><small>SEA COMMONS / FUTURES</small><h1>Operations intelligence</h1><p>Measured system data, refreshed every 60 seconds. Missing values are never inferred.</p></div><nav><a href="https://live.seacommons.org">Live ↗</a><a href="https://play.seacommons.org">Play ↗</a><a href="https://seacommons.org/docs">Docs ↗</a></nav></header><div className="futures-toolbar"><div>{['Dashboard', 'Intelligence', 'Operations', 'Agentic Workflow', 'Partner Hub', 'Documents'].map(name => <button key={name} className={tab === name ? 'selected' : ''} onClick={() => setTab(name)}>{name}</button>)}</div><span>{updated ? `Last checked ${updated.toLocaleTimeString()}` : 'Connecting…'}</span></div>{tab === 'Documents' ? <section className="futures-card"><h2>Document workspace</h2><p>Document production and native editors are not enabled in this release. Use the existing technical documentation while DOCX, XLSX and PPTX rendering is being implemented and validated.</p><a href="https://seacommons.org/docs">Open technical documentation ↗</a></section> : tab === 'Partner Hub' ? <div className="futures-grid"><section className="futures-card"><h2>Partner collaboration</h2><p>Share infrastructure, research expertise, source integrations or development support. Requests and invitations will be tracked through an authenticated partner workspace once its backend and approval workflow are enabled.</p><p><b>Oracle Cloud development support:</b> SeaCommons needs additional isolated compute capacity for drift, satellite processing and geospatial analysis. Partners can offer compatible Oracle Cloud resources, credits or technical assistance without sharing VM credentials.</p><p>Future phases: self-hosted workers and API-to-API integrations.</p><a href="mailto:republic@suezcanal.xyz?subject=SeaCommons%20Futures%20-%20Partner%20collaboration">Contact the project team ↗</a></section><section className="futures-card"><h2>Members and invitations</h2><p>Invitations require administrator approval. No account or role is activated merely by appearing in this list.</p><dl><div><dt>Proposed member</dt><dd>sofia.baldi.it@gmail.com</dd></div><div><dt>Access</dt><dd>Pending role confirmation</dd></div><div><dt>Invitation</dt><dd>Not sent</dd></div></dl><p>Partner requests, conversations, attachments and member approvals are planned, not yet enabled.</p></section></div> : tab === 'Agentic Workflow' ? <section className="futures-card"><h2>Scheduled and agentic operations</h2><p>Scheduler health is read from operational telemetry. A persistent per-run history, agent responses and approval-gated actions require a dedicated event log and authenticated backend; these are not yet connected.</p>{summary.scheduler ? <dl>{entries(summary.scheduler).slice(0,40).map(item=><div key={item.name}><dt>{item.name}</dt><dd>{item.value}</dd></div>)}</dl> : <p>Scheduler telemetry not reported.</p>}</section> : tab === 'Dashboard' ? <><div className="futures-grid">{dashboard.map(item=><section key={item.title} className="futures-card futures-summary"><h2>{item.title}</h2><strong>{item.value}</strong><p>{item.description}</p><button onClick={()=>setTab(item.target)}>Explore {item.target} ↗</button></section>)}</div><section className="futures-card futures-overview"><h2>What SeaCommons does</h2><p>SeaCommons combines maritime signals, humanitarian incident monitoring, satellite observations, drift modelling and evidence-linked forensic reconstruction. LIVE supports current monitoring, PLAY exposes the public historical archive, and FUTURES documents operations, limits and collaboration opportunities.</p><p>Observations, model predictions and verified findings remain distinct. The system is under active development; operational metrics and known issues are shown with their source and freshness.</p></section></> : <><div className="futures-health">{Object.entries(ENDPOINTS).map(([name]) => <div key={name}><strong>{name === 'data' ? 'Data status' : name}</strong><span className={snapshot[name]?.error ? 'bad' : 'good'}>{!snapshot[name] ? 'Checking' : snapshot[name].error || 'Connected'}</span></div>)}</div>{tab === 'Operations' && <section className="futures-card futures-issues"><h2>Operational criticalities</h2><p>Live signals are distinguished from previously observed issues and planned remediation.</p><div className="futures-issue-grid">{criticalities.map(item => <article key={item.title} className="futures-issue"><div className="futures-issue-heading"><strong>{item.title}</strong><span>{item.level}</span></div><p>{item.detail}</p><p><b>Remediation:</b> {item.action}</p><small>Evidence: {item.evidence}</small></article>)}</div></section>}<div className="futures-grid">{sections.map(([name, values]) => <section key={name} className="futures-card"><h2>{name}</h2>{values && Object.keys(values).length ? <dl>{entries(values).slice(0,90).map(item => <div key={item.name}><dt>{item.name}</dt><dd>{item.value}</dd></div>)}</dl> : <p>Not reported by the API.</p>}</section>)}</div></>}</main>;
}
createRoot(document.getElementById('futures-root')).render(<App />);
