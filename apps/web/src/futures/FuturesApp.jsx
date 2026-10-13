import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '../auth.jsx';
import { fetchJson } from '../services/api/client.js';
import { resolveSiteApiBase } from '../site/liveApi.js';
import {
  accessMatrix,
  guidebook,
  partnerDocuments,
  pilotFramework,
  presentationSlides,
  roadmap,
  verticalPathways,
  seaCommonsProject,
  supportAreas,
  timeline,
  tools,
} from './data.js';
import { operationalAudit, hardwareNetwork } from './operationalAudit.js';
import { MethodExplorer, PlatformNetwork, NetworkContributionsIntro } from './NetworkPlatform.jsx';
import { hardwareBuilds, totalCost } from './hardwareCosts.js';
import { contributionNeeds } from './contributionNeeds.js';

const NAV = ['overview', 'intelligence', 'platform', 'knowledge', 'development', 'agents', 'contributions', 'history', 'operations', 'hardware', 'project', 'roadmap', 'documents', 'guidebook', 'tools', 'updates', 'access'];
const PRIMARY_NAV = ['overview', 'intelligence', 'platform', 'knowledge', 'development', 'agents', 'contributions'];
const SUBNAV = { intelligence: [['intelligence','Dashboard'],['history','History'],['operations','Operations']], platform: [['platform','Products & devices'],['hardware','Hardware specifications'],['tools','Software tools']], knowledge: [['knowledge','Knowledge home'],['documents','Documents'],['guidebook','Guidebook']], development: [['development','Development home'],['roadmap','Roadmap'],['updates','Updates']], overview: [['overview','Introduction'],['project','Project details']] };
const NAV_LABELS = { overview: 'Overview', intelligence:'Intelligence', platform:'Platform', knowledge:'Knowledge', development:'Development', agents:'Agents', documents: 'Docs', hardware: 'Devices', contributions: 'Contributions' };

function readWorkspaceView() {
  const value = new URLSearchParams(window.location.search).get('view');
  return value === 'dashboard' ? 'overview' : NAV.includes(value) ? value : 'overview';
}

function replaceWorkspaceView(view, { replace = false } = {}) {
  const url = new URL(window.location.href);
  url.searchParams.set('view', view);
  const method = replace ? 'replaceState' : 'pushState';
  window.history[method]({ view }, '', url);
}


function formatCount(value) {
  if (value === undefined || value === null || value === '') return '—';
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  return new Intl.NumberFormat('en-GB').format(n);
}

function stateTone(state) {
  const value = String(state || '').toLowerCase();
  if (['live', 'operational', 'available', 'active', 'ongoing', 'manage'].includes(value)) return 'good';
  if (['degraded', 'stabilise', 'prototype', 'active development', 'production + active development'].includes(value)) return 'warn';
  if (['offline', 'blocked', 'disabled'].includes(value)) return 'bad';
  return 'neutral';
}

function StatusPill({ children, state = children }) {
  return <span className={`future-pill future-pill--${stateTone(state)}`}>{children}</span>;
}

function SectionHeader({ eyebrow, title, copy, action }) {
  return (
    <header className="future-section-head">
      <div>
        <span className="future-eyebrow">{eyebrow}</span>
        <h2>{title}</h2>
        {copy ? <p>{copy}</p> : null}
      </div>
      {action || null}
    </header>
  );
}

function useOperationalData(hours = 24) {
  const sequence = useRef(0);
  const [snapshot, setSnapshot] = useState({
    status: null,
    counts: null,
    pipeline: null,
    loading: true,
    updatedAt: null,
    error: null,
  });

  const refresh = useCallback(async () => {
    const requestId = ++sequence.current;
    setSnapshot((previous) => ({ ...previous, loading: true }));
    const apiBase = resolveSiteApiBase();
    const requests = await Promise.allSettled([
      fetchJson(apiBase, `/api/v1/status?hours=${hours}`, undefined, 18000),
      fetchJson(apiBase, '/api/v1/play/counts', undefined, 9000),
      fetchJson(apiBase, '/api/v1/live/pipeline', undefined, 9000),
    ]);

    const [statusResult, countsResult, pipelineResult] = requests;
    let status = statusResult.status === 'fulfilled' ? statusResult.value : null;
    if (!status) {
      try { status = await fetchJson(apiBase, `/api/v1/status?hours=${hours}`, undefined, 18000); }
      catch { /* Report unavailable only after a retry. */ }
    }
    const counts = countsResult.status === 'fulfilled' ? countsResult.value : null;
    const pipeline = pipelineResult.status === 'fulfilled' ? pipelineResult.value : null;
    const errorCount = requests.filter((result) => result.status === 'rejected').length;

    if (requestId !== sequence.current) return;
    setSnapshot(previous => ({
      status: status?.window_hours === hours ? status : null,
      counts: counts || previous.counts,
      pipeline: pipeline || previous.pipeline,
      loading: false,
      updatedAt: status ? new Date() : previous.updatedAt,
      error: !status || status.window_hours !== hours
        ? `The ${hours === 24 ? '24-hour' : '7-day'} metrics could not be loaded. Please retry.`
        : errorCount ? 'Some secondary data sources are unavailable.' : null,
    }));
  }, [hours]);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      if (!cancelled) await refresh();
    };
    run();
    const timer = window.setInterval(run, 60_000);
    return () => {
      cancelled = true;
      sequence.current += 1;
      window.clearInterval(timer);
    };
  }, [refresh]);

  return { ...snapshot, refresh };
}

function useOverallData() {
  const [snapshot, setSnapshot] = useState({
    history: null, updatedAt: null, loading: true, error: null,
  });
  const refresh = useCallback(async () => {
    try {
      const data = await fetchJson(resolveSiteApiBase(), '/api/v1/futures/overall', undefined, 18000);
      if (data?.scope !== 'retained_intel_events' || !data?.intel_record) {
        throw new Error('Unexpected aggregate contract');
      }
      setSnapshot({ history: data, updatedAt: new Date(), loading: false, error: null });
    } catch {
      // Do not use demo metrics or silently present stale data as current.
      setSnapshot({ history: null, updatedAt: null, loading: false,
        error: 'Historical data temporarily unavailable. No demonstration values are substituted.' });
    }
  }, []);
  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, 300_000);
    return () => window.clearInterval(timer);
  }, [refresh]);
  return { ...snapshot, refresh };
}

function formatDateTime(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isFinite(date.getTime()) ? date.toLocaleString() : '—';
}

function LifetimeOverview({ ops, overall }) {
  const intel = overall.history?.intel_record || {};
  const geolocated = intel.positioned_events;
  const total = intel.total_events;
  const metrics = [
    ['Historical events', total, 'All retained Intel events, not confirmed incidents'],
    ['Geolocated events', geolocated, 'Records with stored coordinate fields'],
    ['Without coordinates', Number.isFinite(Number(total)) && Number.isFinite(Number(geolocated)) ? Number(total)-Number(geolocated) : null, 'Not a missing-case estimate'],
    ['Play archive', ops.counts?.total_count, 'Cumulative published archive records'],
  ];
  return <section className="future-section future-lifetime" aria-label="Overall historical totals">
    <SectionHeader eyebrow="overall / historical record" title="The cumulative evidence record."
      copy="All retained database records, with separate public archive totals. These populations measure different stages and cannot be added together." />
    <div className="future-lifetime-grid">
      {metrics.map(([label, value, note]) => <article key={label}><small>{label}</small><strong>{formatCount(value)}</strong><p>{note}</p></article>)}
    </div>
    <p className="future-data-provenance">Recorded history: {formatDateTime(intel.oldest_event_utc)} → {formatDateTime(intel.newest_event_utc)}.
      All-time means retained records, not data deleted before retention. {overall.error || ''}</p>
  </section>;
}

function HistoricalAnalytics({ ops, overall }) {
  const record = overall.history?.intel_record || {};
  const monthly = Array.isArray(record.monthly) ? record.monthly : [];
  const max = Math.max(1, ...monthly.map(row => Number(row.count)||0));
  return <>
    <section className="future-page-head">
      <span className="future-eyebrow">history / all retained data</span>
      <h1>What has SeaCommons recorded over time?</h1>
      <p>Longitudinal records calculated from the canonical SeaCommons database. Each month counts retained Intel events, not verified incidents or distress cases.</p>
    </section>
    <LifetimeOverview ops={ops} overall={overall} />
    <section className="future-section">
      <SectionHeader eyebrow="history / monthly breakdown" title="A traceable historical timeline."
        copy="Each bar represents the number of records in its calendar month. No extrapolation or example values." />
      {monthly.length ? <div className="future-history-chart" role="img" aria-label="Monthly retained Intel events">
        {monthly.map(({month,count}) => <div key={month} className="future-history-bar">
          <span title={month+': '+formatCount(count)} style={{height:(5+95*Number(count)/max)+'%'}} />
          <small>{month}</small><strong>{formatCount(count)}</strong>
        </div>)}
      </div> : <p className="future-inline-note">{overall.loading ? 'Loading historical observations…' : overall.error || 'No archived data returned.'}</p>}
    </section>
  </>;
}

function Operations({ ops }) {
  const status = ops.status;
  const sensors = status?.sensor_activity || {};
  const sourceRows = Array.isArray(ops.pipeline?.sources) ? ops.pipeline.sources : [];
  const families = [
    ['AIS positions', sensors.ais_fixes],
    ['Radio bursts', sensors.radio_bursts],
    ['Radio events', sensors.radio_events],
    ['Satellite observations', sensors.satellite_observations],
  ];
  return <>
    <section className="future-page-head">
      <span className="future-eyebrow">data operations / evidence quality</span>
      <h1>How reliably is SeaCommons working?</h1>
      <p>Operations shows what information the software has received, which processing steps completed and where sources may be delayed. It also documents known technical problems, earlier fixes and what still needs verification. A technical warning is not the same as a confirmed maritime incident.</p>
    </section>
    <div className="future-library-actions">
      <button type="button" onClick={ops.refresh}>refresh measurements ↗</button>
      <span className="future-data-provenance">24-hour measurements · generated {formatDateTime(status?.generated_at)} · {ops.error || 'canonical data feed'}</span>
    </div>
    <section className="future-section">
      <SectionHeader eyebrow="evidence pipeline / 24h" title="What the infrastructure has processed."
        copy="Observation, normalisation and corroboration stages are distinct. A technical signal is not a verified incident." />
      <PipelinePanel status={status} />
    </section>
    <section className="future-section">
      <SectionHeader eyebrow="data sources / 24h" title="Sensor and source coverage." />
      <div className="future-history-types">
        {families.map(([label,value]) => <article key={label}><span>{label}</span><strong>{formatCount(value)}</strong></article>)}
      </div>
      <SourceHealth pipeline={ops.pipeline} />
      {sourceRows.length === 0 && <p className="future-inline-note">Source states are unavailable; no status is inferred.</p>}
    </section>
    <OperationalRiskRegister />
  </>;
}

function OperationalRiskRegister() {
  const [priority, setPriority] = useState('all');
  const rows = operationalAudit.filter(item => priority === 'all' || item.priority === priority);
  return <section className="future-section future-risk-register">
    <SectionHeader eyebrow="engineering incident register / historical" title="Known failures, fixes and remaining verification."
      copy="Evidence-based engineering register from August–October 2026. These are historical findings and open verification tasks, not automatically confirmed live outages. Live health metrics appear above." />
    <div className="future-risk-filters" role="group" aria-label="Filter engineering issues">
      {['all','P0','P1','P2'].map(p => <button key={p} type="button" className={priority === p ? 'is-active' : ''} onClick={() => setPriority(p)}>{p === 'all' ? 'All issues' : p}</button>)}
    </div>
    <div className="future-risk-list">{rows.map(item => <details key={item.id} className="future-risk-item" defaultOpen={item.priority === 'P0'}>
      <summary><span className="future-risk-priority">{item.priority}</span><span><strong>{item.title}</strong><small>{item.area} · {item.since}</small></span><span className="future-risk-state">{item.state}</span></summary>
      <div className="future-risk-body"><p><b>Observed issue:</b> {item.symptom}</p><p><b>Work already done:</b> {item.fixes}</p><p><b>Required validation / next fix:</b> {item.next}</p></div>
    </details>)}</div>
    <p className="future-data-provenance">Audit snapshot: 13 Oct 2026. P0 = evidence/publication or recurring availability risk; P1 = functional reliability; P2 = coverage/release maturity. Statuses require runtime verification before closure.</p>
  </section>;
}

function Hardware() {
  const [phase, setPhase] = useState('all');
  const [quantity, setQuantity] = useState({});
  const rows = hardwareBuilds.filter(item => phase === 'all' || item.phase.startsWith(phase));
  const euro = value => `€${value.toLocaleString('it-IT')}`;
  const grandTotal = hardwareBuilds.reduce((sum,item) => sum + totalCost(item) * (quantity[item.id] ?? 1), 0);
  return <>
    <section className="future-page-head"><span className="future-eyebrow">hardware / procurement estimates / Oct 2026</span>
      <h1>How physical sensors could extend SeaCommons.</h1>
      <p>Sensors is a proposed network of coastal antennas, radio receivers, environmental stations and drifting buoys. These instruments could add direct observations to the existing software. Below you can explore equipment, estimated prices, quantities, recurring costs and practical limits. The proposals are not claims of installed stations.</p>
    </section>
    <section className="future-section"><SectionHeader eyebrow="procurement calculator" title="Network investment scenarios."
      copy="Editable unit counts. Planning estimates in EUR, not quotations. Hardware subtotal excludes VAT, shipping, field installation, certification and vessel hire." />
      <div className="future-hardware-total"><span>One of each configuration</span><strong>{euro(hardwareBuilds.reduce((sum,item)=>sum+totalCost(item),0))}</strong><span>Selected quantities</span><strong>{euro(grandTotal)}</strong></div>
      <div className="future-hardware-quantities">{hardwareBuilds.map(item=><label key={item.id}><span>{item.name}</span><input type="number" min="0" max="100" value={quantity[item.id] ?? 1} onChange={e=>setQuantity({...quantity,[item.id]:Math.min(100,Math.max(0,Number(e.target.value)||0))})}/><b>{euro(totalCost(item)*(quantity[item.id]??1))}</b></label>)}</div>
    </section>
    <section className="future-section"><SectionHeader eyebrow="open hardware roadmap" title="Sensors: component-level costs and technical constraints."
      copy="Real products are linked where a supplier reference was found; other rows are explicitly labeled planning allowances. Verify supplier availability, shipping and local taxes before purchasing." />
      <div className="future-risk-filters" role="group" aria-label="Hardware development phase">{['all','1','2','3'].map(p=><button key={p} type="button" className={phase===p?'is-active':''} onClick={()=>setPhase(p)}>{p==='all'?'All phases':`Phase ${p}`}</button>)}</div>
      <div className="future-hardware-grid">{rows.map(item=><article key={item.id} className="future-hardware-card future-hardware-cost-card">
        <small>{item.phase}</small><h3>{item.name}</h3><p>{item.purpose}</p>
        <div className="future-hardware-bom">{item.items.map(([name,count,unit,url,note],i)=><div key={i}><span>{url?<a href={url} target="_blank" rel="noreferrer">{name} ↗</a>:name}<small>{note}</small></span><span>{count} × {euro(unit)}</span><b>{euro(count*unit)}</b></div>)}</div>
        <div className="future-hardware-subtotal"><span>Equipment subtotal</span><strong>{euro(totalCost(item))}</strong></div>
        <p><b>Recurring operating costs</b>{item.recurring}</p><p className="future-hardware-caution"><b>Design and procurement note</b>{item.notes}</p>
      </article>)}</div>
    </section>
    <section className="future-section"><SectionHeader eyebrow="technical sequencing" title="Start with dependable receiving stations."
      copy="First validate one coastal AIS receiver, one radio decoder and resilient storage. Prototype a recoverable Drifter after station-health telemetry and legal/safety requirements are defined. Expand environmental and acoustic sensing only after calibration and maintenance procedures are proven." />
      <p className="future-inline-note">Price anchors: Raspberry Pi official 2026 pricing and RAKwireless GPS tracker listings. EUR component allowances are engineering budgets, not live retailer offers. V4 RTL-SDR has been discontinued, so receiver estimates use the V3 line.</p>
    </section>
  </>;
}

function Contributions() {
  const [filter, setFilter] = useState('all');
  const groups = [...new Set(contributionNeeds.map(item => item.group))];
  const visible = contributionNeeds.filter(item => filter === 'all' || item.group === filter).sort((a, b) => a.rank - b.rank);
  return <>
    <NetworkContributionsIntro />
    <section className="future-page-head"><span className="future-eyebrow">SeaCommons / resource requirements</span>
      <h1>Resources that help the network grow.</h1>
      <p>A resource register for shared nodes, operations and future deployments. Estimated costs describe practical requirements, not a funding campaign.</p>
    </section>
    <section className="future-section"><SectionHeader eyebrow="priority register" title="Keep the platform reliable first."
      copy="Our first priority is protecting the existing service and its history. New sensors and research integrations follow once storage, backup and continuous operation are under control." />
      <div className="future-risk-filters"><button type="button" className={filter === 'all' ? 'is-active' : ''} onClick={() => setFilter('all')}>All priorities</button>{groups.map(group => <button type="button" key={group} className={filter === group ? 'is-active' : ''} onClick={() => setFilter(group)}>{group}</button>)}</div>
      <div className="future-priority-list">{visible.map(item => <article className="future-priority-card" key={item.name}>
        <div className="future-priority-card__meta"><span>Priority {item.rank} · {item.urgency}</span><span>{item.group}</span></div>
        <h3>{item.name}</h3><p className="future-priority-card__reason">{item.plainReason}</p>
        <div className="future-priority-card__facts"><div><small>Planning cost</small><strong>{item.cost}</strong></div><div><small>What we need</small><span>{item.need}</span></div></div>
        <details><summary>Technical scope and current status</summary><p>{item.use}</p><p>{item.reference} · {item.readiness}</p></details>
      </article>)}</div>
      <p className="future-inline-note">Costs are indicative EUR allowances for planning, exclude tax, shipping, installation and labor unless stated. Oracle pricing and availability depend on the selected region, compute shape, usage and current tenancy. No procurement or partnership is implied.</p>
    </section>
    <section className="future-section"><SectionHeader eyebrow="responsible integration" title="Requirements before any system is connected."
      copy="Every external feed or physical device needs explicit permission, a designated operator, documented provenance, security boundaries, source health checks and publication safeguards. Receive-only radio work must respect applicable national law." />
    </section>
  </>;
}

function WorkstreamList({ project }) {
  return (
    <div className="future-workstreams">
      {project.workstreams.map((stream, index) => (
        <article key={stream.id}>
          <div className="future-workstreams__index">{String(index + 1).padStart(2, '0')}</div>
          <div>
            <div className="future-workstreams__title">
              <h4>{stream.name}</h4>
              <StatusPill state={stream.state}>{stream.state}</StatusPill>
            </div>
            <p>{stream.note}</p>
          </div>
        </article>
      ))}
    </div>
  );
}

function ProjectDetail({ project }) {
  if (!project) return null;
  return (
    <section className="future-project-detail">
      <header>
        <div>
          <span className="future-eyebrow">SeaCommons workspace</span>
          <h2>{project.name}</h2>
        </div>
        <StatusPill state={project.status}>{project.status}</StatusPill>
      </header>

      <p className="future-project-lead">{project.summary}</p>

      <div className="future-detail-grid">
        <div><span>current phase</span><strong>{project.phase}</strong></div>
        <div><span>workstreams</span><strong>{project.workstreams.length}</strong></div>
        <div><span>access</span><strong>identity via OIDC; resource grants pending</strong></div>
      </div>

      <div className="future-capabilities">
        <span className="future-eyebrow">capabilities / scope</span>
        <div>{project.capabilities.map((item) => <span key={item}>{item}</span>)}</div>
      </div>

      <div className="future-two-col future-two-col--wide">
        <section>
          <span className="future-eyebrow">development workstreams</span>
          <WorkstreamList project={project} />
        </section>
        <section>
          <span className="future-eyebrow">project documents</span>
          <div className="future-doc-list">
            {project.documents.map((doc) => (
              <div className="future-doc-row" key={doc.id}>
                <span>
                  <b>{doc.title}</b>
                  <small>{doc.kind} · {doc.visibility}</small>
                </span>
                <time>{doc.updated}</time>
              </div>
            ))}
          </div>
        </section>
      </div>
    </section>
  );
}

function OperationalStrip({ ops, period = '24h' }) {
  const status = ops.status;
  const counts = ops.counts;
  const pipeline = status?.pipeline || {};
  const serviceState = status?.status || (ops.loading ? 'connecting' : 'metrics unavailable');

  return (
    <section className="future-ops-strip" aria-label="SeaCommons operational status">
      <div>
        <span>system</span>
        <strong>{serviceState}</strong>
        <StatusPill state={serviceState}>{ops.loading ? 'connecting' : serviceState}</StatusPill>
      </div>
      <div>
        <span>Public archive · all time</span>
        <strong>{formatCount(counts?.total_count)}</strong>
        <small>{formatCount(counts?.humanitarian_count)} humanitarian · {formatCount(counts?.maritime_count)} maritime</small>
      </div>
      <div>
        <span>episodes · {period === '7d' ? '7 days' : '24 h'}</span>
        <strong>{formatCount(pipeline?.maritime_episodes)}</strong>
        <small>{formatCount(pipeline?.corroborated_episodes)} corroborated</small>
      </div>
      <div>
        <span>investigations · {period === '7d' ? '7 days' : '24 h'}</span>
        <strong>{formatCount(pipeline?.investigation_hypotheses)}</strong>
        <small>Signals under examination, not confirmed incidents</small>
      </div>
    </section>
  );
}

function PipelinePanel({ status }) {
  const pipeline = status?.pipeline || {};
  const sensors = status?.sensor_activity || {};
  const rows = [
    ['raw observations', pipeline.raw_observations],
    ['normalised events', pipeline.parsed_events],
    ['analysis outputs', pipeline.analysis_outputs],
    ['maritime episodes', pipeline.maritime_episodes],
    ['investigation hypotheses', pipeline.investigation_hypotheses],
    ['corroborated episodes', pipeline.corroborated_episodes],
  ];
  const sensorRows = [
    ['AIS fixes', sensors.ais_fixes],
    ['radio bursts', sensors.radio_bursts],
    ['radio events', sensors.radio_events],
    ['satellite observations', sensors.satellite_observations],
  ];

  return (
    <div className="future-metric-panels">
      <section className="future-metric-panel">
        <span className="future-eyebrow">evidence pipeline · 24 h</span>
        <div className="future-metric-list">
          {rows.map(([label, value]) => <div key={label}><span>{label}</span><strong>{formatCount(value)}</strong></div>)}
        </div>
      </section>
      <section className="future-metric-panel">
        <span className="future-eyebrow">sensor activity · 24 h</span>
        <div className="future-metric-list">
          {sensorRows.map(([label, value]) => <div key={label}><span>{label}</span><strong>{formatCount(value)}</strong></div>)}
        </div>
      </section>
    </div>
  );
}

function SourceHealth({ pipeline }) {
  const sources = Array.isArray(pipeline?.sources) ? pipeline.sources : [];
  const expected = [
    ['ais', 'AIS'],
    ['first_party', 'First-party'],
    ['partner', 'Partner'],
    ['public_feed', 'Public feeds'],
    ['radio', 'Radio'],
  ];
  const rows = expected.map(([family, label]) => {
    const source = sources.find((item) => item?.family === family);
    return { family, label, state: source?.state || (pipeline ? 'unknown' : 'unavailable'), mode: source?.mode };
  });

  return (
    <section className="future-source-health">
      <span className="future-eyebrow">acquisition families</span>
      <div>
        {rows.map((row) => (
          <article key={row.family}>
            <span>{row.label}</span>
            <div>
              {row.mode ? <small>{row.mode}</small> : null}
              <StatusPill state={row.state}>{row.state}</StatusPill>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function PlatformSummary({ ops, period }) {
  const windowLabel = period === '7d' ? '7 days' : '24 hours';
  const generated = ops.status?.generated_at || ops.counts?.generated_at;
  const stages = [
    { label: 'Observed', value: ops.status?.pipeline?.raw_observations, note: `raw envelopes / ${windowLabel}` },
    { label: 'Normalised', value: ops.status?.pipeline?.parsed_events, note: `events / ${windowLabel}` },
    { label: 'Analysed', value: ops.status?.pipeline?.derived_cues, note: `derived cues / ${windowLabel}` },
    { label: 'Corroborated', value: ops.status?.pipeline?.corroborated_episodes, note: `episodes / ${windowLabel}` },
  ];
  const products = [
    { label: 'Live', note: 'Active, privacy-filtered public cases', url: null },
    { label: 'Play', note: 'Historic public cases and timelines', url: null },
    { label: 'API', note: 'Typed contracts and service status', url: null },
    { label: 'Futures', note: 'Partner workspace and project knowledge', url: null },
  ];
  return <>
    <section className="future-section future-overview-story">
      <SectionHeader eyebrow="01 / project at a glance" title="How SeaCommons turns scattered signals into evidence."
        copy="SeaCommons links heterogeneous observations into traceable maritime investigations, while preserving uncertainty, source independence and the distinction between an observation and a verified finding." />
      <div className="future-narrative-grid">
        <article><small>scope</small><h3>Humanitarian OSINT</h3><p>Distress, SAR activity and humanitarian reporting under conservative privacy, provenance and location-precision controls.</p></article>
        <article><small>scope</small><h3>Maritime Intelligence</h3><p>AIS integrity, vessel behaviour, radio, environmental and satellite investigation context without presuming intent.</p></article>
        <article><small>method</small><h3>One evidence model</h3><p>Source observation → normalization → derived cue → episode → hypothesis → policy-governed public case.</p></article>
      </div>
    </section>
    {period !== 'overall' && <section className="future-section">
      <SectionHeader eyebrow="02 / measured activity" title="How incoming information becomes evidence."
        copy={`Values are from the selected ${windowLabel} window. The Play archive is cumulative and stays separate.`} />
      <div className="future-funnel-grid">
        {stages.map((stage, index) => <article key={stage.label}>
          <small>{String(index + 1).padStart(2, '0')} / {stage.label}</small>
          <strong>{formatCount(stage.value)}</strong>
          <span>{stage.note}</span>
        </article>)}
      </div>
      <p className="future-data-provenance">Source: canonical SeaCommons API /api/v1/status?hours={period === '7d' ? 168 : 24}. {generated ? 'Snapshot generated ' + new Date(generated).toLocaleString() + '.' : 'Waiting for timestamp.'} A derived cue is not a factual finding.</p>
    </section>}
    <section className="future-section">
      <SectionHeader eyebrow="03 / product ecology" title="The different parts of SeaCommons."
        copy="Each SeaCommons surface has a separate purpose and audience. Futures keeps you inside your authenticated partner workspace." />
      <div className="future-product-grid">
        {products.map((product) => {
          const content = <><small>SeaCommons / {product.label}</small><h3>{product.label}</h3><p>{product.note}</p><span>{product.url ? 'open surface ↗' : product.label === 'Futures' ? 'you are here' : 'reference only'}</span></>;
          return product.url
            ? <a key={product.label} href={product.url} target="_blank" rel="noreferrer">{content}</a>
            : <article key={product.label}>{content}</article>;
        })}
      </div>
    </section>
  </>;
}

function ApplicationPathways() {
  return (
    <section className="future-section future-pathways">
      <SectionHeader
        eyebrow="04 / applied research"
        title="Start at sea. Expand only where the evidence supports it."
        copy="A modular research approach for public-interest partners. The first pathway uses existing SeaCommons infrastructure; subsequent verticals are proposals, not live data products."
      />
      <section className="future-pathway-grid" aria-label="Application pathways and maturity">
        {verticalPathways.map((item, index) => (
          <article key={item.id} className={index === 0 ? 'is-operational' : ''}>
            <header>
              <span>{item.phase}</span>
              <StatusPill state={item.status}>{item.status}</StatusPill>
            </header>
            <h3>{item.title}</h3>
            <p>{item.detail}</p>
            <div className="future-pathway-meta">
              <small>Potential inputs</small>
              <span>{item.inputs.join(' · ')}</span>
            </div>
            <div className="future-pathway-meta">
              <small>Intended output</small>
              <span>{item.output}</span>
            </div>
          </article>
        ))}
      </section>
      <p className="future-data-provenance">Future pathways require a separate source assessment, data permissions, verified field methods and an implementation agreement. The platform does not currently measure their impact or outcomes.</p>
    </section>
  );
}

function PilotFramework() {
  return (
    <section className="future-section future-pilot">
      <SectionHeader eyebrow="05 / collaboration model" title="A bounded pilot, built to be evaluated."
        copy="Translate one concrete question into a reliable, inspectable deliverable rather than an undifferentiated dashboard." />
      <div className="future-pilot-steps">
        {pilotFramework.map((step) => (
          <article key={step.label}>
            <small>{step.label}</small>
            <p>{step.text}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

function Overview({ ops, overall, period, setPeriod, navigate, compact = false }) {
  return (
    <>
      <section className="future-hero">
        <span className="future-eyebrow">SeaCommons Futures / partner workspace</span>
        <h1>Understand what happens at sea, through evidence.</h1>
        <p>
          SeaCommons brings together maritime observations, evaluates their reliability and helps researchers understand complex events without confusing signals with verified facts.
        </p>
        <div className="future-hero__meta">
          <StatusPill state={ops.status?.status || 'unknown'}>{ops.status?.status || 'operational feed pending'}</StatusPill>
          <span>{ops.updatedAt ? `updated ${ops.updatedAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : 'connecting to operational contracts'}</span>
          <button onClick={ops.refresh}>refresh</button>
        </div>
        {ops.error ? <p className="future-inline-note">{ops.error} Static project information remains available.</p> : null}
      </section>

      {!compact && <MethodExplorer />}


      <section className="future-period-tabs" aria-label="Analytics time period">
        <div role="group" aria-label="Analytics time window">
          {[
            ['24h', '24 hours'], ['7d', '7 days'], ['overall', 'Overall'],
          ].map(([value, label]) => <button key={value} type="button" aria-pressed={period === value}
            className={period === value ? 'is-active' : ''} onClick={() => setPeriod(value)}>{label}</button>)}
        </div>
        <small>{period === 'overall' ? 'Complete retained history in the database, not every observation ever seen' : `Activity recorded in the last ${period === '7d' ? 'seven days' : '24 hours'}, not a count of confirmed incidents`}</small>
      </section>
      {period === 'overall' && <LifetimeOverview ops={ops} overall={overall} />}
      {period !== 'overall' && <OperationalStrip ops={ops} period={period} />}
      <PlatformSummary ops={ops} period={period} />
      <section className="future-section future-dashboard-quicklinks">
        <SectionHeader eyebrow="workspace priorities" title="Operational reliability and sensor expansion." />
        <div className="future-hardware-grid">
          <button type="button" onClick={() => navigate('operations')}><small>incident register / 10 areas</small><strong>Criticalities and unresolved fixes ↗</strong><span>Passenger vessels, storage pressure, AIS, PLAY, scheduler and publication confidence.</span></button>
          <button type="button" onClick={() => navigate('hardware')}><small>distributed infrastructure / 7 pathways</small><strong>Sensors: equipment and costs ↗</strong><span>AIS and radio antennas, drifters, hydrophones, coastal sensors, compute and field partners.</span></button>
        </div>
      </section>
      {!compact && <ApplicationPathways />}
      {!compact && <PilotFramework />}

      <section className="future-section">
        <SectionHeader
          eyebrow="SeaCommons"
          title="Current development work"
          copy="The workspace is scoped to SeaCommons only. Other Suez products and client projects live on their own surfaces."
        />
        <WorkstreamList project={seaCommonsProject} />
      </section>

      <section className="future-section">
        <SectionHeader
          eyebrow="SeaCommons / live state"
          title="Evidence operations"
          copy="These figures come from the same public-safe contracts used by SeaCommons itself, not a parallel analytics layer."
        />
        {period === 'overall' ? <p className="future-inline-note">Current source health appears below. Full-period Intel statistics are shown in Overall above; recent pipeline activity is not a lifetime total.</p> : <PipelinePanel status={ops.status} />}
        <SourceHealth pipeline={ops.pipeline} />
      </section>


    </>
  );
}

function Project() {
  return (
    <>
      <section className="future-page-head">
        <span className="future-eyebrow">SeaCommons project</span>
        <h1>What SeaCommons is building, and why.</h1>
        <p>
          This Futures domain is the private operational workspace for SeaCommons.
          Other Suez products and client work remain outside this workspace even when they share identity infrastructure.
        </p>
      </section>
      <ProjectDetail project={seaCommonsProject} />
    </>
  );
}

function Roadmap() {
  const lanes = [
    ['now', roadmap.now],
    ['next', roadmap.next],
    ['later', roadmap.later],
  ];

  return (
    <>
      <section className="future-page-head">
        <span className="future-eyebrow">development roadmap</span>
        <h1>What is being built, in what order, and why.</h1>
        <p>
          Roadmap items represent active engineering priorities and planned dependencies.
          They are not promises of completed capability.
        </p>
      </section>

      <section className="future-roadmap-board">
        {lanes.map(([label, items]) => (
          <div className="future-roadmap-lane" key={label}>
            <header><span>{label}</span><strong>{items.length}</strong></header>
            {items.map((item) => (
              <article key={item.project + item.title}>
                <div><small>{item.project}</small><StatusPill state={item.state}>{item.state}</StatusPill></div>
                <h3>{item.title}</h3>
                <p>{item.detail}</p>
              </article>
            ))}
          </div>
        ))}
      </section>

      <section className="future-section">
        <SectionHeader
          eyebrow="development needs"
          title="Where support compounds"
          copy="Operational needs are shown as project requirements, not as a grant-specific funding template."
        />
        <div className="future-support-grid">
          {supportAreas.map((item) => (
            <article key={item.area}>
              <StatusPill state={item.status}>{item.status}</StatusPill>
              <h3>{item.area}</h3>
              <p>{item.need}</p>
            </article>
          ))}
        </div>
      </section>
    </>
  );
}

function Documents() {
  const [query, setQuery] = useState('');
  const [group, setGroup] = useState('all');
  const [deckOpen, setDeckOpen] = useState(false);
  const [openDocument, setOpenDocument] = useState(null);
  useEffect(() => {
    if (deckOpen) window.requestAnimationFrame(() => document.getElementById('futures-deck-viewer')?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
  }, [deckOpen]);
  const [slideIndex, setSlideIndex] = useState(0);
  const groups = ['all', ...new Set(partnerDocuments.map((doc) => doc.group))];
  const filtered = partnerDocuments.filter((doc) => {
    const searchable = [doc.title, doc.source, doc.description, doc.kind].join(' ').toLowerCase();
    return (group === 'all' || doc.group === group) && searchable.includes(query.trim().toLowerCase());
  });
  const currentSlide = presentationSlides[slideIndex];

  return (
    <>
      <section className="future-page-head">
        <span className="future-eyebrow">SeaCommons / docs library</span>
        <h1>Documents, presentations and project knowledge.</h1>
        <p>This is the reading room for people learning about SeaCommons. Find presentations, project briefs, background research and technical references. A restricted label means a file is listed for context but cannot be downloaded without separate permission.</p>
      </section>

      <section className="future-library-intro">
        <div>
          <span className="future-eyebrow">featured / presentation</span>
          <h2>SeaCommons partner introduction</h2>
          <p>A concise nine-slide introduction: the maritime challenge, how evidence is evaluated, the SeaCommons products, current engineering limits and the proposed Sensors network.</p>
          <div className="future-library-actions">
            <button type="button" onClick={() => { setDeckOpen(true); setSlideIndex(0); }}>view presentation ↗</button>
            <a href="/SeaCommons_Futures_Introduction_2026.pdf" download="SeaCommons_Futures_Introduction_2026.pdf">download PDF ↓</a>
          </div>
        </div>
        <div className="future-library-cover" aria-label="SeaCommons presentation cover">
          <small>SEACOMMONS / 2026</small>
          <strong>From observation<br />to accountable<br />evidence.</strong>
          <span>Partner introduction / 9 slides</span>
        </div>
      </section>

      {deckOpen && <section id="futures-deck-viewer" className="future-deck-section" aria-label="SeaCommons partner presentation">
        <div className="future-deck-toolbar">
          <span>SeaCommons / presentation · {slideIndex + 1} / {presentationSlides.length}</span>
          <a href="/SeaCommons_Futures_Introduction_2026.pdf" download="SeaCommons_Futures_Introduction_2026.pdf">download PDF ↓</a>
          <button type="button" onClick={() => setDeckOpen(false)} aria-label="Close presentation">close ✕</button>
        </div>
        <article className="future-deck-slide">
          <small>{currentSlide.kicker} / {String(slideIndex + 1).padStart(2, '0')}</small>
          <h2>{currentSlide.title}</h2>
          <p>{currentSlide.body}</p>
          <ul>{currentSlide.points.map((point) => <li key={point}>{point}</li>)}</ul>
        </article>
        <div className="future-deck-controls">
          <button type="button" onClick={() => setSlideIndex((n) => Math.max(0, n - 1))} disabled={slideIndex === 0}>← previous</button>
          <span>Slide {slideIndex + 1} of {presentationSlides.length}</span>
          <button type="button" onClick={() => setSlideIndex((n) => Math.min(presentationSlides.length - 1, n + 1))} disabled={slideIndex === presentationSlides.length - 1}>next →</button>
        </div>
      </section>}

      <section className="future-section">
        <SectionHeader eyebrow="document register" title="Browse current project material."
          copy="Published materials open from their cited source. Restricted documents are not served by this catalogue and require an explicit resource grant." />
        <div className="future-library-filters">
          <label><span>search documents</span><input type="search" placeholder="Title, format or topic" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
          <label><span>category</span><select value={group} onChange={(event) => setGroup(event.target.value)}>
            {groups.map((item) => <option value={item} key={item}>{item}</option>)}
          </select></label>
          <span>{filtered.length} / {partnerDocuments.length} resources</span>
        </div>
        <section className="future-document-table" aria-label="SeaCommons project documents">
          <header><span>document</span><span>project</span><span>type</span><span>access</span><span>updated</span></header>
          {filtered.map((doc) => (
            <article key={doc.projectId + doc.id}>
              <div><strong>{doc.title}</strong><small>{doc.description || doc.source}</small>
                {doc.deck
                  ? <button className="future-doc-link" onClick={() => { setDeckOpen(true); setSlideIndex(0); }}>view slides ↗</button>
                  : doc.href ? <button type="button" className="future-doc-link" onClick={() => { setOpenDocument(doc); setDeckOpen(false); }}>read in Futures ↗</button> : <small>restricted / request access</small>}
              </div>
              <span>{doc.project}</span>
              <span>{doc.kind}</span>
              <StatusPill state={doc.visibility === 'restricted' ? 'warn' : 'active'}>{doc.visibility}</StatusPill>
              <time>{doc.updated}</time>
            </article>
          ))}
          {filtered.length === 0 && <p className="future-inline-note">No resource matches the selected filters.</p>}
        </section>
      </section>

      {openDocument && <section className="future-section future-embedded-document" aria-label="Document reader">
        <div className="future-deck-toolbar"><span>SEA COMMONS / FUTURES / DOCUMENTS</span><button type="button" onClick={() => setOpenDocument(null)}>close reader ✕</button></div>
        <h2>{openDocument.title}</h2><p>{openDocument.description}</p>
        <iframe title={openDocument.title} src={openDocument.href} loading="lazy" referrerPolicy="no-referrer" sandbox="allow-scripts allow-forms" />
        <p className="future-inline-note">Some publishers do not permit embedded viewing. If this source cannot display here, you can <a href={openDocument.href} target="_blank" rel="noreferrer">open the original source</a>.</p>
      </section>}
      <section className="future-library-intake">
        <div><span className="future-eyebrow">partner materials</span><h3>Request a reviewed document</h3>
          <p>Published reference materials are available above. For a partner brief or an unpublished resource, contact the programme team. Confidential materials are never uploaded to the public source repository. In-app uploads and permissioned downloads will be enabled only after verified private storage and server-side resource grants are in place.</p></div>
        <a href="mailto:republic@suezcanal.xyz?subject=SeaCommons%20document%20request">contact programme team ↗</a>
      </section>
    </>
  );
}

function Guidebook() {
  const [activeId, setActiveId] = useState(guidebook[0].id);
  const active = guidebook.find((item) => item.id === activeId) || guidebook[0];
  const groups = [...new Set(guidebook.map((item) => item.group))];

  return (
    <section className="future-guide">
      <aside>
        <span className="future-eyebrow">guidebook</span>
        {groups.map((group) => (
          <div className="future-guide__group" key={group}>
            <small>{group}</small>
            {guidebook.filter((item) => item.group === group).map((item) => (
              <button key={item.id} className={active.id === item.id ? 'is-active' : ''} onClick={() => setActiveId(item.id)}>
                {item.title}
              </button>
            ))}
          </div>
        ))}
      </aside>
      <article>
        <span className="future-eyebrow">living project knowledge</span>
        <h1>{active.title}</h1>
        <p className="future-guide__summary">{active.summary}</p>
        <hr />
        {active.body.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
        <div className="future-guide__footer">
          <span>native Futures document</span>
          <span>Technical documentation is available in the Documents section.</span>
        </div>
      </article>
    </section>
  );
}

function Tools() {
  return (
    <>
      <section className="future-page-head">
        <span className="future-eyebrow">tools</span>
        <h1>Surfaces you can open from this workspace.</h1>
        <p>
          This page only exposes SeaCommons surfaces. Other Suez products and tools are managed on their own domains
          and are not part of the SeaCommons workspace.
        </p>
      </section>

      <section className="future-tool-grid">
        {tools.map((tool) => {
          const inner = (
            <>
              <div><small>{tool.kind}</small><StatusPill state={tool.state}>{tool.state}</StatusPill></div>
              <h3>{tool.name}</h3>
              <p>{tool.description}</p>
              <span className="future-tool-grid__cta">open tool ↗</span>
            </>
          );
          return tool.href ? <a key={tool.id} href={tool.href} target="_blank" rel="noopener noreferrer">{inner}</a> : <article key={tool.id}>{inner}</article>;
        })}
      </section>
    </>
  );
}

function Updates() {
  return (
    <>
      <section className="future-page-head">
        <span className="future-eyebrow">updates</span>
        <h1>A readable development history.</h1>
        <p>Important changes are recorded as project events so partners can understand what changed without reading commit logs.</p>
      </section>
      <section className="future-update-list">
        {timeline.map((item) => (
          <article key={item.date + item.title}>
            <time>{item.date}</time>
            <div>
              <div><span>{item.project}</span><small>{item.kind}</small></div>
              <h3>{item.title}</h3>
              <p>{item.detail}</p>
            </div>
          </article>
        ))}
      </section>
    </>
  );
}

function Invitations() {
  const { token } = useAuth();
  const [form, setForm] = useState({ first_name: '', last_name: '', email: '', requested_role: 'viewer' });
  const [items, setItems] = useState([]);
  const [message, setMessage] = useState('');
  const headers = token ? { Authorization: `Bearer ${token}` } : {};
  const refresh = async () => {
    if (!token) return;
    try {
      const response = await fetch('/api/v1/futures/invitations', { headers });
      if (response.ok) setItems(await response.json());
      else setMessage(`Invitations API: HTTP ${response.status}`);
    } catch { setMessage('Invitations API is unavailable.'); }
  };
  useEffect(() => { refresh(); }, [token]);
  const submit = async (event) => {
    event.preventDefault(); setMessage('Saving invitation…');
    try {
      const response = await fetch('/api/v1/futures/invitations', {
        method: 'POST', headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || `HTTP ${response.status}`);
      setForm({ first_name: '', last_name: '', email: '', requested_role: 'viewer' });
      setMessage('Invitation saved for scheduled review.'); await refresh();
    } catch (error) { setMessage(`Not saved: ${error.message}`); }
  };
  return <section className="future-section future-invitations">
    <SectionHeader eyebrow="partner access" title="Invitations" copy="Propose a partner with their first name, last name and email. Requests are reviewed every six hours. No membership is granted automatically." />
    <form onSubmit={submit}>
      <label>First name<input required maxLength={100} value={form.first_name} onChange={e => setForm({ ...form, first_name: e.target.value })} /></label>
      <label>Last name<input required maxLength={100} value={form.last_name} onChange={e => setForm({ ...form, last_name: e.target.value })} /></label>
      <label>Email<input required type="email" maxLength={320} value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} /></label>
      <label>Access level<input value="Viewer · read only" readOnly aria-label="Requested access level" /></label>
      <button type="submit" disabled={!token}>Save Viewer invitation</button>
    </form>
    <p role="status">{message || (!token ? 'Sign in to propose an invitation.' : 'Only authenticated, authorized partners can propose invitations.')}</p>
    <div>{items.map(item => <article key={item.id}><strong>{item.first_name} {item.last_name}</strong> <span>{item.email} · {item.requested_role || 'viewer'}</span> <StatusPill state={item.status}>{item.status}</StatusPill></article>)}</div>
  </section>;
}

function Access({ user }) {
  const identity = user?.profile?.email || user?.profile?.preferred_username || user?.email || 'authorised administrator';
  return (
    <>
      <section className="future-page-head">
        <span className="future-eyebrow">access</span>
        <h1>Your account and workspace access.</h1>
        <p>
          This page shows which account you are using and how workspace permissions work. Signing in confirms your identity, but it does not automatically grant access to private investigations or documents. You can propose invitations below; every request is reviewed before any access can be granted.
        </p>
      </section>

      <section className="future-identity-card">
        <div><span>identity</span><strong>{identity}</strong></div>
        <div><span>role</span><strong>not asserted by frontend</strong></div>
        <div><span>session</span><strong>OIDC identity only</strong></div>
      </section>

      <section className="future-access-table">
        <header><span>workspace</span><span>level</span><span>scope</span><span>mode</span></header>
        {accessMatrix.map((row) => (
          <article key={row.system}>
            <strong>{row.system}</strong>
            <StatusPill state={row.level}>{row.level}</StatusPill>
            <span>{row.scope}</span>
            <small>{row.state}</small>
          </article>
        ))}
      </section>

      <Invitations />
      <section className="future-access-note">
        <span className="future-eyebrow">final permission hierarchy</span>
        <p>organisation → SeaCommons workspace → project / subproject → resource or tool</p>
        <p>A grant can stop at any level. Access to one document never implies access to the rest of the project.</p>
      </section>
    </>
  );
}

export default function FuturesApp() {
  const { user, signOut } = useAuth();
  const [period, setPeriod] = useState('overall');
  const [view, setView] = useState(() => readWorkspaceView());
  const [installPrompt, setInstallPrompt] = useState(null);
  const [installed, setInstalled] = useState(false);
  const [showInstallGuide, setShowInstallGuide] = useState(() => {
    if (typeof window === 'undefined') return false;
    const mobile = window.matchMedia('(max-width: 700px)').matches;
    const standalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
    return mobile && !standalone && window.localStorage.getItem('futures-pwa-guide-dismissed') !== 'yes';
  });
  const isIOS = typeof navigator !== 'undefined' && /iPad|iPhone|iPod/.test(navigator.userAgent);
  const dismissInstallGuide = () => {
    window.localStorage.setItem('futures-pwa-guide-dismissed', 'yes');
    setShowInstallGuide(false);
  };
  useEffect(() => {
    const handlePrompt = (event) => { event.preventDefault(); setInstallPrompt(event); };
    const handleInstalled = () => { setInstalled(true); setInstallPrompt(null); setShowInstallGuide(false); };
    window.addEventListener('beforeinstallprompt', handlePrompt);
    window.addEventListener('appinstalled', handleInstalled);
    return () => { window.removeEventListener('beforeinstallprompt', handlePrompt); window.removeEventListener('appinstalled', handleInstalled); };
  }, []);
  const installApp = async () => { if (!installPrompt) return; await installPrompt.prompt(); setInstallPrompt(null); };
  const ops = useOperationalData(view === 'operations' ? 24 : period === '7d' ? 168 : 24);
  const overall = useOverallData();

  useEffect(() => {
    replaceWorkspaceView(view, { replace: true });

    const handlePopState = () => setView(readWorkspaceView());
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  const navigate = (nextView) => {
    if (!NAV.includes(nextView) || nextView === view) return;
    setView(nextView);
    replaceWorkspaceView(nextView);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  return (
    <div className="future-app">
      <aside className="future-sidebar">
        <button type="button" className="future-brand" onClick={() => navigate('overview')} aria-label="Futures dashboard">
          <i /><span>SEA<br />COMMONS</span>
        </button>
        <div className="future-product"><span>futures</span><small>partner workspace</small></div>
        <button type="button" className="future-mobile-account" onClick={() => navigate('access')} aria-label="Open account" aria-current={view === 'access' ? 'page' : undefined}><span aria-hidden="true">◎</span> Account</button>
        <nav aria-label="Futures">
          {PRIMARY_NAV.map((item) => (
            <button key={item} className={view === item ? 'is-active' : ''} onClick={() => navigate(item)}>
              <span>{NAV_LABELS[item] || item}</span><i>↗</i>
            </button>
          ))}
        </nav>
        {installPrompt && !installed && <button type="button" className="future-install-button" onClick={installApp}>install app ↓</button>}
        <div className="future-sidebar__base">
          <span>OIDC connected</span>
          <button onClick={() => signOut?.()}>sign out</button>
        </div>
      </aside>

      <main className="future-main">
        <header className="future-topbar">
          <div><span>SeaCommons / Futures</span><b>{NAV_LABELS[view] || view}</b></div>
          <div className="future-topbar__links"><span>Secure partner workspace</span><button type="button" className="future-topbar-logo" onClick={() => navigate('overview')} aria-label="SeaCommons Futures home"><i aria-hidden="true" /><span>SEA<br />COMMONS</span></button></div>
        </header>

        <div className="future-content">
          {Object.entries(SUBNAV).some(([,items])=>items.some(([id])=>id===view)) && <nav className="future-subnav" aria-label="Section navigation">{(Object.entries(SUBNAV).find(([,items])=>items.some(([id])=>id===view))?.[1] || []).map(([id,label])=><button type="button" key={id} className={id===view?'is-active':''} onClick={()=>navigate(id)}>{label}</button>)}</nav>}
          {view === 'intelligence' && <><section className="future-page-head"><span className="future-eyebrow">Intelligence / evidence and coverage</span><h1>What the system is recording.</h1><p>Explore current windows, retained history, data coverage and operational health. Values remain linked to their sources and do not represent verified incidents by default.</p></section><Overview ops={ops} overall={overall} period={period} setPeriod={setPeriod} navigate={navigate} compact /></>}
          {view === 'platform' && <PlatformNetwork />}
          {view === 'knowledge' && <><section className="future-page-head"><span className="future-eyebrow">Knowledge</span><h1>Learn, review and share.</h1><p>Technical references, practical guides and partner-ready documents in one place.</p></section><Documents /></>}
          {view === 'development' && <Roadmap />}
          {view === 'agents' && <><section className="future-page-head"><span className="future-eyebrow">Agents / scheduled workflows</span><h1>Work that can be verified.</h1><p>Scheduled research and engineering tasks will show their next run, execution history, reports and linked code changes when a trusted scheduler feed is connected. No demonstration runs are presented as real.</p></section><section className="future-section"><SectionHeader eyebrow="scheduler status" title="Waiting for a verified execution feed" copy="Task metadata and execution results will be read from the scheduler, not inferred from the roadmap." /></section></>}
          {view === 'overview' && <Overview ops={ops} overall={overall} period={period} setPeriod={setPeriod} navigate={navigate} />}
          {view === 'history' && <HistoricalAnalytics ops={ops} overall={overall} />}
          {view === 'operations' && <Operations ops={ops} />}
          {view === 'hardware' && <Hardware />}
          {view === 'contributions' && <Contributions />}
          {view === 'project' && <Project />}
          {view === 'roadmap' && <Roadmap />}
          {view === 'documents' && <Documents />}
          {view === 'guidebook' && <Guidebook />}
          {view === 'tools' && <Tools />}
          {view === 'updates' && <Updates />}
          {view === 'access' && <Access user={user} />}
        </div>
      </main>
      {showInstallGuide && !installed && <div className="future-pwa-overlay" role="presentation">
        <section className="future-pwa-dialog" role="dialog" aria-modal="true" aria-labelledby="future-pwa-title">
          <div className="future-pwa-heading"><small>FUTURES / MOBILE APP</small><button type="button" onClick={dismissInstallGuide} aria-label="Close installation guide">✕</button></div>
          <div className="future-pwa-symbol" aria-hidden="true">◈</div>
          <h2 id="future-pwa-title">Take Futures with you.</h2>
          <p>Install SeaCommons Futures on your Home Screen for an app-like experience with full-screen navigation and quick access to your workspace.</p>
          {isIOS ? <ol><li>Open this page in <b>Safari</b>.</li><li>Tap <b>Share</b> (square with an upward arrow).</li><li>Select <b>Add to Home Screen</b>, then tap <b>Add</b>.</li></ol> : <ol><li>Open this page in <b>Chrome</b>.</li><li>Open the browser menu and select <b>Install app</b> or <b>Add to Home screen</b>.</li><li>Confirm installation.</li></ol>}
          {installPrompt && !isIOS && <button type="button" className="future-pwa-primary" onClick={() => { installApp(); dismissInstallGuide(); }}>Install Futures</button>}
          <button type="button" className="future-pwa-secondary" onClick={dismissInstallGuide}>Continue in browser</button>
          <small>You can always install it later from your browser menu.</small>
        </section>
      </div>}
      <nav className="future-mobile-nav" aria-label="Mobile app navigation">
        {['overview','intelligence','platform','agents','contributions'].map((item) => (
          <button type="button" key={item} className={view === item ? 'is-active' : ''} onClick={() => navigate(item)}>
            <span className="future-mobile-nav-icon" aria-hidden="true">{{overview:'◈',intelligence:'⌁',platform:'◉',agents:'◇',contributions:'▤',access:'◎'}[item]}</span>
            <span>{({overview:'Overview',intelligence:'Data',platform:'Platform',agents:'Agents',contributions:'Network',access:'Account'})[item]}</span>
          </button>
        ))}
      </nav>
    </div>
  );
}
