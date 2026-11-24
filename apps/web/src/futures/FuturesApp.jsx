import {L,useT,useLocale} from './locale.jsx';
import KnowledgeLibrary from './KnowledgeLibrary.jsx';
import DeveloperGuide from '../docs/DeveloperGuide.jsx';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import './contributions-store.css';
import StrategyWorkspace from './StrategyWorkspace.jsx';
import FuturesOverview from './Overview.jsx';
import GlossaryText from './GlossaryText.jsx';
import KeyFigures from './KeyFigures.jsx';
import AgenticJournal from './AgenticJournal.jsx';
import {FuturesLocale} from './locale.jsx';
import journal from './strategyJournal.json';
import { retainedEvidence } from './retainedEvidence.js';
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
import IntelligenceDashboard from './IntelligenceDashboard.jsx';
import AisCrossCheck from './AisCrossCheck.jsx';
import { hardwareBuilds, totalCost } from './hardwareCosts.js';
import { contributionNeeds } from './contributionNeeds.js';

const NAV = ['overview', 'intelligence', 'intel-measures', 'intel-sources', 'intel-quality', 'intel-sensors', 'intel-activity', 'platform', 'knowledge', 'development', 'agents', 'contributions', 'history', 'operations', 'ais-check', 'hardware', 'project', 'roadmap', 'documents', 'guidebook', 'tools', 'updates', 'access'];
const PRIMARY_NAV = ['overview', 'intelligence', 'platform', 'knowledge', 'development', 'agents', 'contributions'];
const SUBNAV = { intelligence: [['intelligence','Comparison'],['intel-measures','Measurements'],['intel-sources','Sources'],['intel-quality','Quality'],['intel-sensors','Research domains'],['intel-activity','Acquisition'],['history','Timeline'],['operations','Operations'],['ais-check','AIS cross-check']], platform: [['platform','Products & devices'],['hardware','Hardware specifications'],['tools','Software tools']], knowledge: [['knowledge','Dossiers'],['documents','Document register'],['guidebook','Guidebook']], development: [['development','Development home'],['roadmap','Roadmap'],['updates','Updates']], overview: [['overview','Project overview'],['project','Technical reference']] };
const NAV_LABELS = {history:'Timeline',operations:'Operations',project:'Project details',roadmap:'Roadmap',guidebook:'Guidebook',tools:'Software tools',updates:'Updates',access:'Account and access','intel-measures':'Measurements','intel-sources':'Sources','intel-quality':'Quality','intel-sensors':'Research domains','intel-activity':'Acquisition', overview: 'Overview', intelligence:'Intelligence', 'ais-check':'AIS cross-check', platform:'Platform', knowledge:'Knowledge', development:'Development', agents:'Agents', documents: 'Docs', hardware: 'Devices', contributions: 'Contributions' };

const IT_NAV={'intel-measures':'Misurazioni','intel-sources':'Fonti','intel-quality':'Qualità','intel-sensors':'Domini e sensori','intel-activity':'Acquisizione',overview:'Il progetto',intelligence:'Intelligence',platform:'Piattaforma',knowledge:'Documentazione',development:'Sviluppo',agents:'Agenti',contributions:'Contributi',history:'Cronologia',operations:'Operazioni','ais-check':'Verifica AIS',hardware:'Dispositivi',project:'Approfondimento tecnico',roadmap:'Piano di sviluppo',documents:'Documenti',guidebook:'Guida',tools:'Strumenti',updates:'Aggiornamenti',access:'Account'};
function LanguageSwitch({lang,setLang}){return <div className="future-language-switch" role="group" aria-label="Language / Lingua">{['it','en'].map(l=><button type="button" key={l} aria-pressed={lang===l} onClick={()=>setLang(l)}><L>{l.toUpperCase()}</L></button>)}</div>}
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
  if (['warn','degraded', 'stabilise', 'prototype', 'active development', 'production + active development'].includes(value)) return 'warn';
  if (['bad','offline', 'blocked', 'disabled'].includes(value)) return 'bad';
  if (['planned','later','proposed','research','partial'].includes(value)) return 'plan';
  return 'neutral';
}

function StatusPill({ children, state = children }) {
  return <span className={`future-pill future-pill--${stateTone(state)}`}><L>{children}</L></span>;
}

function SectionHeader({ eyebrow, title, copy, action }) {
  return (
    <header className="future-section-head">
      <div>
        <span className="future-eyebrow"><L>{eyebrow}</L></span>
        <h2><L>{title}</L></h2>
        {copy ? <p><L>{copy}</L></p> : null}
      </div>
      <L>{action || null}</L>
    </header>
  );
}

function AgentTaskDashboard() {
 const [state,setState]=useState({loading:true,data:null,error:''});
 const reload=useCallback(async()=>{
  setState(s=>({...s,loading:true,error:''}));
  try {
   const data=await fetchJson(resolveSiteApiBase(),'/api/v1/operator/ingestion/scheduled-tasks',undefined,18000);
   setState({loading:false,data,error:''});
  } catch {
   setState({loading:false,data:null,error:'Could not load the protected scheduler snapshot.'});
  }
 },[]);
 useEffect(()=>{reload();},[reload]);
 const tasks=state.data?.tasks||[];
 const [taskFilter,setTaskFilter]=useState('all');
 const filteredTasks=tasks.filter(t=>taskFilter==='all'||(taskFilter==='enabled'?t.enabled===true:t.enabled===false));
 const syncedAt=state.data?.synced_at ? Date.parse(state.data.synced_at) : NaN;
 const stale=Number.isFinite(syncedAt)&&Date.now()-syncedAt>24*60*60*1000;
 return <><section className="future-page-head"><span className="future-eyebrow"><L>Agents / scheduled workflows</L></span><h1><L>Scheduled workflows</L></h1><p><L>Verified SeaCommons tasks from ChatGPT. This workspace shows a protected read-only snapshot, not a live scheduler connection.</L></p></section>
 <KeyFigures items={[{title:"Registered workflows",value:state.data?tasks.length:null,detail:"Tasks in the imported scheduler snapshot."},{title:"Enabled",value:state.data?tasks.filter(t=>t.enabled===true).length:null,detail:"Enabled in the snapshot; execution is not confirmed."},{title:"Paused",value:state.data?tasks.filter(t=>t.enabled===false).length:null,detail:"Paused in the snapshot."}]}/>
 <section className="future-section" aria-busy={state.loading}><div className="future-intelligence-freshness"><span><L>{state.loading?'Loading tasks…':state.error||('ChatGPT Tasks · '+tasks.length+' registered')}</L></span><small><L>{state.data?.synced_at?'Snapshot: '+new Date(state.data.synced_at).toLocaleString():'No verified snapshot'}</L></small><button type="button" disabled={state.loading} onClick={reload}><L>Refresh</L></button></div>
 <div className="future-risk-filters" role="group" aria-label="Filter scheduled workflows">{[['all','All'],['enabled','Enabled in snapshot'],['paused','Paused in snapshot']].map(([id,label])=><button type="button" key={id} aria-pressed={taskFilter===id} className={taskFilter===id?'is-active':''} onClick={()=>setTaskFilter(id)}><L>{label}</L></button>)}</div>
 {state.loading?<p role="status"><L>Loading scheduled tasks…</L></p>:tasks.length?<div className="future-agent-grid">{filteredTasks.map((task,i)=><article className="future-agent-card" key={task.title||i}><StatusPill state={task.enabled?'active':'planned'}>{task.enabled?'Enabled in snapshot':'Paused in snapshot'}</StatusPill><h3><L>{task.title}</L></h3><p><L>{task.cadence||'Cadence unavailable'}</L> · <L>{task.timezone||'Time zone unavailable'}</L></p><small><L>Last execution: </L><L>{task.last_run?new Date(task.last_run).toLocaleString():'Not reported'}</L></small><small><L>Snapshot status: </L><L>{task.status||'Imported'}</L></small></article>)}</div>:<p><L>{state.error||'No synchronized SeaCommons tasks are available. This is not evidence that all ChatGPT tasks have stopped.'}</L></p>}
 {stale&&<p role="status" className="future-factual-note"><L>Snapshot older than 24 hours. ENABLED describes the last imported state, not a live check of this task.</L></p>}
 <p className="future-inline-note"><L>Tasks are managed in ChatGPT. Changes to cadence, activation or notifications do not sync automatically to this read-only snapshot.</L></p>
 {tasks.length>0&&filteredTasks.length===0&&<p role="status"><L>No workflows match this filter.</L></p>}
 </section></>;
}
function AgentsWorkspace({lang}){
 const [section,setSection]=useState('journal');
 const tr=(it,en)=>lang==='it'?it:en;
 return <><nav className="futures-switcher agentic-view-switch" aria-label={tr('Sezioni agenti','Agent sections')}>{[['journal',tr('Attività e aggiornamenti','Activity and updates')],['scheduler',tr('Workflow programmati','Scheduled workflows')]].map(([id,label])=><button key={id} type="button" aria-pressed={section===id} onClick={()=>setSection(id)}><L>{label}</L></button>)}</nav>{section==='journal'?<AgenticJournal lang={lang} showRuns/>:<AgentTaskDashboard/>}</>;
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
    setSnapshot((previous) => ({ ...previous, loading: true, status: previous.status?.window_hours === hours ? previous.status : null }));
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
      counts,
      pipeline,
      loading: false,
      updatedAt: status?.window_hours === hours ? new Date() : null,
      error: !status || status.window_hours !== hours
        ? `The ${hours === 24 ? '24-hour' : '7-day'} metrics could not be loaded. Please retry.`
        : errorCount ? 'Some secondary data sources are unavailable.' : null,
    }));
  }, [hours]);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      if (!cancelled && document.visibilityState !== 'hidden') await refresh();
    };
    run();
    const onVisibility = () => {
      if (document.visibilityState === 'visible') run();
    };
    document.addEventListener('visibilitychange', onVisibility);
    const timer = window.setInterval(run, 60_000);
    return () => {
      cancelled = true;
      sequence.current += 1;
      document.removeEventListener('visibilitychange', onVisibility);
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
      if (!retainedEvidence(data)) {
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
    const run = () => {
      if (document.visibilityState !== 'hidden') refresh();
    };
    run();
    const onVisibility = () => {
      if (document.visibilityState === 'visible') run();
    };
    document.addEventListener('visibilitychange', onVisibility);
    const timer = window.setInterval(run, 300_000);
    return () => {
      document.removeEventListener('visibilitychange', onVisibility);
      window.clearInterval(timer);
    };
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
  const validated = retainedEvidence(overall.history);
  const geolocated = validated?.positioned ?? null;
  const total = validated?.total ?? null;
  const metrics = [
    ['Historical events', total, 'All retained Intel events, not confirmed incidents'],
    ['Geolocated events', geolocated, 'Records with stored coordinate fields'],
    ['Without coordinates', validated ? total-geolocated : null, 'Not a missing-case estimate'],
    ['Play archive', ops.counts?.total_count, 'Cumulative published archive records'],
  ];
  return <section className="future-section future-lifetime" aria-label="Overall historical totals">
    <SectionHeader eyebrow="overall / historical record" title="The cumulative evidence record."
      copy="All retained database records, with separate public archive totals. These populations measure different stages and cannot be added together." />
    <div className="future-lifetime-grid">
      {metrics.map(([label, value, note]) => <article key={label}><small><L>{label}</L></small><strong><L>{formatCount(value)}</L></strong><p><L>{note}</L></p></article>)}
    </div>
    <div className="future-data-provenance">
      <p><b><L>SeaCommons collection:</L></b> <L>{intel.first_ingested_at ? formatDateTime(intel.first_ingested_at) + ' → ' + formatDateTime(intel.last_ingested_at) : 'Collection start not yet available from the API.'}</L></p>
      <p><b><L>Historical dates contained in the sources:</L></b> <L>{formatDateTime(intel.oldest_event_utc)}</L> → <L>{formatDateTime(intel.newest_event_utc)}</L><L>. Source events may predate SeaCommons; they do not indicate when the software began operating.</L></p>
      <p><L>All-time means records currently retained in the database. </L><L>{validated ? 'Inventory generated '+formatDateTime(validated.generatedAt)+'.' : 'Verified history is unavailable.'}</L> <L>{overall.error || ''}</L></p>
    </div>
  </section>;
}

function HistoricalAnalytics({ overall }) {
  // The event's timestamp can describe a historical ship or report years
  // before SeaCommons existed. Only canonical ingestion (created_at) is a
  // measurement of SeaCommons collection activity.
  const productStart = '2026-02';
  const record = overall.history?.intel_record || {};
  const monthly = (Array.isArray(record.ingested_monthly) ? record.ingested_monthly : [])
    .filter(row => /^\d{4}-\d{2}$/.test(String(row.month)) && row.month >= productStart
      && Number.isSafeInteger(Number(row.count)) && Number(row.count) >= 0);
  const max = Math.max(1, ...monthly.map(row => Number(row.count)));
  const first = monthly[0]?.month || '';
  const last = monthly[monthly.length-1]?.month || '';
  return <>
    <section className="future-page-head">
      <span className="future-eyebrow"><L>Intelligence / collection timeline</L></span>
      <h1><L>Collection timeline</L></h1>
      <p><L>Monthly volumes from records actually ingested by SeaCommons, not the historical dates described inside them. The view is scoped to the project period beginning in 2026, without repeating the Overall dashboard.</L></p>
    </section>
    <section className="future-section" aria-label="Monthly SeaCommons collection timeline">
      <SectionHeader eyebrow="collection / ingestion time" title="Monthly collected records"
        copy="Each month shows retained normalized Intel records by database creation date. Backfills can increase a month’s count; deletion or retention can reduce it. These are not incident counts." />
      {first && <p className="future-data-provenance"><L>Recorded months: </L><L>{first}</L> to <L>{last}</L><L>. Earliest retained ingestion: </L><L>{formatDateTime(record.first_ingested_at)}</L><L>. Snapshot: </L><L>{formatDateTime(overall.history?.generated_at)}</L>.</p>}
      {monthly.length ? <div className="future-history-chart future-collection-timeline" role="img" aria-label="Monthly SeaCommons ingestion volume">
        {monthly.map(({month,count})=><div key={month} className="future-history-bar">
          <span title={month+': '+formatCount(count)+' records'} style={{height:(5+95*Number(count)/max)+'%'}}/>
          <small><L>{new Date(month+'-01T00:00:00Z').toLocaleDateString('en-GB',{month:'short',year:'numeric',timeZone:'UTC'})}</L></small>
          <strong><L>{formatCount(count)}</L></strong>
        </div>)}
      </div> : <p className="future-inline-note"><L>{overall.loading?'Loading collection timeline…':overall.error||'No retained ingestion-month records returned for the SeaCommons project period.'}</L></p>}
      <p className="future-data-provenance"><L>The start boundary is an editorial project-era filter (February 2026), not a claim that sensors or ingestion were live that month. Months with no returned records are not filled with invented zeroes. Source-event chronology may reach earlier years and is intentionally excluded.</L></p>
    </section>
  </>;
}

function ViewTabs({items,selected,onChange}){const t=useT();return <nav className="futures-switcher local-section-tabs" aria-label={t("Section navigation")}>{items.map(([id,label])=><button key={id} type="button" aria-pressed={selected===id} onClick={()=>onChange(id)}>{t(label)}</button>)}</nav>}
function Operations({ ops }) {
  const [tab,setTab]=useState("monitor");
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
      <span className="future-eyebrow"><L>data operations / evidence quality</L></span>
      <h1><L>Service reliability</L></h1>
      <p><L>Check whether SeaCommons is receiving information and working as expected. The page explains delays, known problems and what still needs to be checked. A service problem is not a maritime incident.</L></p>
    </section>
    <ViewTabs items={[["monitor","Monitoring"],["sources","Sources"],["risks","Risk register"]]} selected={tab} onChange={setTab}/>
    {tab==="monitor"&&<>
    <div className="future-library-actions">
      <button type="button" onClick={ops.refresh}><L>refresh measurements ↗</L></button>
      <span className="future-data-provenance"><L>24-hour measurements · generated </L><L>{formatDateTime(status?.generated_at)}</L> · <L>{ops.error || 'canonical data feed'}</L></span>
    </div>
    <section className="future-section">
      <SectionHeader eyebrow="evidence pipeline / 24h" title="Evidence processing"
        copy="Observation, normalisation and corroboration stages are distinct. A technical signal is not a verified incident." />
      <PipelinePanel status={status} />
    </section>
    </>}
    {tab==="sources"&&<section className="future-section">
      <SectionHeader eyebrow="data sources / 24h" title="Sensor and source coverage" />
      <div className="future-history-types">
        {families.map(([label,value]) => <article key={label}><span><L>{label}</L></span><strong><L>{formatCount(value)}</L></strong></article>)}
      </div>
      <SourceHealth pipeline={ops.pipeline} />
      {sourceRows.length === 0 && <p className="future-inline-note"><L>Source states are unavailable; no status is inferred.</L></p>}
    </section>}
    {tab==="risks"&&<OperationalRiskRegister />}
  </>;
}

function OperationalRiskRegister() {
  const [priority, setPriority] = useState('all');
  const rows = operationalAudit.filter(item => priority === 'all' || item.priority === priority);
  return <section className="future-section future-risk-register">
    <SectionHeader eyebrow="Operations / continuous improvement" title="Fine-tuning"
      copy="Technical issues, improvements and validation. Review earlier fixes and unresolved checks by priority. These are historical findings and open verification tasks, not automatically confirmed live outages. Live source health appears above." />
    <div className="future-risk-filters" role="group" aria-label="Filter engineering issues">
      {['all','P0','P1','P2'].map(p => <button key={p} type="button" className={priority === p ? 'is-active' : ''} onClick={() => setPriority(p)}><L>{p === 'all' ? 'All issues' : p}</L></button>)}
    </div>
    <KeyFigures items={[{title:"Audit entries",value:operationalAudit.length,detail:"Historical register and pending checks."},{title:"P0 entries",value:operationalAudit.filter(i=>i.priority==="P0").length,detail:"Highest-priority audit items, not necessarily current outages."},{title:"Visible entries",value:rows.length,detail:"Matching the selected priority."}]}/><div className="future-risk-list">{rows.map(item => <details key={item.id} className="future-risk-item" >
      <summary><span className="future-risk-priority"><L>{item.priority}</L></span><span><strong><L>{item.title}</L></strong><small><L>{item.area}</L> · <L>{item.since}</L></small></span><StatusPill state="warn">{item.state}</StatusPill></summary>
      <div className="future-risk-body"><p><b><L>Observed issue:</L></b> <L>{item.symptom}</L></p><p><b><L>Work already done:</L></b> <L>{item.fixes}</L></p><p><b><L>Required validation / next fix:</L></b> <L>{item.next}</L></p></div>
    </details>)}</div>
    <p className="future-data-provenance"><L>Audit snapshot: 13 Oct 2026. P0 = evidence/publication or recurring availability risk; P1 = functional reliability; P2 = coverage/release maturity. Statuses require runtime verification before closure.</L></p>
  </section>;
}

function Hardware() {
  const [tab,setTab]=useState("catalog");
  const lang=useLocale();
  const [phase, setPhase] = useState('all');
  const [quantity, setQuantity] = useState({});
  const rows = hardwareBuilds.filter(item => phase === 'all' || item.phase.startsWith(phase));
  const euro = value => `€${value.toLocaleString(lang==='it'?'it-IT':'en-GB')}`;
  const grandTotal = hardwareBuilds.reduce((sum,item) => sum + totalCost(item) * (quantity[item.id] ?? 1), 0);
  return <>
    <section className="future-page-head"><span className="future-eyebrow"><L>hardware / procurement estimates / Oct 2026</L></span>
      <h1><L>Hardware specifications</L></h1>
      <p><L>Sensors is a proposed network of coastal antennas, radio receivers, environmental stations and drifting buoys. These instruments could add direct observations to the existing software. Below you can explore equipment, estimated prices, quantities, recurring costs and practical limits. The proposals are not claims of installed stations.</L></p>
    </section>
    <ViewTabs items={[["catalog","Equipment catalogue"],["budget","Budget calculator"],["validation","Field validation"]]} selected={tab} onChange={setTab}/>
    {tab==="budget"&&<section className="future-section"><SectionHeader eyebrow="procurement calculator" title="Equipment budget calculator"
      copy="Editable unit counts. Planning estimates in EUR, not quotations. Hardware subtotal excludes VAT, shipping, field installation, certification and vessel hire." />
      <KeyFigures items={[{title:"Selected equipment budget",value:euro(grandTotal),detail:"Estimated equipment subtotal for chosen quantities."},{title:"Reference budget",value:euro(hardwareBuilds.reduce((sum,item)=>sum+totalCost(item),0)),detail:"One of each configuration; not a funding request."},{title:"Configurations",value:hardwareBuilds.length,detail:"Proposed equipment designs."}]}/>
      <div className="future-hardware-quantities">{hardwareBuilds.map(item=><label key={item.id}><span><L>{item.name}</L></span><input type="number" min="0" max="100" value={quantity[item.id] ?? 1} onChange={e=>setQuantity({...quantity,[item.id]:Math.min(100,Math.max(0,Number(e.target.value)||0))})}/><b><L>{euro(totalCost(item)*(quantity[item.id]??1))}</L></b></label>)}</div>
    </section>}
    {tab==="catalog"&&<section className="future-section"><SectionHeader eyebrow="open hardware roadmap" title="Equipment and component costs"
      copy="Real products are linked where a supplier reference was found; other rows are explicitly labeled planning allowances. Verify supplier availability, shipping and local taxes before purchasing." />
      <div className="future-risk-filters" role="group" aria-label="Hardware development phase">{['all','1','2','3'].map(p=><button key={p} type="button" className={phase===p?'is-active':''} onClick={()=>setPhase(p)}><L>{p==='all'?'All phases':`Phase ${p}`}</L></button>)}</div>
      <div className="future-hardware-grid">{rows.map(item=><article key={item.id} className="future-hardware-card future-hardware-cost-card">
        <StatusPill state="planned">{item.phase}</StatusPill><h3><L>{item.name}</L></h3><strong className="future-equipment-price"><L>{euro(totalCost(item))}</L></strong><span className="future-data-provenance"><L>Estimated equipment subtotal per configuration</L></span><p><GlossaryText>{item.purpose}</GlossaryText></p>
        <details className="future-hardware-expand"><summary><L>Components and unit costs</L></summary><div className="future-hardware-bom">{item.items.map(([name,count,unit,url,note],i)=><div key={i}><span>{url?<a href={url} target="_blank" rel="noreferrer"><L>{name}</L> ↗</a>:<L>{name}</L>}<small><L>{note}</L></small></span><span><L>{count}</L> × <L>{euro(unit)}</L></span><b><L>{euro(count*unit)}</L></b></div>)}</div>
        <div className="future-hardware-subtotal"><span><L>Equipment subtotal</L></span><strong><L>{euro(totalCost(item))}</L></strong></div>
        <p><b><L>Recurring operating costs</L></b><L>{item.recurring}</L></p><p className="future-hardware-caution"><b><L>Design and procurement note</L></b><L>{item.notes}</L></p></details>
      </article>)}</div>
    </section>}
    {tab==="validation"&&<section className="future-section"><SectionHeader eyebrow="technical sequencing" title="Field validation sequence"
      copy="First validate one coastal AIS receiver, one radio decoder and resilient storage. Prototype a recoverable Drifter after station-health telemetry and legal/safety requirements are defined. Expand environmental and acoustic sensing only after calibration and maintenance procedures are proven." />
      <p className="future-inline-note"><GlossaryText>Price anchors: Raspberry Pi official 2026 pricing and RAKwireless GPS tracker listings. EUR component allowances are engineering budgets, not live retailer offers. V4 RTL-SDR has been discontinued, so receiver estimates use the V3 line.</GlossaryText></p>
    </section>}
  </>;
}

const contributionIcons = {'Infrastructure':'◈','Sensors / coastal stations':'⌁','Sensors / field research':'◉','Existing systems / data':'▤','Open-source software':'⌘','Verification / fieldwork':'◇'};
const contributionSummary = name => ({
  'Compute and Oracle VM capacity':'Give the team a safe place to test changes before they reach the live system.',
  'Resilient storage, telemetry and networking':'Help protect the archive and recover quickly when a server fails.',
  'Authorized maritime observation feeds':'Make the map more reliable by adding a documented source of vessel observations.',
  'Receivers, firmware and interoperability':'Help different instruments speak the same language.',
  'AIS coastal observation node':'Build a shore station that listens for nearby vessel positions.',
  'Receive-only maritime radio':'Support a lawful listening station for maritime messages.',
  'Satellite, oceanography and historical archives':'Add independent images and ocean data to check an investigation.',
  'Field validation and calibration':'Test instruments in the field before their readings inform research.',
  'Drifter buoy and environmental instrumentation':'Help prototype a recoverable floating instrument to study surface movement.'
})[name] || name;
function Contributions() {
  const t=useT(),lang=useLocale();
  const [tab,setTab]=useState("catalog");
  const [filter, setFilter] = useState('all');
  const [selected, setSelected] = useState([]);
  const [showSteps, setShowSteps] = useState(false);
  const groups = [...new Set(contributionNeeds.map(item => item.group))];
  const visible = contributionNeeds.filter(item => filter === 'all' || item.group === filter).sort((a,b)=>a.rank-b.rank);
  const toggle = name => setSelected(old=>old.includes(name)?old.filter(n=>n!==name):[...old,name]);
  const message = lang==='it'?'Ciao SeaCommons,\n\nVorrei contribuire con:\n'+selected.map(n=>'• '+t(n)).join('\n')+'\n\nOrganizzazione / nome:\nRisorse disponibili:\nLuogo e disponibilità:\nContatto preferito:\n\nChiedo di concordare ambito tecnico e prossimi passi prima di acquisti o accessi.':'Hello SeaCommons,\n\nI would like to help with:\n'+selected.map(n=>'• '+n).join('\n')+'\n\nMy organisation / name:\nWhat I can provide:\nLocation and availability:\nPreferred contact:\n\nPlease share the technical scope and next steps before any purchase or account access.';
  const contact = 'mailto:republic@suezcanal.xyz?subject='+encodeURIComponent(lang==='it'?'SeaCommons — richiesta di contributo':'SeaCommons — contribution enquiry')+'&body='+encodeURIComponent(message);
  return <div className="future-contribute">
    <section className="future-contribute__hero"><span className="future-eyebrow"><L>SEA COMMONS / BUILD WITH US</L></span><h1><L>Resource contributions</L></h1><p><L>SeaCommons needs people, equipment, data access and resources to continue its research. This page explains what is needed, how each contribution would help and how to discuss a collaboration. No payment or commitment is made here.</L></p><div className="future-contribute__hero-links"><button type="button" onClick={()=>setTab("catalog")}><L>Explore contributions ↓</L></button><button type="button" onClick={()=>setTab("onboarding")}><L>Start with a free server ↗</L></button></div></section>
    <KeyFigures items={[{title:"Resource requirements",value:contributionNeeds.length,detail:"Defined opportunities in the contribution register."},{title:"Urgent priorities",value:contributionNeeds.filter(n=>n.urgency==="Urgent").length,detail:"Planning priority, not an operational incident count."},{title:"Selected",value:selected.length,detail:"Resources in your enquiry. No payment is made here."}]}/>
    <ViewTabs items={[["catalog","Contribution catalogue"],["onboarding","Partner onboarding"],["request","Contribution request"]]} selected={tab} onChange={setTab}/>
    {tab==="onboarding"&&<>
    <section id="contribute-start" className="future-contribute__starter"><div className="future-contribute__starter-copy"><span className="future-eyebrow"><L>A GOOD FIRST STEP / INFRASTRUCTURE</L></span><h2><L>Isolated test server</L></h2><p><L>SeaCommons needs a separate place to try updates and check backups. An eligible Oracle Cloud Always Free virtual machine can support small, isolated tests without touching the live database.</L></p><div className="future-contribute__price"><strong>€0</strong><span><L>/ month, within eligible Always Free limits</L></span></div><p className="future-contribute__warning"><L>This is a test environment, not a replacement for the production server. Oracle may require a payment card for verification; capacity and free eligibility depend on the account, region and chosen resources.</L></p><button type="button" onClick={()=>setShowSteps(v=>!v)} aria-expanded={showSteps}><L>{showSteps?'Hide':'Show'}</L><L> the setup guide </L><L>{showSteps?'−':'+'}</L></button></div><div className="future-contribute__starter-visual" aria-hidden="true"><div className="future-contribute__server">01<span>ORACLE CLOUD</span><strong><L>TEST VM</L></strong><small><L>Isolated · Always Free eligible</L></small></div><div className="future-contribute__connection">↓ <span><L>Health checks · test restores</L></span></div><div className="future-contribute__server future-contribute__server--end">02<span>SEA COMMONS</span><strong>STAGING</strong><small><L>No production data or credentials</L></small></div></div></section>
    {showSteps && <section className="future-contribute__guide" aria-label="Oracle Always Free setup guide"><h3><L>How to get started</L></h3><ol><li><strong><L>Create your own Oracle Cloud account.</L></strong><p><L>Open the official Free Tier registration page. Choose your home region carefully; free capacity is not guaranteed in every region.</L></p><a href="https://www.oracle.com/cloud/free/" target="_blank" rel="noreferrer">Oracle Free Tier ↗</a></li><li><strong><L>Create an Always Free eligible VM.</L></strong><p><L>In Compute → Instances, choose an eligible shape and verify the “Always Free” label. Stay within the published compute, storage and networking quotas.</L></p><a href="https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier.htm" target="_blank" rel="noreferrer"><L>Check Oracle's limits ↗</L></a></li><li><strong><L>Secure it before connecting anything.</L></strong><p><L>Use SSH keys, restrict inbound access, enable monitoring and set budget alerts. Never send passwords, private keys, API tokens or billing details.</L></p></li><li><strong><L>Contact SeaCommons for a scoped test.</L></strong><p><L>Send the region, eligible VM shape and a contact email. We will agree a non-production test and the access needed. Do not connect it to production until the scope is approved.</L></p><a href="mailto:republic@suezcanal.xyz?subject=SeaCommons%20Oracle%20Always%20Free%20test%20VM"><L>Request onboarding ↗</L></a></li></ol><p className="future-contribute__guide-note"><L>This is a real self-service account setup followed by a manual technical review, not an automated provisioning or payment flow. The contribution is only accepted after the team confirms it.</L></p></section>}
    </>}
    {tab==="catalog"&&<section id="contribute-catalog" className="future-contribute__catalog"><div className="future-contribute__catalog-heading"><div><span className="future-eyebrow"><L>PICK A PART OF THE PROJECT</L></span><h2><L>Contribution catalogue</L></h2></div><p><L>Prices are planning estimates, not checkout prices. You can offer equipment, services, access or engineering time instead of money.</L></p></div><div className="future-contribute__filters" role="group" aria-label="Filter contributions"><button type="button" className={filter==='all'?'is-active':''} onClick={()=>setFilter('all')}><L>All</L></button>{groups.map(g=><button key={g} type="button" className={filter===g?'is-active':''} onClick={()=>setFilter(g)}><L>{g}</L></button>)}</div><div className="future-contribute__grid">{visible.map(item=><article key={item.name} className="future-contribute__item"><div className="future-contribute__item-top"><span className="future-contribute__icon" aria-hidden="true"><L>{contributionIcons[item.group]||'◇'}</L></span><small><L>{item.group}</L></small><StatusPill state={item.urgency==='Urgent'?'warn':'planned'}>{item.urgency}</StatusPill></div><h3><L>{item.name}</L></h3><p><GlossaryText>{contributionSummary(item.name)}</GlossaryText></p><strong className="future-contribute__cost"><L>{item.cost}</L></strong><details><summary><L>What's included and how we test it</L></summary><p><strong><L>Needed:</L></strong> <GlossaryText>{item.need}</GlossaryText></p><p><strong><L>Partner role:</L></strong> <GlossaryText>{item.partnerRole}</GlossaryText></p><p><strong><L>Proof it works:</L></strong> <GlossaryText>{item.acceptance}</GlossaryText></p></details><button type="button" className={selected.includes(item.name)?'is-selected':''} onClick={()=>toggle(item.name)} aria-pressed={selected.includes(item.name)}><L>{selected.includes(item.name)?'✓ Selected — remove':'Add to my contribution +'}</L></button></article>)}</div></section>}
    {tab==="request"&&<section className="future-contribute__basket" aria-live="polite"><div><span className="future-eyebrow"><L>YOUR CONTRIBUTION</L></span><h2><L>{selected.length ? selected.length+' · '+t('Selected'):'No resources selected'}</L></h2><p><L>{selected.length?selected.map(t).join(' · '):'Choose one or more options above. There is no online payment: the next step is a conversation about feasibility, responsibilities and access.'}</L></p></div>{selected.length?<a href={contact}><L>Send contribution enquiry ↗</L></a>:<a href="mailto:republic@suezcanal.xyz?subject=SeaCommons%20collaboration"><L>Discuss a different idea ↗</L></a>}</section>}
  </div>;
}

function WorkstreamList({ project }) {
  return (
    <div className="future-workstreams">
      {project.workstreams.map((stream, index) => (
        <article key={stream.id}>
          <div className="future-workstreams__index"><L>{String(index + 1).padStart(2, '0')}</L></div>
          <div>
            <div className="future-workstreams__title">
              <h4><L>{stream.name}</L></h4>
              <StatusPill state={stream.state}>{stream.state}</StatusPill>
            </div>
            <p><L>{stream.note}</L></p>
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
          <span className="future-eyebrow"><L>SeaCommons workspace</L></span>
          <h2><L>{project.name}</L></h2>
        </div>
        <StatusPill state={project.status}>{project.status}</StatusPill>
      </header>

      <p className="future-project-lead"><L>{project.summary}</L></p>

      <div className="future-detail-grid">
        <div><span><L>current phase</L></span><strong><L>{project.phase}</L></strong></div>
        <div><span><L>workstreams</L></span><strong><L>{project.workstreams.length}</L></strong></div>
        <div><span><L>access</L></span><strong><L>identity via OIDC; resource grants pending</L></strong></div>
      </div>

      <div className="future-capabilities">
        <span className="future-eyebrow"><L>capabilities / scope</L></span>
        <div>{project.capabilities.map((item) => <span key={item}><L>{item}</L></span>)}</div>
      </div>

      <div className="future-two-col future-two-col--wide">
        <section>
          <span className="future-eyebrow"><L>development workstreams</L></span>
          <WorkstreamList project={project} />
        </section>
        <section>
          <span className="future-eyebrow"><L>project documents</L></span>
          <div className="future-doc-list">
            {project.documents.map((doc) => (
              <div className="future-doc-row" key={doc.id}>
                <span>
                  <b><L>{doc.title}</L></b>
                  <small><L>{doc.kind}</L> · <L>{doc.visibility}</L></small>
                </span>
                <time><L>{doc.updated}</L></time>
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
        <span><L>system</L></span>
        <strong><L>{serviceState}</L></strong>
        <StatusPill state={serviceState}>{ops.loading ? 'connecting' : serviceState}</StatusPill>
      </div>
      <div>
        <span><L>Raw observations · </L><L>{period === '7d' ? '7 days' : '24 h'}</L></span>
        <strong><L>{formatCount(pipeline?.raw_observations)}</L></strong>
        <small><L>Source inputs received in this time window</L></small>
      </div>
      <div>
        <span><L>episodes · </L><L>{period === '7d' ? '7 days' : '24 h'}</L></span>
        <strong><L>{formatCount(pipeline?.maritime_episodes)}</L></strong>
        <small><L>{formatCount(pipeline?.corroborated_episodes)}</L><L> corroborated</L></small>
      </div>
      <div>
        <span><L>investigations · </L><L>{period === '7d' ? '7 days' : '24 h'}</L></span>
        <strong><L>{formatCount(pipeline?.investigation_hypotheses)}</L></strong>
        <small><L>Signals under examination, not confirmed incidents</L></small>
      </div>
    </section>
  );
}

function PipelinePanel({ status, period = '24h' }) {
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
        <span className="future-eyebrow"><L>evidence pipeline · </L><L>{period === '7d' ? '7 days' : '24 h'}</L></span>
        <div className="future-metric-list">
          {rows.map(([label, value]) => <div key={label}><span><L>{label}</L></span><strong><L>{formatCount(value)}</L></strong></div>)}
        </div>
      </section>
      <section className="future-metric-panel">
        <span className="future-eyebrow"><L>sensor activity · </L><L>{period === '7d' ? '7 days' : '24 h'}</L></span>
        <div className="future-metric-list">
          {sensorRows.map(([label, value]) => <div key={label}><span><L>{label}</L></span><strong><L>{formatCount(value)}</L></strong></div>)}
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
      <span className="future-eyebrow"><L>acquisition families</L></span>
      <div>
        {rows.map((row) => (
          <article key={row.family}>
            <span><L>{row.label}</L></span>
            <div>
              {row.mode ? <small><L>{row.mode}</L></small> : null}
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
  const generated = ops.status?.generated_at;
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
        <article><small><L>scope</L></small><h3><L>Humanitarian OSINT</L></h3><p><GlossaryText>Distress, SAR activity and humanitarian reporting under conservative privacy, provenance and location-precision controls.</GlossaryText></p></article>
        <article><small><L>scope</L></small><h3><L>Maritime Intelligence</L></h3><p><GlossaryText>AIS integrity, vessel behaviour, radio, environmental and satellite investigation context without presuming intent.</GlossaryText></p></article>
        <article><small><L>method</L></small><h3><L>One evidence model</L></h3><p><L>Source observation → normalization → derived cue → episode → hypothesis → policy-governed public case.</L></p></article>
      </div>
    </section>
    {period !== 'overall' && <section className="future-section">
      <SectionHeader eyebrow="02 / measured activity" title="How incoming information becomes evidence."
        copy={`Values are from the selected ${windowLabel} window. The Play archive is cumulative and stays separate.`} />
      <div className="future-funnel-grid">
        {stages.map((stage, index) => <article key={stage.label}>
          <small><L>{String(index + 1).padStart(2, '0')}</L> / <L>{stage.label}</L></small>
          <strong><L>{formatCount(stage.value)}</L></strong>
          <span><L>{stage.note}</L></span>
        </article>)}
      </div>
      <p className="future-data-provenance">Source: canonical SeaCommons API /api/v1/status?hours=<L>{period === '7d' ? 168 : 24}</L>. <L>{generated ? 'Snapshot generated ' + new Date(generated).toLocaleString() + '.' : 'Waiting for timestamp.'}</L><L> A derived cue is not a factual finding.</L></p>
    </section>}
    <section className="future-section">
      <SectionHeader eyebrow="03 / product ecology" title="The different parts of SeaCommons."
        copy="Each SeaCommons surface has a separate purpose and audience. Futures keeps you inside your authenticated partner workspace." />
      <div className="future-product-grid">
        {products.map((product) => {
          const content = <><small>SeaCommons / <L>{product.label}</L></small><h3><L>{product.label}</L></h3><p><L>{product.note}</L></p><span><L>{product.url ? 'open surface ↗' : product.label === 'Futures' ? 'you are here' : 'reference only'}</L></span></>;
          return product.url
            ? <a key={product.label} href={product.url} target="_blank" rel="noreferrer"><L>{content}</L></a>
            : <article key={product.label}><L>{content}</L></article>;
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
              <span><L>{item.phase}</L></span>
              <StatusPill state={item.status}>{item.status}</StatusPill>
            </header>
            <h3><L>{item.title}</L></h3>
            <p><L>{item.detail}</L></p>
            <div className="future-pathway-meta">
              <small><L>Potential inputs</L></small>
              <span><L>{item.inputs.join(' · ')}</L></span>
            </div>
            <div className="future-pathway-meta">
              <small><L>Intended output</L></small>
              <span><L>{item.output}</L></span>
            </div>
          </article>
        ))}
      </section>
      <p className="future-data-provenance"><L>Future pathways require a separate source assessment, data permissions, verified field methods and an implementation agreement. The platform does not currently measure their impact or outcomes.</L></p>
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
            <small><L>{step.label}</L></small>
            <p><L>{step.text}</L></p>
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
        <span className="future-eyebrow"><L>SeaCommons Futures / partner workspace</L></span>
        <h1><L>Understand what happens at sea, through evidence.</L></h1>
        <p><L>
          SeaCommons brings together maritime observations, evaluates their reliability and helps researchers understand complex events without confusing signals with verified facts.
        </L></p>
        <div className="future-hero__meta">
          <StatusPill state={ops.status?.status || 'unknown'}>{ops.status?.status || 'operational feed pending'}</StatusPill>
          <span><L>{ops.updatedAt ? `updated ${ops.updatedAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : 'connecting to operational contracts'}</L></span>
          <button onClick={ops.refresh}>refresh</button>
        </div>
        {ops.error ? <p className="future-inline-note"><L>{ops.error}</L><L> Static project information remains available.</L></p> : null}
      </section>

      {!compact && <MethodExplorer />}


      <section className="future-period-tabs" aria-label="Analytics time period">
        <div role="group" aria-label="Analytics time window">
          {[
            ['24h', '24 hours'], ['7d', '7 days'], ['overall', 'Overall'],
          ].map(([value, label]) => <button key={value} type="button" aria-pressed={period === value}
            className={period === value ? 'is-active' : ''} onClick={() => setPeriod(value)}><L>{label}</L></button>)}
        </div>
        <small><L>{period === 'overall' ? 'Complete retained history in the database, not every observation ever seen' : `Activity recorded in the last ${period === '7d' ? 'seven days' : '24 hours'}, not a count of confirmed incidents`}</L></small>
      </section>
      {period === 'overall' && <LifetimeOverview ops={ops} overall={overall} />}
      {period !== 'overall' && <OperationalStrip ops={ops} period={period} />}
      <PlatformSummary ops={ops} period={period} />
      <section className="future-section future-dashboard-quicklinks">
        <SectionHeader eyebrow="workspace priorities" title="Operational reliability and sensor expansion." />
        <div className="future-hardware-grid">
          <button type="button" onClick={() => navigate('operations')}><small><L>incident register / 10 areas</L></small><strong><L>Criticalities and unresolved fixes ↗</L></strong><span><L>Passenger vessels, storage pressure, AIS, PLAY, scheduler and publication confidence.</L></span></button>
          <button type="button" onClick={() => navigate('hardware')}><small><L>distributed infrastructure / 7 pathways</L></small><strong><L>Sensors: equipment and costs ↗</L></strong><span><L>AIS and radio antennas, drifters, hydrophones, coastal sensors, compute and field partners.</L></span></button>
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
        {period === 'overall' ? <p className="future-inline-note"><L>Current source health appears below. Full-period Intel statistics are shown in Overall above; recent pipeline activity is not a lifetime total.</L></p> : <PipelinePanel status={ops.status} period={period} />}
        <SourceHealth pipeline={ops.pipeline} />
      </section>


    </>
  );
}

function Project({navigate,ops,overall}) {
  const [tab,setTab]=useState('reference');
  return (
    <>
      <section className="future-page-head">
        <span className="future-eyebrow"><L>SeaCommons project</L></span>
        <h1><L>Technical reference</L></h1>
        <p><L>
          This section contains the detailed technical information supporting the project proposal. It is intended for developers and reviewers who need to examine the software, documents and current limitations.
        </L></p>
      </section>
      <ViewTabs items={[["reference","Technical overview"],["register","Project register"]]} selected={tab} onChange={setTab}/>{tab==="reference"?<FuturesOverview navigate={navigate} ops={ops} overall={overall}/>:<ProjectDetail project={seaCommonsProject} />}
    </>
  );
}

const deliveryLenses = [
 {area:'Evidence integrity',now:'Source observations, normalized events, derived cues and review states have separate data meanings.',gap:'More independent source verification and counter-evidence must be assessed before stronger claims.',proof:'Trace one sampled claim from raw input to lineage, review and publication rule.',question:'Can another reviewer reproduce the conclusion without trusting a screenshot?'},
 {area:'Operational resilience',now:'Live and Play operate as separate public surfaces backed by a canonical API.',gap:'Single-host risks, log growth, retention decisions and restart-safe archival still require measured closure.',proof:'Perform a test restore, simulate ingestion restart and measure bytes/day of recoverable storage.',question:'Can observations survive a network or server failure without being silently lost?'},
 {area:'Measurement contract',now:'24-hour, rolling 7-day and retained historical views exist as distinct populations.',gap:'Source time, reception time, database creation and update time must never be mixed in a single count.',proof:'Compare a sample of dashboard totals with independent database reference queries, with consistent as-of timestamps.',question:'What exactly is counted, over which interval and with what denominator?'},
 {area:'External interoperability',now:'The SeaCommons evidence pipeline is modular; partner integrations are possible through scoped APIs.',gap:'New verticals require fresh domain schemas, permits, rights, consent and operator responsibility.',proof:'Connect a synthetic test feed through a documented schema, authentication boundary and audit trail.',question:'Can a partner reuse a module without inheriting sensitive maritime records?'},
];
function DevelopmentHome({navigate}) {
 return <>
  <section className="future-page-head"><span className="future-eyebrow"><L>Development / engineering assessment</L></span><h1><L>Engineering and delivery</L></h1><p><L>Find out what still needs to be improved, why it matters and how the team will check the results. The work plan describes proposed activities; the updates register documents changes already made.</L></p></section>
  <KeyFigures items={[{title:"Evaluation areas",value:deliveryLenses.length,detail:"Engineering criteria used to assess the pilot."},{title:"Work packages",value:developmentSteps.length,detail:"Defined in the delivery roadmap."},{title:"Documented changes",value:journal.length,detail:"Entries in the reviewed editorial update register."}]}/>
  <section className="future-section"><SectionHeader eyebrow="Evaluation framework" title="Engineering evaluation" copy="Each topic makes a current capability, a real limitation and an independently checkable result visible to reviewers."/>
    <div className="future-domain-grid">{deliveryLenses.map(x=><article key={x.area}><small><L>ENGINEERING / EVALUATION</L></small><h3><L>{x.area}</L></h3><p><b><L>Current basis:</L></b> <GlossaryText>{x.now}</GlossaryText></p><details><summary><L>Constraints and evaluation</L></summary><p><b><L>Open constraint:</L></b> <GlossaryText>{x.gap}</GlossaryText></p><p><b><L>Required evidence:</L></b> <GlossaryText>{x.proof}</GlossaryText></p><p className="future-factual-note"><L>{x.question}</L></p></details></article>)}</div>
  </section>
  <section className="future-section"><SectionHeader eyebrow="Release governance" title="Release acceptance criteria" copy="Software release, field prototype and research conclusion are separate acceptance decisions."/>
   <div className="future-architecture-flow"><span><b><L>1 / Traceable source</L></b><p><L>Consent, license, device identity, acquisition clock and raw provenance.</L></p></span><span><b><L>2 / Measured behavior</L></b><p><L>Repeatable tests, observability, failure budgets and documented counter-cases.</L></p></span><span><b><L>3 / Human review</L></b><p><L>Independent interpretation and explicit limitations before public conclusions.</L></p></span><span><b><L>4 / Maintenance owner</L></b><p><L>One named custodian, security updates, costs and a recovery path.</L></p></span></div>
  </section>
  <section className="future-section"><SectionHeader eyebrow="Explore the evidence" title="Development records"/>
   <div className="future-support-grid"><article><h3><L>Roadmap</L></h3><p><L>Dependencies, expected duration and evidence required to close each planned work package.</L></p><button type="button" onClick={()=>navigate('roadmap')}><L>Examine the planned work →</L></button></article><article><h3><L>Updates</L></h3><p><L>Versioned changes with a verification source and the problem they resolve.</L></p><button type="button" onClick={()=>navigate('updates')}><L>Read verified changes →</L></button></article><article><h3><L>Operations</L></h3><p><L>Observed service activity, historically recorded defects and remaining verification tasks.</L></p><button type="button" onClick={()=>navigate('operations')}><L>Inspect operations →</L></button></article></div>
  </section>
 </>;
}

const developmentSteps = [
 {name:'Operational reliability',duration:'1–2 weeks',state:'ongoing',dependency:'Existing infrastructure and access to recovery backups',deliverable:'Recovery-tested hosting and monitored storage',description:'Document the data footprint, apply bounded retention and test restoring the evidence store. Make system interruptions visible before users lose access.',acceptance:'Successful restore test, storage alerts and a continuous service-health baseline.'},
 {name:'Measurement quality',duration:'2–3 weeks',state:'active',dependency:'Reliable observation storage and versioned metric definitions',deliverable:'Reconciled activity metrics for 24h, 7d and Overall',description:'Separate newly created records from updates, source observation times and automated processing. Verify that each dashboard metric uses a clearly defined population.',acceptance:'Independent reference queries agree with published measures and estimates are identified.'},
 {name:'Cross-source evidence',duration:'3–5 weeks',state:'active',dependency:'Verified source lineage and consistent measurements',deliverable:'Reviewable AIS, radio, satellite and humanitarian evidence chains',description:'Connect related observations while preventing dependent sources from being counted as independent corroboration. Record counter-evidence, uncertainty and reviewer decisions.',acceptance:'Representative investigations can be reproduced from source through assessed episode.'},
 {name:'Radio decoding and sensor validation',duration:'2–4 weeks',state:'planned',dependency:'Stable storage, receiver samples and quality criteria',deliverable:'Measured decode quality and field-device acceptance tests',description:'Evaluate repeatable radio decoding, coverage, timing accuracy and receiver health before expansion. Validate proposed coastal and drifting devices separately from existing software.',acceptance:'Documented sample-set results, failure modes and a maintainable pilot configuration.'},
 {name:'Partner interoperability',duration:'3–6 weeks',state:'planned',dependency:'Stable evidence contracts and tested access policies',deliverable:'Reproducible partner integration and documentation',description:'Provide versioned data interfaces, permissions, provenance records and onboarding workflows for authorized external feeds and collaborators.',acceptance:'A partner can integrate a sample source, review access boundaries and trace the resulting data.'},
 {name:'Field pilots and evaluation',duration:'4–8 weeks per pilot',state:'later',dependency:'Instrument reliability, local permissions and assigned operators',deliverable:'Evidence-backed pilot report and deployment decision',description:'Run a bounded trial with clear geographic coverage, maintenance responsibilities, calibration and public-interest outcomes. Evaluate performance before scaling.',acceptance:'Coverage, uptime, costs, evidence value and operating responsibilities are documented.'},
];
function Roadmap() {
 return <>
  <section className="future-page-head future-development-intro"><span className="future-eyebrow"><L>Development / delivery pathway</L></span><h1><L>Development roadmap</L></h1><p><L>A dependency-led plan with indicative implementation times. Durations represent focused engineering work after prerequisites are ready; phases may overlap, and they are not fixed delivery dates.</L></p></section>
  <KeyFigures items={[{title:"Work packages",value:developmentSteps.length,detail:"Planned sequence of development activities."},{title:"Active / ongoing",value:developmentSteps.filter(s=>["active","ongoing"].includes(s.state)).length,detail:"Editorial roadmap status, not verified progress."},{title:"Planned / later",value:developmentSteps.filter(s=>["planned","later"].includes(s.state)).length,detail:"Work dependent on earlier milestones."}]}/>
  <section className="future-section future-roadmap-timeline" aria-label="SeaCommons development stages"><header><div><span className="future-eyebrow"><L>Implementation pathway</L></span><h2><L>Six connected work packages</L></h2><p><L>Each phase names its outcome, prerequisites and an objective way to verify completion. The durations are estimates, not commitments.</L></p></div></header>
   <div className="future-roadmap-steps">{developmentSteps.map((step,index)=><article key={step.name} className="future-roadmap-step"><div className="future-roadmap-step-index"><span><L>{String(index+1).padStart(2,'0')}</L></span><i aria-hidden="true"/></div><div className="future-roadmap-step-body"><div className="future-roadmap-step-head"><div><h3><L>{step.name}</L></h3><p><L>{step.deliverable}</L></p></div><div className="future-roadmap-step-meta"><strong><L>{step.duration}</L></strong><StatusPill state={step.state}>{step.state}</StatusPill></div></div><p><GlossaryText>{step.description}</GlossaryText></p><details><summary><L>Dependencies and completion criteria</L></summary><dl><dt><L>Prerequisites</L></dt><dd><GlossaryText>{step.dependency}</GlossaryText></dd><dt><L>Completion check</L></dt><dd><GlossaryText>{step.acceptance}</GlossaryText></dd></dl></details></div></article>)}</div>
   <p className="future-inline-note"><L>Time estimates exclude partner approvals, procurement lead times and field permits. Each next phase begins when its prerequisites have been validated.</L></p>
  </section>
  <section className="future-section"><SectionHeader eyebrow="Partner contributions" title="What accelerates delivery" copy="Support is grouped by operational need, with clear responsibilities rather than repeated product categories."/><div className="future-support-grid">{supportAreas.map(item=><article key={item.area}><StatusPill state={item.status}>{item.status}</StatusPill><h3><L>{item.area}</L></h3><p><L>{item.need}</L></p></article>)}</div></section>
 </>;
}

function Documents() {
  const t=useT();
  const [query, setQuery] = useState('');
  const [group, setGroup] = useState('all');
  const groups = ['all', ...new Set(partnerDocuments.map((doc) => doc.group))];
  const filtered = partnerDocuments.filter((doc) => {
    const searchable = [doc.title, doc.source, doc.description, doc.kind].map(v=>String(v||'')+' '+t(v||'')).join(' ').toLowerCase();
    return (group === 'all' || doc.group === group) && searchable.includes(query.trim().toLowerCase());
  });

  return (
    <>
      <section className="future-page-head">
        <span className="future-eyebrow"><L>SeaCommons / docs library</L></span>
        <h1><L>Knowledge library</L></h1>
        <p><L>Engineering references and background material. Restricted sources require separate permission.</L></p>
      </section>


      <section className="future-section">
        <SectionHeader eyebrow="document register" title="Document register"
          copy="Published materials open from their cited source. Restricted documents are not served by this catalogue and require an explicit resource grant." />
        <div className="future-library-filters">
          <label><span><L>search documents</L></span><input type="search" placeholder={t("Title, format or topic")} value={query} onChange={(event) => setQuery(event.target.value)} /></label>
          <label><span><L>category</L></span><select value={group} onChange={(event) => setGroup(event.target.value)}>
            {groups.map((item) => <option value={item} key={item}><L>{item}</L></option>)}
          </select></label>
          <span><L>{filtered.length}</L> / <L>{partnerDocuments.length}</L><L> resources</L></span>
        </div>
        <section className="future-document-table" aria-label="SeaCommons project documents">
          <header><span><L>document</L></span><span><L>project</L></span><span><L>type</L></span><span><L>access</L></span><span><L>updated</L></span></header>
          {filtered.map((doc) => (
            <article key={doc.projectId + doc.id}>
              <div><strong><L>{doc.title}</L></strong><small><L>{doc.description || doc.source}</L></small>
                {doc.href ? <a className="future-doc-link" href={doc.href} target="_blank" rel="noopener noreferrer"><L>View reference ↗</L></a> : <small><L>restricted / request access</L></small>}
              </div>
              <span><L>{doc.project}</L></span>
              <span><L>{doc.kind}</L></span>
              <StatusPill state={doc.visibility === 'restricted' ? 'warn' : 'active'}>{doc.visibility}</StatusPill>
              <time><L>{doc.updated}</L></time>
            </article>
          ))}
          {filtered.length === 0 && <p className="future-inline-note"><L>No resource matches the selected filters.</L></p>}
        </section>
      </section>

      <section className="future-library-intake">
        <div><span className="future-eyebrow"><L>partner materials</L></span><h3><L>Request a reviewed document</L></h3>
          <p><L>Published reference materials are available above. For a partner brief or an unpublished resource, contact the programme team. Confidential materials are never uploaded to the public source repository. In-app uploads and permissioned downloads will be enabled only after verified private storage and server-side resource grants are in place.</L></p></div>
        <a href="mailto:republic@suezcanal.xyz?subject=SeaCommons%20document%20request"><L>contact programme team ↗</L></a>
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
        <span className="future-eyebrow"><L>guidebook</L></span>
        {groups.map((group) => (
          <div className="future-guide__group" key={group}>
            <small><L>{group}</L></small>
            {guidebook.filter((item) => item.group === group).map((item) => (
              <button key={item.id} className={active.id === item.id ? 'is-active' : ''} onClick={() => setActiveId(item.id)}>
                <L>{item.title}</L>
              </button>
            ))}
          </div>
        ))}
      </aside>
      <article>
        <span className="future-eyebrow"><L>living project knowledge</L></span>
        <h1><L>{active.title}</L></h1>
        <p className="future-guide__summary"><GlossaryText>{active.summary}</GlossaryText></p>
        <hr />
        {active.body.map((paragraph) => <p key={paragraph}><GlossaryText>{paragraph}</GlossaryText></p>)}
        <div className="future-guide__footer">
          <span><L>native Futures document</L></span>
          <span><L>Technical documentation is available in the Documents section.</L></span>
        </div>
      </article>
    </section>
  );
}

const transferableModules = [
 {codeReference:'apps/api/core/acquisition',name:'Acquisition adapters',state:'Established maritime core; adaptable',function:'Connect data feeds through rate-limited ingestion, source identifiers, timestamps, licenses and retry-aware acquisition.',reuse:'Public records, civic indicators, environmental datasets and field-research submissions.',gate:'A new adapter needs a permissioned source, tested schema and documented acquisition failures.'},
 {codeReference:'apps/api/core/intel',name:'Evidence & provenance ledger',state:'Established core; domain schemas required',function:'Retain original records and transformations so an auditor can distinguish source claims from software-derived statements.',reuse:'Cultural heritage documentation, participatory research and climate-observation registries.',gate:'New use cases must define consent, retention, data protection and reviewer authority.'},
 {codeReference:'apps/api/core/intel',name:'Geospatial correlation',state:'Established maritime methods; adaptable',function:'Compare time, distance, uncertainty and independent sources without turning proximity into a causal claim.',reuse:'Island infrastructure, coastal resilience, distributed field sites and public-space research.',gate:'Geographic coverage, coordinate quality and baseline assumptions must be evaluated per pilot.'},
 {codeReference:'apps/api/core/radio',name:'Radio and device ingestion',state:'Specialist pipeline / active validation',function:'Receive selected radio and sensor formats, preserve capture metadata, and test decoders against known fixtures.',reuse:'Community sensor stations, environmental instrumentation and local research networks.',gate:'Regulatory limits, supported equipment, calibration and maintenance need field validation.'},
 {codeReference:'apps/api/core/drift',name:'Simulation & environmental context',state:'Research capability',function:'Join metocean inputs, drift assumptions and observed positions to construct reproducible scenarios with uncertainty.',reuse:'Coastal environmental monitoring, training exercises and geographically bounded impact studies.',gate:'A model result must be compared with reference observations before operational interpretation.'},
 {codeReference:'apps/web/src/futures',name:'Publishing & partner workspaces',state:'Operational SeaCommons surfaces; reusable patterns',function:'Separate restricted raw evidence from privacy-filtered public maps, histories, reports and role-aware collaboration.',reuse:'Civic observatories, academic research portals and local cultural infrastructure.',gate:'A new workspace needs its own information model, access policy, editorial governance and audit.'},
];
function Tools() {
  const [tab,setTab]=useState("guide");
  return (
    <>
      <section className="future-page-head">
        <span className="future-eyebrow"><L>tools</L></span>
        <h1><L>Developer resources</L></h1>
        <p><L>
          SeaCommons is one implementation of a modular software architecture. The modules below describe which methods can be adapted to other research and civic sectors, and which are still subject to new validation. Other projects are not automatically part of this authenticated workspace.
        </L></p>
      </section>

      <ViewTabs items={[["guide","Developer resources"],["modules","Reusable modules"],["products","Product access and permissions"]]} selected={tab} onChange={setTab}/>
      {tab==="guide"&&<DeveloperGuide/>}
      {tab==="modules"&&<section className="future-section"><SectionHeader eyebrow="Transferable toolkit" title="Reusable modules" copy="Each row distinguishes actual SeaCommons capabilities from the extra implementation, legal and domain work needed to reuse a pattern elsewhere."/>
      <div className="future-domain-grid">{transferableModules.map(m=><article key={m.name}><small><L>{m.state}</L></small><h3><L>{m.name}</L></h3><p><b><L>What it does:</L></b> <GlossaryText>{m.function}</GlossaryText></p><p><b><L>Where it could transfer:</L></b> <GlossaryText>{m.reuse}</GlossaryText></p><p className="future-factual-note"><b><L>Before reuse:</L></b> <GlossaryText>{m.gate}</GlossaryText></p><a href={"https://github.com/suezcanalxyz/seacommons/tree/main/"+m.codeReference} target="_blank" rel="noopener noreferrer"><L>Inspect source module ↗</L></a></article>)}</div>
      <p className="future-factual-note"><L>Transferability is an engineering opportunity, not a claim of completed deployments in every listed sector. New fields require distinct funding, methods, permissions and domain verification.</L></p></section>}
      {tab==="products"&&<><section className="future-section"><SectionHeader eyebrow="Available product surfaces" title="Product access and permissions" copy="These are actual SeaCommons interfaces; they are different from the transferable modules above."/></section>
      <section className="future-tool-grid">
        {tools.map((tool) => {
          const inner = (
            <>
              <div><small><L>{tool.kind}</L></small><StatusPill state={tool.state}>{tool.state}</StatusPill></div>
              <h3><L>{tool.name}</L></h3>
              <p><L>{tool.description}</L></p>
              <span className="future-tool-grid__cta"><L>open tool ↗</L></span>
            </>
          );
          return tool.href ? <a key={tool.id} href={tool.href} target="_blank" rel="noopener noreferrer"><L>{inner}</L></a> : <article key={tool.id}><L>{inner}</L></article>;
        })}
      </section></>}
    </>
  );
}

function Updates() {
  return (
    <>
      <section className="future-page-head">
        <span className="future-eyebrow"><L>updates</L></span>
        <h1><L>Development updates</L></h1>
        <p><L>Evidence-led engineering decisions, not promotional announcements. Each update explains what changed, why it matters, what remains unverified and where the technical record can be checked.</L></p>
      </section>
      <section className="future-update-list">
        {timeline.map((item) => (
          <article key={item.date + item.title}>
            <time><L>{item.date}</L></time>
            <div>
              <div><span><L>{item.project}</L></span><small><L>{item.kind}</L></small></div>
              <h3><L>{item.title}</L></h3>
              <p><GlossaryText>{item.detail}</GlossaryText></p>
              {item.impact&&<p><b><L>What changes for a partner:</L></b> <GlossaryText>{item.impact}</GlossaryText></p>}
              {item.limit&&<p className="future-factual-note"><b><L>Still to verify:</L></b> <GlossaryText>{item.limit}</GlossaryText></p>}
              {item.proof&&<a href={item.proof} target="_blank" rel="noopener noreferrer"><L>Review the source change ↗</L></a>}
            </div>
          </article>
        ))}
      </section>
    </>
  );
}

function Invitations() {
  return <section className="future-section future-invitations" aria-label="Viewer invitations availability">
    <SectionHeader eyebrow="partner access / manual review" title="Request Viewer access"
      copy="Viewer invitations require explicit administrator approval and server-side membership controls. Signing in does not grant access to private evidence or permit invitations." />
    <p className="future-factual-note" role="status"><L>The invitation submission service is not enabled for this workspace. No invitation can be saved or approved from this page today. This is a documented access limitation, not a pending invitation.</L></p>
    <p><L>To propose a partner, provide their name, institutional email and intended purpose directly to the workspace administrator. Do not send credentials, API keys or protected evidence in an email.</L></p>
    <a href="mailto:republic@suezcanal.xyz?subject=SeaCommons%20Futures%20Viewer%20access"><L>Contact the workspace administrator ↗</L></a>
    <p className="future-data-provenance"><L>Activation criteria: OIDC authorization enforced on the invitation API, restricted roles, audited approvals, read-only scope and an end-to-end test. Access remains manual until all conditions pass.</L></p>
  </section>;
}
function Access({ user }) {
  const identity = user?.profile?.email || user?.profile?.preferred_username || user?.email || 'authorised administrator';
  return (
    <>
      <section className="future-page-head">
        <span className="future-eyebrow"><L>access</L></span>
        <h1><L>Your account and workspace access.</L></h1>
        <p><L>
          This page shows which account you are using and how workspace permissions work. Signing in confirms your identity, but it does not automatically grant access to private investigations or documents. You can propose invitations below; every request is reviewed before any access can be granted.
        </L></p>
      </section>

      <section className="future-identity-card">
        <div><span><L>identity</L></span><strong><L>{identity}</L></strong></div>
        <div><span><L>role</L></span><strong><L>not asserted by frontend</L></strong></div>
        <div><span><L>session</L></span><strong><L>OIDC identity only</L></strong></div>
      </section>

      <section className="future-access-table">
        <header><span><L>workspace</L></span><span><L>level</L></span><span><L>scope</L></span><span><L>mode</L></span></header>
        {accessMatrix.map((row) => (
          <article key={row.system}>
            <strong><L>{row.system}</L></strong>
            <StatusPill state={row.level}>{row.level}</StatusPill>
            <span><L>{row.scope}</L></span>
            <small><L>{row.state}</L></small>
          </article>
        ))}
      </section>

      <Invitations />
      <section className="future-access-note">
        <span className="future-eyebrow"><L>final permission hierarchy</L></span>
        <p><L>organisation → SeaCommons workspace → project / subproject → resource or tool</L></p>
        <p><L>A grant can stop at any level. Access to one document never implies access to the rest of the project.</L></p>
      </section>
    </>
  );
}

export default function FuturesApp() {
  const { user, signOut } = useAuth();
  const [period, setPeriod] = useState('overall');
  const [lang,setLang]=useState(()=>{try{return localStorage.getItem('futures-language')==='en'?'en':'it'}catch{return 'it'}});
  useEffect(()=>{try{localStorage.setItem('futures-language',lang)}catch{/* storage unavailable */} document.documentElement.lang=lang;},[lang]);
  const navLabel=item=>lang==='it'?(IT_NAV[item]||item):(NAV_LABELS[item]||item);
  const [view, setView] = useState(() => readWorkspaceView());
  const [installPrompt, setInstallPrompt] = useState(null);
  const [installed, setInstalled] = useState(false);
  // Installation help is opt-in: never block a partner's first mobile visit.
  const [showInstallGuide, setShowInstallGuide] = useState(false);
  const isIOS = typeof navigator !== 'undefined' && /iPad|iPhone|iPod/.test(navigator.userAgent);
  const dismissInstallGuide = () => {
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
    <FuturesLocale value={lang}><div className="future-app">
      <aside className="future-sidebar">
        <button type="button" className="future-brand" onClick={() => navigate('overview')} aria-label="Futures dashboard">
          <i /><span>SEA<br />COMMONS</span>
        </button>
        <div className="future-product"><span>futures</span><small><L>{lang==='it'?'area partner':'partner workspace'}</L></small></div>
        <div className="future-mobile-language"><LanguageSwitch lang={lang} setLang={setLang}/></div><button type="button" className="future-mobile-account" onClick={() => navigate('access')} aria-label="Open account" aria-current={view === 'access' ? 'page' : undefined}><span aria-hidden="true">◎</span><L> Account</L></button>
        <nav aria-label="Futures">
          {PRIMARY_NAV.map((item) => (
            <button key={item} className={view === item || (SUBNAV[item]||[]).some(([id])=>id===view) ? 'is-active' : ''} onClick={() => navigate(item)}>
              <span><L>{navLabel(item)}</L></span><i>↗</i>
            </button>
          ))}
        </nav>
        {installPrompt && !installed && <button type="button" className="future-install-button" onClick={installApp}><L>install app ↓</L></button>}
        <div className="future-sidebar__base">
          <span className="future-session-pill"><L>OIDC connected</L></span>
          <button onClick={() => signOut?.()}><L>sign out</L></button>
        </div>
      </aside>

      <main className="future-main">
        <header className="future-topbar">
          <div><span>SeaCommons / Futures</span><b><L>{navLabel(view)}</L></b></div>
          <div className="future-topbar__links"><span><L>{lang==='it'?'Area partner':'Secure partner workspace'}</L></span><LanguageSwitch lang={lang} setLang={setLang}/>{!installed&&<button type="button" className="future-install-shortcut" aria-label="How to install Futures" onClick={()=>setShowInstallGuide(true)}><L>Install</L></button>}<button type="button" className="future-account-shortcut" onClick={()=>navigate("access")}><L>Account</L></button><button type="button" className="future-topbar-logo" onClick={() => navigate('overview')} aria-label="SeaCommons Futures home"><i aria-hidden="true" /><span>SEA<br />COMMONS</span></button></div>
        </header>

        <div className="future-content" data-view={view}>
          {lang==='it'&&['documents','knowledge','tools','project','guidebook'].includes(view)&&<div className="future-language-note">Alcuni dati delle fonti e materiali originali possono restare in inglese.</div>}
          {Object.entries(SUBNAV).some(([,items])=>items.some(([id])=>id===view)) && <nav className="future-subnav" aria-label={lang==='it'?'Navigazione di sezione':'Section navigation'}>{(Object.entries(SUBNAV).find(([,items])=>items.some(([id])=>id===view))?.[1] || []).map(([id,label])=><button type="button" key={id} aria-current={id===view?'page':undefined} className={id===view?'is-active':''} onClick={()=>navigate(id)}><L>{lang==='it'?(id==='intelligence'?'Confronto':id==='knowledge'?'Dossier':id==='documents'?'Registro documenti':IT_NAV[id]||label):label}</L></button>)}</nav>}
          {(view === 'intelligence'||view.startsWith('intel-')) && <IntelligenceDashboard section={view==='intelligence'?'compare':view.slice(6)} ops={ops} overall={overall} period={period} setPeriod={setPeriod} navigate={navigate} />}
          {view === 'platform' && <PlatformNetwork />}
          {view === 'knowledge' && <KnowledgeLibrary />}
          {view === 'development' && <DevelopmentHome navigate={navigate} />}
          {view === 'agents' && <AgentsWorkspace lang={lang}/>}
          {view === 'overview' && <StrategyWorkspace lang={lang} navigate={navigate} ops={ops} overall={overall}/>}
          {view === 'history' && <HistoricalAnalytics ops={ops} overall={overall} />}
          {view === 'operations' && <Operations ops={ops} />}
          {view === 'ais-check' && <AisCrossCheck />}
          {view === 'hardware' && <Hardware />}
          {view === 'contributions' && <Contributions />}
          {view === 'project' && <Project navigate={navigate} ops={ops} overall={overall}/>}
          {view === 'roadmap' && <Roadmap />}
          {view === 'documents' && <Documents />}
          {view === 'guidebook' && <Guidebook />}
          {view === 'tools' && <Tools />}
          {view === 'updates' && <AgenticJournal lang={lang}/>}
          {view === 'access' && <Access user={user} />}
        </div>
      </main>
      {showInstallGuide && !installed && <div className="future-pwa-overlay" role="presentation">
        <section className="future-pwa-dialog" role="dialog" aria-modal="true" aria-labelledby="future-pwa-title">
          <div className="future-pwa-heading"><small><L>FUTURES / MOBILE APP</L></small><button type="button" onClick={dismissInstallGuide} aria-label="Close installation guide">✕</button></div>
          <div className="future-pwa-symbol" aria-hidden="true">◈</div>
          <h2 id="future-pwa-title"><L>Take Futures with you.</L></h2>
          <p><L>Install SeaCommons Futures on your Home Screen for an app-like experience with full-screen navigation and quick access to your workspace.</L></p>
          {isIOS ? <ol><li><L>Open this page in </L><b>Safari</b>.</li><li><L>Tap </L><b><L>Share</L></b><L> (square with an upward arrow).</L></li><li><L>Select </L><b><L>Add to Home Screen</L></b><L>, then tap </L><b><L>Add</L></b>.</li></ol> : <ol><li><L>Open this page in </L><b>Chrome</b>.</li><li><L>Open the browser menu and select </L><b><L>Install app</L></b> or <b><L>Add to Home screen</L></b>.</li><li><L>Confirm installation.</L></li></ol>}
          {installPrompt && !isIOS && <button type="button" className="future-pwa-primary" onClick={() => { installApp(); dismissInstallGuide(); }}><L>Install Futures</L></button>}
          <button type="button" className="future-pwa-secondary" onClick={dismissInstallGuide}><L>Continue in browser</L></button>
          <small><L>You can always install it later from your browser menu.</L></small>
        </section>
      </div>}
      <nav className="future-mobile-nav" aria-label="Mobile app navigation">
        {['overview','intelligence','platform','agents','contributions'].map((item) => (
          <button type="button" key={item} className={view === item || (SUBNAV[item]||[]).some(([id])=>id===view) ? 'is-active' : ''} onClick={() => navigate(item)}>
            <span className="future-mobile-nav-icon" aria-hidden="true"><L>{{overview:'◈',intelligence:'⌁',platform:'◉',agents:'◇',contributions:'▤',access:'◎'}[item]}</L></span>
            <span><L>{lang==='it'?({overview:'Sintesi',intelligence:'Dati',platform:'Piattaforma',agents:'Agenti',contributions:'Contributi'})[item]:({overview:'Overview',intelligence:'Data',platform:'Platform',agents:'Agents',contributions:'Network',access:'Account'})[item]}</L></span>
          </button>
        ))}
      </nav>
    </div></FuturesLocale>
  );
}
