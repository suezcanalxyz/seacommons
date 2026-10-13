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
export default function IntelligenceDashboard({ops,overall,period,setPeriod,navigate}){
 const status=ops.status?.window_hours===(period==='7d'?168:24)?ops.status:null;
 const [showTechnical,setShowTechnical]=useState(false);
 return <><section className="future-page-head"><span className="future-eyebrow">Intelligence / Observations & evidence</span><h1>What the system has actually collected.</h1><p>Start with source observations. Follow them through normalization, analysis and evidence review. Each step has a different meaning: a large number of signals is not a large number of confirmed incidents.</p></section>
 <div className="future-period-tabs" aria-label="Intelligence time window"><div role="group" aria-label="Intelligence time window">{[['24h','24 hours'],['7d','7 days'],['overall','All-time']].map(([id,label])=><button type="button" aria-pressed={period===id} className={period===id?'is-active':''} onClick={()=>setPeriod(id)} key={id}>{label}</button>)}</div><small>{period==='overall'?'All retained records, not events since SeaCommons began operations':period==='7d'?'Rolling 168 hours':'Rolling 24 hours'}</small></div>
 {period==='overall'?<section className="future-section"><header><h2>Retained historical corpus</h2></header><p>The currently available partner-safe overall API covers retained normalized Intel events. The private operator dashboard also contains all-time raw observations, source breakdowns and evidence-stage counts, but these are not exposed through this API. Unavailable values are not estimated.</p><div className="future-intelligence-metrics"><article className="future-intelligence-metric"><span>Retained normalized events</span><strong>{number(overall.history?.intel_record?.total_events)}</strong><p>Canonical Intel event records retained, regardless of the age of the historical events described.</p></article><article className="future-intelligence-metric"><span>Records with coordinates</span><strong>{number(overall.history?.intel_record?.positioned_events)}</strong><p>Records with stored latitude data; not necessarily verified incident locations.</p></article></div><p className="future-data-provenance">Data retrieved: {stamp(overall.updatedAt)}. {overall.error||''}</p><button type="button" onClick={()=>navigate('history')}>Explore history →</button></section>:<>
 <div className="future-intelligence-freshness"><span>{ops.loading?'Loading updated measurements…':ops.error?'Some measurements unavailable; last verified snapshot where present.':'Canonical status feed'}</span><small>Generated {stamp(status?.generated_at)} · Last retrieval {stamp(ops.updatedAt)}</small><button type="button" onClick={ops.refresh}>Refresh</button></div>
 <MetricSet heading="01 / Evidence processing" rows={stages} data={status?.pipeline}/>
 <MetricSet heading="02 / Sensors & source activity" rows={sensors} data={status?.sensor_activity}/>
 <section className="future-section"><header><h2>03 / Data freshness</h2></header><div className="future-intelligence-metrics">{freshness.map(([key,title,meaning])=><article className="future-intelligence-metric" key={key}><span>{title}</span><strong className="future-intelligence-date">{stamp(status?.freshness?.[key])}</strong><p>{meaning}</p></article>)}</div></section>
 <section className="future-section"><header><h2>04 / Where the numbers come from</h2></header><p>Futures reads the public-safe status API. The operator ingestion dashboard provides additional restricted source breakdowns, acquisition channels and case-level review tools. Those private details should only be added behind server-enforced partner permissions, never by storing an operator gateway secret in the frontend.</p><button type="button" onClick={()=>setShowTechnical(!showTechnical)} aria-expanded={showTechnical}>{showTechnical?'Hide':'Show'} API mapping</button>{showTechnical&&<div className="future-intelligence-legend"><p><code>/api/v1/status?hours={period==='7d'?168:24}</code> supplies the recent evidence funnel, sensor counters and freshness. Private operator routes use different permissions and scopes; similarly named metrics can differ between contracts.</p><p>The all-time public endpoint <code>/api/v1/futures/overall</code> currently returns normalized events only, not the private operator’s complete corpus inventory.</p></div>}</section>
 </>}
 </>;
}
