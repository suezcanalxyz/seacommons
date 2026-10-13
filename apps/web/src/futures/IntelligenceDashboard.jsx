import React, {useState} from 'react';

const stages=[
  ['raw_observations','Raw observations','Source records received by SeaCommons. They are raw inputs, not confirmed events.'],
  ['parsed_events','Normalized events','Records converted into the standard SeaCommons format so sources can be compared.'],
  ['derived_cues','Derived cues','Possible patterns detected by rules or models. A cue is a lead, not proof.'],
  ['maritime_episodes','Recognized episodes','Groups of related maritime observations that can be investigated together.'],
  ['investigation_hypotheses','Hypotheses','Questions or possible explanations being evaluated, not conclusions.'],
  ['corroborated_episodes','Corroborated episodes','Episodes supported by at least two independent evidence lineages.'],
  ['review_ready','Ready for review','Investigations prepared for human assessment. This does not establish wrongdoing.'],
  ['analysis_outputs','Analysis outputs','Episodes and investigation hypotheses processed in the selected window. Overlaps with previous counts; never add them together.']
];
const sensors=[
  ['ais_fixes','AIS positions','Position reports recorded from vessel AIS transmissions. A position does not indicate an incident.'],
  ['radio_bursts','Radio bursts','Detected radio signal bursts. A burst may not contain a successfully decoded message.'],
  ['radio_events','Radio events','Radio observations translated into usable events. Not every burst becomes an event.'],
  ['satellite_observations','Satellite observations','Actual satellite observations ingested, not all potentially available imagery or search results.'],
  ['active_source_names','Active data sources','Distinct source names contributing raw observations in the selected period.']
];
const freshness=[
  ['raw_observation','Latest raw observation','Last received source observation.'],
  ['parsed_event','Latest normalized event','Last received event in the normalized schema.'],
  ['analysis_output','Latest analysis output','Last recorded analysis result.']
];
function number(value){return value===null||value===undefined?'Not reported':Number.isFinite(Number(value))?new Intl.NumberFormat('en-GB').format(Number(value)):'Not reported'}
function stamp(value){if(!value)return 'Not reported';const d=new Date(value);return Number.isNaN(d.getTime())?'Not reported':d.toLocaleString()}
function MetricSet({heading,rows,data}) {const [expanded,setExpanded]=useState(null);return <section className="future-section"><header><h2>{heading}</h2></header><div className="future-intelligence-metrics">{rows.map(([key,label,meaning])=><article key={key} className="future-intelligence-metric"><div className="future-intelligence-metric-top"><span>{label}</span><button type="button" aria-expanded={expanded===key} aria-label={'Explain '+label} onClick={()=>setExpanded(expanded===key?null:key)}>What is this? {expanded===key?'−':'+'}</button></div><strong>{number(data?.[key])}</strong><p>{meaning}</p>{expanded===key&&<div className="future-intelligence-legend"><b>How to read it</b><p>{meaning} The number belongs to its own evidence stage; it is not directly comparable to a case or vessel count. Missing means unavailable, not zero.</p><small>API field: {key}</small></div>}</article>)}</div></section>}

import { fetchJson } from '../services/api/client.js';
import { resolveSiteApiBase } from '../site/liveApi.js';

const TABS = [['pipeline','Evidence pipeline'],['sources','Sources & types'],['quality','Evidence quality'],['sensors','Sensors & SAR'],['activity','Acquisition & logs']];
const stageKeys={raw:'raw_observations',normalized:'parsed_events',derived:'derived_cues',episodes:'maritime_episodes',hypotheses:'investigation_hypotheses',corroborated:'corroborated_episodes',review_ready:'review_ready'};
const stageDescriptions=Object.fromEntries(stages.map(s=>[s[0],s[2]]));
const sourceHelp={
  raw_by_source:'Who supplied the original observations. Sources can have different collection rates.',
  raw_observation_types:'Types of source observations before standardization, including AIS and public reports.',
  normalized_by_source:'Source attribution on processed Intel events. This is not the raw ingestion count.',
  normalized_event_types:'Types assigned to standardized events after parsing and classification.',
  episode_families:'Kinds of related maritime observations recognized by the correlation engine.',
  episode_verification:'Verification of episodes: one source, multiple indicators, or independent lineages.',
  hypothesis_types:'Investigation topics; counts are not findings of illegal activity.',
  hypothesis_states:'Processing state of hypotheses: collecting, candidate or ready for review.',
  hypothesis_evidence_stages:'Highest evidence level reached by each hypothesis.'
};
function Breakdown({title,items,help}) {
 const entries=Object.entries(items||{}).filter(([,n])=>Number.isFinite(Number(n))).sort((a,b)=>Number(b[1])-Number(a[1]));
 const max=Math.max(1,...entries.map(x=>Number(x[1])));
 return <section className="future-section future-intelligence-breakdown"><h2>{title}</h2><p>{help}</p>{entries.length?<div className="future-intelligence-bars">{entries.map(([key,value])=><div className="future-intelligence-bar" key={key}><span title={key}>{key.replaceAll('_',' ')}</span><div><i style={{width:Math.max(1,100*Number(value)/max)+'%'}}/></div><strong>{number(value)}</strong></div>)}</div>:<p>No breakdown currently available for this period.</p>}</section>
}
function useOperatorMetrics(period){
 const [data,setData]=React.useState(null);
 const [loading,setLoading]=React.useState(false);
 const [error,setError]=React.useState('');
 const refresh=React.useCallback(async()=>{
  setLoading(true);setError('');
  try{
   const url=period==='overall'?'/api/v1/operator/ingestion/overall':`/api/v1/operator/ingestion/overview?hours=${period==='7d'?168:24}`;
   const result=await fetchJson(resolveSiteApiBase(),url,undefined,22000);
   setData(result);
  }catch(e){setData(null);setError('Restricted operator data unavailable. An operator/admin API role and deployed endpoint are required.');}
  finally{setLoading(false);}
 },[period]);
 React.useEffect(()=>{refresh();},[refresh]);
 return {data,loading,error,refresh};
}
function useOperatorSections(period,tab) {
 const [snapshot,setSnapshot]=React.useState({data:null,error:''});
 React.useEffect(()=>{
   let active=true;
   if(period==='overall'){setSnapshot({data:null,error:''});return()=>{active=false;};}
   const hours=period==='7d'?168:24;
   const paths=tab==='pipeline'?['funnel']:tab==='sources'?['funnel']:tab==='quality'?['funnel','stabilization','cases']:tab==='sensors'?['sar-fleet','satellite-queue']:tab==='activity'?['stream','analysis','pipeline-map']:null;
   if(!paths){setSnapshot({data:null,error:''});return()=>{active=false;};}
   Promise.allSettled(paths.map(p=>fetchJson(resolveSiteApiBase(),`/api/v1/operator/ingestion/${p}?hours=${hours}&limit=60`,undefined,18000)))
   .then(results=>{if(!active)return;const data={};let failed=0;results.forEach((v,i)=>{if(v.status==='fulfilled')data[paths[i]]=v.value;else failed++});setSnapshot({data,error:failed?'Some protected sections are unavailable.':''})});
   return()=>{active=false;};
 },[period,tab]);
 return snapshot;
}
function SimpleRecords({title,items,description}) {
 if(!Array.isArray(items)||!items.length)return <section className="future-section"><h2>{title}</h2><p>{description}</p><p>No records currently available.</p></section>;
 return <section className="future-section"><h2>{title}</h2><p>{description}</p><div className="future-intelligence-records">{items.slice(0,60).map((row,i)=><details key={row.observation_id||row.event_id||row.id||i}><summary><strong>{row.semantic_label||row.title||row.kind||row.type||'Observation'}</strong><span>{stamp(row.received_at||row.timestamp_utc||row.updated_at||row.observed_at)}</span></summary><p>Source: {row.source_name||row.source||row.kind||'Unknown'} · Evidence stage: {row.pipeline_role||row.kind||'Unspecified'}</p><p>Category: {row.observation_type||row.type||row.family||row.status||'Unspecified'}</p><p>Records in this view are observations or hypotheses, not proven incidents.</p></details>)}</div></section>
}
const qualityHelp={
 episode_to_multi_lineage:'Share of recognized episodes independently corroborated. A low rate is not a software failure by itself.',
 multi_lineage_to_review_ready:'Share of independently corroborated episodes that reached human-review readiness.',
 derived_to_episode:'Share of derived cues grouped into recognized episodes. A descriptive process ratio.',
};
function QualityDiagnostics({data}) {
 if(!data)return <section className="future-section"><h2>Quality & stabilization</h2><p>Protected quality metrics not available.</p></section>;
 const entries=Object.entries(data.rates||{});
 const checks=Object.entries(data.invariants||{});
 return <section className="future-section"><h2>Pipeline quality checks</h2><p>These are diagnostics, not scores of vessel behavior or evidence of unlawful activity.</p><div className="future-intelligence-metrics">{entries.map(([k,v])=><article className="future-intelligence-metric" key={k}><span>{k.replaceAll('_',' ')}</span><strong>{typeof v==='number'?Number(v*100).toFixed(1)+'%':String(v??'—')}</strong><p>{qualityHelp[k]||'Process rate for the selected window.'}</p></article>)}{checks.map(([k,v])=><article className="future-intelligence-metric" key={k}><span>{k.replaceAll('_',' ')}</span><strong>{typeof v==='boolean'?(v?'PASS':'CHECK'):number(v)}</strong><p>A consistency check for independent evidence lineages.</p></article>)}</div><h3>Radio decoding threshold</h3><p>The radio receiver network should not be expanded on signal volume alone: decodes must be repeatable and verifiable.</p><p>{data.radio?.scale_gate||'Decode quality threshold not reported.'}</p></section>
}
function FleetView({data}) {
 const features=Array.isArray(data?.features)?data.features:[];
 return <section className="future-section"><h2>Civil and state SAR fleet</h2><p>Registered {number(data?.meta?.total_registered)} · Live {number(data?.meta?.live_ais)} · Stale {number(data?.meta?.stale_ais)} · Offline {number(data?.meta?.offline)}. Tracker: {data?.meta?.tracking_stream?.connected?'connected':'not confirmed'}.</p><p>The fleet registry shows monitoring status, not whether a vessel is conducting rescue operations. Only recent positions may be plotted; stale coordinates remain withheld.</p>{features.length?<div className="future-intelligence-metrics">{features.map((f,i)=><article className="future-intelligence-metric" key={f.id||i}><span>{f.properties?.ship_name||f.properties?.name||'SAR asset'}</span><strong className="future-intelligence-date">{f.properties?.ais_status||'Status unknown'}</strong><p>{f.properties?.org||'Fleet registration'} · {f.properties?.operator_type==='state_authority'?'state SAR':'civil SAR'}</p></article>)}</div>:<p>{data?'The fleet response does not expose a readable feature list.':'Fleet data unavailable with current permissions.'}</p>}</section>
}
function CaseReview({data}) {
 const cases=Array.isArray(data?.cases)?data.cases:[];
 return <section className="future-section"><h2>Investigation evidence chains</h2><p>Real hypotheses, their evidence lineages and blockers. A candidate is not a criminal allegation, a SAR alert or a published case.</p>{cases.length?cases.slice(0,30).map((c,i)=><details key={c.case_id||i} className="future-intelligence-chain"><summary>{c.label||c.hypothesis_type||'Investigation'} · {c.state||'unreviewed'}</summary><p>Evidence stage: {c.evidence_stage||'not reported'} · Verification: {c.verification_status||'not reported'}</p>{Array.isArray(c.independence_groups)&&<p>Independent lineages: {c.independence_groups.join(', ')||'Not established'}</p>}{Array.isArray(c.blockers)&&<p>Why progress is blocked: {c.blockers.join(' · ')||'No blockers reported'}</p>}{Array.isArray(c.evidence)&&<p>Evidence links: {c.evidence.length} recorded references. Their existence does not establish claim truth.</p>}</details>):<p>Case evidence is unavailable with the current operator permissions or window.</p>}</section>
}
function ParserTopology({data}) {
 const chains=Array.isArray(data?.chains)?data.chains:[];
 return <section className="future-section"><h2>Source → observation → episode</h2><p>Each source passes through specific normalization, validation and correlation steps.</p>{chains.length?chains.map((c,i)=><details key={c.id||i} className="future-intelligence-chain"><summary>{c.label||c.title||c.id||'Pipeline'}</summary><p>Inputs: {(c.inputs||[]).join(' · ')||'Not specified'}</p><p>Raw observations: {(c.raw_observations||[]).join(' · ')||'Not specified'}</p><p>Checks: {(c.controls||[]).join(' · ')||'Not specified'}</p></details>):<p>Parser metadata unavailable.</p>}</section>
}
function StagePanels({rows,lookup}){
 return <div className="future-intelligence-metrics">{rows.map(([key,title,help])=><article className="future-intelligence-metric" key={key}><span>{title}</span><strong>{number(lookup?.[key])}</strong><p>{help}</p></article>)}</div>
}
export default function IntelligenceDashboard({ops,overall,period,setPeriod,navigate}){
 const [tab,setTab]=useState('pipeline');
 const operator=useOperatorMetrics(period);
 const sections=useOperatorSections(period,tab);
 const isOverall=period==='overall';
 const raw=operator.data;
 const status=!isOverall&&ops.status?.window_hours===(period==='7d'?168:24)?ops.status:null;
 const rawStages=Array.isArray(raw?.stages)?Object.fromEntries(raw.stages.map(s=>[stageKeys[s.id]||s.id,s.count])):null;
 const funnelStages=Array.isArray(sections.data?.funnel?.stages)?Object.fromEntries(sections.data.funnel.stages.map(s=>[stageKeys[s.id]||s.id,s.count])):null;
 const pipeline=isOverall?rawStages:(funnelStages||raw?.pipeline_status?.pipeline||status?.pipeline);
 const sensorsData=isOverall?raw?.sensor_activity:raw?.pipeline_status?.sensor_activity||status?.sensor_activity;
 const breakdown=isOverall?raw?.breakdowns:{
   raw_by_source:raw?.source_observations?.by_source,
   raw_observation_types:raw?.source_observations?.by_type,
   normalized_by_source:raw?.parsed_events?.by_source,
   normalized_event_types:raw?.parsed_events?.by_type,
   hypothesis_states:sections.data?.funnel?.diagnostics?.hypothesis_states,
   hypothesis_evidence_stages:sections.data?.funnel?.diagnostics?.hypothesis_evidence_stages,
   episode_verification:sections.data?.funnel?.diagnostics?.episode_verification,
   episode_families:sections.data?.funnel?.diagnostics?.episode_families,
   hypothesis_types:sections.data?.funnel?.diagnostics?.hypothesis_reason_codes,
 };
 const allStages=stages.filter(x=>x[0]!=='analysis_outputs');
 const specialSensors=isOverall&&sensorsData?{...sensorsData,active_source_names:sensorsData.source_names}:sensorsData;
 return <><section className="future-page-head"><span className="future-eyebrow">SeaCommons / Intelligence</span><h1>Evidence, from first signal to human review.</h1><p>One canonical pipeline. Follow what was collected, what software inferred and which cases have independent support. The volumes describe different evidence layers; they must not be added together.</p></section>
 <div className="future-period-tabs" aria-label="Intelligence time window"><div role="group" aria-label="Intelligence time window">{[['24h','24 hours'],['7d','7 days'],['overall','Overall']].map(([id,label])=><button type="button" aria-pressed={period===id} className={period===id?'is-active':''} onClick={()=>setPeriod(id)} key={id}>{label}</button>)}</div><small>{isOverall?'All records currently retained, irrespective of the age of the source event':period==='7d'?'Rolling seven days':'Rolling 24 hours'}</small></div>
 <nav className="future-intelligence-subnav" aria-label="Intelligence sections">{TABS.map(([key,title])=><button key={key} type="button" className={key===tab?'is-active':''} aria-current={key===tab?'page':undefined} onClick={()=>setTab(key)}>{title}</button>)}</nav>
 <div className="future-intelligence-freshness"><span>{operator.loading?'Loading operator aggregates…':operator.data?'Verified operator aggregation':operator.error?'Operator aggregation restricted · public-safe fields shown where available':'Awaiting operational data'}</span><small>{operator.data?.generated_at?'Generated '+stamp(operator.data.generated_at):'No operator snapshot available'}</small><button type="button" onClick={operator.refresh}>Refresh</button></div>
 {operator.error&&<p className="future-inline-note" role="status">{operator.error} This dashboard does not use demonstration totals or hard-coded figures.</p>}
 {tab==='pipeline'&&<><section className="future-section"><h2>01 / Canonical evidence funnel</h2><p>From raw source messages to independent corroboration and review. Raw records, normalized events, derived cues, episodes and hypotheses describe overlapping processing stages, not sequential case conversion.</p><StagePanels rows={allStages} lookup={pipeline}/></section><section className="future-section"><h2>02 / Collection context</h2><p>In the supplied operator snapshot, raw observations substantially outnumber normalized events. This is expected: high-volume AIS telemetry is filtered and grouped. The dashboard always shows current API values instead of preserving the snapshot as if it were live.</p>{isOverall&&<p>First raw intake: {stamp(raw?.first_last?.raw_first)}. Latest raw intake: {stamp(raw?.first_last?.raw_latest)}. Historical dates inside sources may predate SeaCommons.</p>}</section></>}
 {tab==='sources'&&<>{Object.entries(sourceHelp).slice(0,4).map(([key,help])=><Breakdown key={key} title={key.replaceAll('_',' ')} items={breakdown?.[key]} help={help}/>)}</>}
 {tab==='sensors'&&<><MetricSet heading="Sensors and signal coverage" rows={sensors} data={specialSensors}/><FleetView data={sections.data?.['sar-fleet']}/><section className="future-section"><h2>Satellite review queue</h2><p>Satellite candidates require independent matching and review; these do not indicate confirmed detections or distress.</p><p>Queue candidates: {number(sections.data?.['satellite-queue']?.total_candidates)}</p></section></>}
 {tab==='quality'&&<><QualityDiagnostics data={sections.data?.stabilization}/><CaseReview data={sections.data?.cases}/>{Object.entries(sourceHelp).slice(4).map(([key,help])=><Breakdown key={key} title={key.replaceAll('_',' ')} items={breakdown?.[key]} help={help}/>)}</>}
 {tab==='activity'&&<><section className="future-section"><h2>Source acquisition</h2><p>Connector health tracks input availability, not the validity of a claim.</p>{raw?.acquisition?<pre className="future-intelligence-json">{JSON.stringify(raw.acquisition,null,2)}</pre>:<p>Acquisition metadata unavailable.</p>}</section><SimpleRecords title="01 / Raw ingestion" items={sections.data?.stream?.items?.filter(x=>x.kind==='source_observation')} description="Unprocessed source observations. Reappearance after silence is telemetry, not proof of covert activity."/><SimpleRecords title="02 / Normalized events" items={sections.data?.stream?.items?.filter(x=>x.kind==='parsed_event')} description="Parsed events are standardized source observations, not validated incidents."/><SimpleRecords title="03 / Episodes and hypotheses" items={sections.data?.analysis?.items} description="Investigation candidates and recognized episodes; each requires further independent evidence."/><ParserTopology data={sections.data?.['pipeline-map']}/></>}
 {sections.error&&<p role="status">{sections.error}</p>}
 <section className="future-section"><h2>Data provenance and interpretation</h2><p>Operator figures are calculated by the same database aggregation functions as the canonical ingestion dashboard. Public fallback figures are drawn from the canonical status feed. Overall operator counts cover the retained corpus; recent values cover ingestion windows. Sensor counts may be estimated when database statistics are used, especially AIS fixes.</p><p>Source evidence is not the same as an incident. Independent corroboration and human review are required before claims become publishable.</p><button type="button" onClick={()=>navigate('history')}>Explore historical collection →</button></section>
 </>;
}
