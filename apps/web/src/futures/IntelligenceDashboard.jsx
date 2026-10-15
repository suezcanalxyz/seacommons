import React, {useState} from 'react';

const stages=[
  ['raw_observations','Raw observations','Source records received by SeaCommons. They are raw inputs, not confirmed events.'],
  ['parsed_events','Normalized events','Records converted into the standard SeaCommons format so sources can be compared.'],
  ['derived_cues','Derived cues','Possible patterns detected by rules or models. A cue is a lead, not proof.'],
  ['maritime_episodes','Recognized episodes','Groups of related maritime observations that can be investigated together.'],
  ['investigation_hypotheses','Hypotheses','Questions or possible explanations being evaluated, not conclusions.'],
  ['corroborated_episodes','Corroborated episodes','Episodes supported by at least two independent evidence lineages.'],
  ['review_ready','Ready for review','Investigations prepared for human assessment. This does not establish wrongdoing.'],
  ['public_live','Public Live','Signals currently eligible for public Live publication. A zero is possible even with high ingestion because publication requires separate safeguards.'],
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
function number(value){return value===null||value===undefined?'Unavailable':Number.isFinite(Number(value))?new Intl.NumberFormat('en-GB').format(Number(value)):'Unavailable'}
function stamp(value){if(!value)return 'Unavailable';const d=new Date(value);return Number.isNaN(d.getTime())?'Unavailable':d.toLocaleString()}
function MetricSet({heading,rows,data}) {const [expanded,setExpanded]=useState(null);return <section className="future-section"><header><h2>{heading}</h2></header><div className="future-intelligence-metrics">{rows.map(([key,label,meaning])=><article key={key} className="future-intelligence-metric"><div className="future-intelligence-metric-top"><span><GlossaryTerm label={label}/></span><button type="button" aria-expanded={expanded===key} aria-label={'Explain '+label} onClick={()=>setExpanded(expanded===key?null:key)}>What is this? {expanded===key?'−':'+'}</button></div><strong>{number(data?.[key])}</strong><p>{meaning}</p>{expanded===key&&<div className="future-intelligence-legend"><b>How to read it</b><p>{meaning} The number belongs to its own evidence stage; it is not directly comparable to a case or vessel count. Missing means unavailable, not zero.</p><small>API field: {key}</small></div>}</article>)}</div></section>}

import { fetchJson } from '../services/api/client.js';
import { resolveSiteApiBase } from '../site/liveApi.js';

const TABS = [['pipeline','Evidence pipeline'],['sources','Sources & types'],['quality','Evidence quality'],['sensors','Sensors & SAR'],['activity','Acquisition & logs']];
const stageKeys={raw:'raw_observations',normalized:'parsed_events',derived:'derived_cues',episodes:'maritime_episodes',hypotheses:'investigation_hypotheses',corroborated:'corroborated_episodes',review_ready:'review_ready',live:'public_live'};
const stageDescriptions=Object.fromEntries(stages.map(s=>[s[0],s[2]]));
const sourceHelp={
  raw_by_source:'Who supplied the original observations. Sources can have different collection rates.',
  raw_observation_types:'Types of source observations before standardization, including AIS and public reports.',
  normalized_by_source:'Source attribution on processed Intel events. This is not the raw ingestion count.',
  normalized_event_types:'Types assigned to standardized events after parsing and classification.',
  episode_families:'Kinds of related maritime observations recognized by the correlation engine.',
  episode_verification:'Verification of episodes: one source, multiple indicators, or independent lineages.',
  hypothesis_types:'Investigation topics; counts are not findings of illegal activity.',
  hypothesis_counter_indicators:'Evidence pointing to innocent or alternative explanations, or against the current hypothesis.',
  hypothesis_states:'Processing state of hypotheses: collecting, candidate or ready for review.',
  hypothesis_evidence_stages:'Highest evidence level reached by each hypothesis.'
};
const termGlossary={
 ais_gap:'An AIS transmission was observed again after sampled silence. This is telemetry, not proof of deliberate concealment.',
 ais_nav_status:'Navigation status reported by AIS, including voyage and safety-related status messages.',
 remote_radio_signal:'A radio burst observed by a remote receiver; its contents may not be decoded.',
 ais_derived_event:'A vessel-related event derived through AIS processing and other data checks.',
 sanctions_list_match:'Potential identity match against a sanctions list; requires strong identifier verification.',
 source_post:'A collected source post, which retains provenance but does not prove its claims.',
 media_attachment:'A media item attached to a source observation, tracked separately from written content.',
 dsc_message:'Digital Selective Calling message from maritime radio; validity and association require review.',
 ais_spike:'An unusual AIS movement or position feature selected for further analysis.',
 correlated_alert:'A software correlation between potentially related source records; not an independently corroborated incident.',
 ais_rendezvous:'A proximity or meeting-related AIS cue; normal operations can explain the pattern.',
 ais_anomaly:'An AIS-integrity cue that can arise from reception, equipment, or movement.',
 vessel_identity:'A recorded change or inconsistency in vessel identification.',
 vessel_incident:'An event described as involving a vessel; it requires independent verification.',
 distress:'A distress-related report or status, not automatically a verified rescue case.',
 rendezvous_episode:'A grouped sequence of possible vessel meeting observations.',
 gap_episode:'A grouped AIS continuity episode, not a finding of intentional dark activity.',
 spoofing_episode:'An episode concerning possible position-integrity issues; equipment or reception errors remain alternatives.',
 unclassified_episode:'An episode that has not yet received a recognized evidence family.',
 identity_integrity_episode:'A grouped episode concerning possible vessel identity inconsistency.',
 safety_episode:'A group of safety or navigation-related observations.',
 dark_transit:'A hypothesis assessing a vessel-specific AIS gap; requires contextual and independent evidence.',
 position_spoofing:'A hypothesis examining possible false position information.',
 covert_rendezvous:'A hypothesis about a possible unreported meeting; not proof of unlawful intent.',
 infrastructure_pattern:'A hypothesis assessing possible activity near maritime infrastructure.',
 single_source_observed:'An episode supported by one source only.',
 single_source_multi_indicator:'Multiple indicators from one source, which are not independent corroboration.',
 multi_source_corroborated:'At least two independently originated evidence lineages support the episode.',
 collecting:'An investigation is still gathering evidence.',
 candidate:'An investigation hypothesis is a candidate for additional checks.',
 review_ready:'Evidence prepared for human review, not a published finding.',
 derived:'A rule or model produced a cue, not an independently verified claim.'
};
function termDescription(key){return termGlossary[key]||'Category recorded by the canonical pipeline. The count is descriptive and does not by itself verify an incident.';}
function Breakdown({title,items,help}) {
 const entries=Object.entries(items||{}).filter(([,n])=>Number.isFinite(Number(n))).sort((a,b)=>Number(b[1])-Number(a[1]));
 const max=Math.max(1,...entries.map(x=>Number(x[1])));
 return <section className="future-section future-intelligence-breakdown"><h2>{title}</h2><p>{help}</p>{entries.length?<div className="future-intelligence-bars">{entries.map(([key,value])=><div className="future-intelligence-bar" key={key}><span title={key}>{key.replaceAll('_',' ')}</span><div><i style={{width:Math.max(1,100*Number(value)/max)+'%'}}/></div><strong>{number(value)}</strong><small>{termDescription(key)}</small></div>)}</div>:<p>No breakdown currently available for this period.</p>}</section>
}
function useOperatorMetrics(period){
 const [snapshot,setSnapshot]=React.useState({period:null,data:null,loading:true,error:'',source:null});
 const seq=React.useRef(0);
 const refresh=React.useCallback(async()=>{
  const request=++seq.current;
  // Never show a previous window's numbers or timestamp as current.
  setSnapshot({period,data:null,loading:true,error:'',source:null});
  const accept=(data,source)=>{
   if(request===seq.current)setSnapshot({period,data,source,loading:false,error:''});
  };
  const fail=()=>{
   if(request===seq.current)setSnapshot({period,data:null,source:null,loading:false,error:'Metrics could not be loaded for this period. Please retry.'});
  };
  try{
   const url=period==='overall'?'/api/v1/operator/ingestion/overall-metrics':`/api/v1/operator/ingestion/overview?hours=${period==='7d'?168:24}`;
   const result=await fetchJson(resolveSiteApiBase(),url,undefined,period==='overall'?35000:30000);
   const valid=period==='overall'
    ? result?.scope==='all_time'&&Array.isArray(result?.stages)&&result?.sensor_activity
    : result?.lookback_hours===(period==='7d'?168:24)&&result?.pipeline_status?.pipeline;
   if(!valid)throw new Error('Unexpected measurement contract');
   accept(result,'operator');
  }catch{
   try{
    if(period==='overall'){
     const historical=await fetchJson(resolveSiteApiBase(),'/api/v1/operator/ingestion/overall',undefined,26000);
     if(historical?.scope!=='all_time'||!Array.isArray(historical?.stages))throw new Error('Unexpected historical contract');
     accept(historical,'historical');
    }else{
     const hours=period==='7d'?168:24;
     const status=await fetchJson(resolveSiteApiBase(),`/api/v1/status?hours=${hours}`,undefined,30000);
     if(status?.window_hours!==hours||!status?.pipeline)throw new Error('Unexpected public status contract');
     accept({lookback_hours:hours,generated_at:status.generated_at,pipeline_status:{pipeline:status.pipeline,sensor_activity:status.sensor_activity},fallback_public:true},'public');
    }
   }catch{fail();}
  }
 },[period]);
 React.useEffect(()=>{refresh();return()=>{seq.current+=1;};},[refresh]);
 return snapshot.period===period?{...snapshot,refresh}:{period,data:null,source:null,loading:true,error:'',refresh};
}
function useOperatorSections(period,tab) {
 const [snapshot,setSnapshot]=React.useState({data:null,error:'',key:''});
 React.useEffect(()=>{
   let active=true;
   if(period==='overall'){
    if(tab!=='sources'&&tab!=='quality'){setSnapshot({data:null,error:'',key:period+':'+tab});return()=>{active=false;};}
    setSnapshot({data:null,error:'',key:period+':'+tab});
    fetchJson(resolveSiteApiBase(),'/api/v1/operator/ingestion/overall',undefined,50000)
      .then(overall=>{if(active)setSnapshot({data:{overall},error:'',key:period+':'+tab});})
      .catch(()=>{if(active)setSnapshot({data:null,error:'Historical breakdown is temporarily unavailable. The main indicators remain accessible.',key:period+':'+tab});});
    return()=>{active=false;};
   }
   const hours=period==='7d'?168:24;
   const paths=tab==='pipeline'?[]:tab==='sources'?['funnel']:tab==='quality'?['funnel','stabilization','cases']:tab==='sensors'?['sar-fleet','satellite-queue','humanitarian-ais-correlation']:tab==='activity'?['observations','events','signals','analysis','pipeline-map']:null;
   if(!paths||!paths.length){setSnapshot({data:{},error:'',key:period+':'+tab});return()=>{active=false;};}
   setSnapshot({data:null,error:'',key:period+':'+tab});
   Promise.allSettled(paths.map(p=>fetchJson(resolveSiteApiBase(),`/api/v1/operator/ingestion/${p}?hours=${hours}&limit=60`,undefined,18000)))
   .then(results=>{if(!active)return;const data={};let failed=0;results.forEach((v,i)=>{if(v.status==='fulfilled')data[paths[i]]=v.value;else failed++});setSnapshot({data,error:failed?'Some detailed evidence views are temporarily unavailable.':'',key:period+':'+tab})});
   return()=>{active=false;};
 },[period,tab]);
 return snapshot.key===period+':'+tab ? snapshot : {data:null,error:''};
}

const measurementRows=[
 ['observations_received','Raw received','Original source envelopes received during this time window.'],
 ['events_received','Normalized received','Standardized records received. Not a percentage conversion of raw observations.'],
 ['events_created','Normalized created','New normalized event rows inserted during this time window.'],
 ['investigations_created','New investigations','Hypotheses first created in this window, excluding those now expired or rejected.'],
 ['investigations_updated','Investigations updated','Existing or newly created hypotheses whose latest saved update falls inside the window. Repeat processing can change this.'],
 ['investigations_open_now','Current non-expired investigations','Current stock of hypotheses not expired or rejected, including assessed and published records. Not a windowed activity total.'],
 ['investigations_rejected_or_expired_updated','Excluded hypotheses updated','Rejected or expired hypotheses whose last update occurred in the window; not included in active investigations.'],
 ['episodes_created','New episodes','Classified episodes first created in this window.'],
 ['episodes_updated','Episodes updated','Classified episodes last modified in this window; older episodes may be included.'],
 ['corroborated_episodes_updated','Corroborated episodes updated','Episodes with independent-lineage corroboration and a recent update, not new corroboration transitions.'],
 ['investigations_review_ready_updated','Review-ready hypotheses updated','Hypotheses in review-ready, assessed or published state and modified within the window.'],
 ['ais_positions_observed','AIS positions observed','Stored vessel positions timestamped by the AIS source in the selected window.'],
 ['ais_positions_received','AIS positions received','AIS track rows actually received by SeaCommons in the selected window.'],
];
function MeasurementContract({period}) {
 const [state,setState]=React.useState({period:null,data:null,loading:true,error:''});
 React.useEffect(()=>{
  if(period==='overall'){setState({period,data:null,loading:false,error:''});return;}
  let alive=true;const hours=period==='7d'?168:24;
  setState({period,data:null,loading:true,error:''});
  fetchJson(resolveSiteApiBase(),`/api/v1/operator/ingestion/measurements?hours=${hours}`,undefined,30000)
   .then(data=>{if(alive)setState({period,data,loading:false,error:''});})
   .catch(()=>{if(alive)setState({period,data:null,loading:false,error:'Measurement contract unavailable. Historical aggregates below remain separate.'});});
  return()=>{alive=false;};
 },[period]);
 const data=state.period===period?state.data:null;
 return <section className="future-section" aria-label="Measurement definitions">
  <h2>Measurement contract / what these numbers actually mean</h2>
  <p>One as-of time, distinct clocks. A new investigation is not the same as an updated one. The current open total is a stock, not a windowed activity total.</p>
  {period==='overall'?<p>Overall shows retained records. It is not an immutable historical ingestion total. Created-versus-updated measures apply to the 24-hour and 7-day windows.</p>:<>
   <p className="future-data-provenance">{state.loading?'Loading canonical measurements…':state.error||'As of '+stamp(data?.as_of)+' · window start '+stamp(data?.window_start)+' · contract v'+(data?.contract_version||'?')}</p>
   <div className="future-intelligence-metrics">{measurementRows.map(([key,title,desc])=><article className="future-intelligence-metric" key={key}>
    <span>{title}</span><strong>{state.loading?'Loading…':number(data?.counts?.[key])}</strong>
    <p>{desc}</p><small>Clock: {data?.definitions?.[key]?.clock||'not available'}</small>
   </article>)}</div>
   {data?.sources&&<Breakdown title="Contributing raw sources" items={data.sources} help="Source groups count original observations received within the same period. Multiple source families need not generate equivalent numbers of normalized events."/>}
  </>}
  <p className="future-data-provenance">Rows are not additive. Historical data, current states, model cues and published cases represent different populations. Updated rows can reflect automated reprocessing without new evidence.</p>
 </section>;
}
const headlineMetrics=[
 ['raw_observations','Raw observations','Original source records received in the period, before normalization.'],
 ['parsed_events','Normalized events','Source data converted into comparable Intel events. This is not an incident count.'],
 ['derived_cues','Derived cues','Events flagged by analytical rules or models after legacy-gap exclusions. Leads, not findings.'],
 ['maritime_episodes','Recognized episodes','Classified clusters of related observations; for 24h/7d, those updated in the window.'],
 ['investigation_hypotheses','Investigation hypotheses','Non-expired/non-rejected hypotheses last updated in the selected window; not necessarily newly created. Overall includes retained historical hypotheses.'],
 ['corroborated_episodes','Corroborated episodes','Classified episodes currently supported by independent evidence lineages; recent counts use last update.'],
 ['review_ready','Review ready','Hypotheses now in review-ready, assessed or published state; recent counts use last update. Not verified wrongdoing.'],
 ['ais_fixes','AIS positions','Stored AIS position records timestamped within the selected window. Overall may be an estimate.'],
 ['radio_bursts','Radio bursts','Captured radio bursts, including transmissions that could not be decoded.'],
 ['radio_events','Radio events','Radio observations decoded or turned into usable events. Not all bursts qualify.'],
 ['satellite_observations','Satellite observations','Satellite observations discovered by the system, not all images available.'],
 ['active_source_names','Active source names','Number of distinct sources contributing retained raw observations in the selected period.'],
];
const termExplanations={
 'AIS positions':'Automatic Identification System positions reported by vessels and received by monitoring networks. A missing position does not by itself prove concealment.',
 'Derived cues':'Signals flagged by analytical rules or models as worthy of examination. These are leads, not confirmed incidents.',
 'Corroborated episodes':'Related observations with supporting evidence from genuinely independent source lineages.',
 'Investigation hypotheses':'Possible explanations being evaluated. They are not confirmed events or allegations.',
 'Normalized events':'Incoming records translated into a shared schema so independent formats can be compared without losing their origin.',
 'Radio bursts':'Short received radio transmissions or fragments, including those not yet decoded into meaningful events.',
 'Review ready':'Material organized for human examination. It does not imply that the investigation has reached a conclusion.',
};
const metricClocks={
 raw_observations:'received_at',parsed_events:'received_at',derived_cues:'received_at',
 maritime_episodes:'updated_at',investigation_hypotheses:'updated_at',
 corroborated_episodes:'updated_at',review_ready:'updated_at',
 ais_fixes:'AIS observation time',radio_bursts:'created_at',radio_events:'created_at',
 satellite_observations:'discovered_at',active_source_names:'received_at (distinct sources)',
};
function GlossaryTerm({label}){
 const meaning=termExplanations[label];
 const [expanded,setExpanded]=useState(false);
 const tooltipId=React.useId();
 if(!meaning)return label;
 return <span className={'future-glossary-wrap'+(expanded?' is-open':'')}>
  <button type="button" className="future-glossary-term" aria-expanded={expanded} aria-describedby={tooltipId}
   onClick={()=>setExpanded(open=>!open)} onKeyDown={event=>{if(event.key==='Escape')setExpanded(false)}}
   onBlur={()=>setExpanded(false)}>{label}</button>
  <span className="future-glossary-definition" id={tooltipId} role="tooltip">{meaning}</span>
 </span>;
}
function IntelligenceMetricGrid({period,pipeline,sensorsData,loadedAt,estimatedFields=[],loading=false,source=null}) {
 const [expanded,setExpanded]=useState(null);
 const measurements={...sensorsData,...pipeline};
 const overall=period==='overall';
 const scopeText=overall?'Retained records, subject to data retention':period==='7d'?'Rolling 7 days':'Rolling 24 hours';
 const countsAvailable=headlineMetrics.filter(([key])=>measurements?.[key]!==null&&measurements?.[key]!==undefined).length;
 const report=loading?'Updating measurements':countsAvailable===0?'Measurements unavailable':countsAvailable<12?'Partial measurements':'Measurements available';
 return <section className="future-section future-intelligence-headline" aria-label="Intelligence metric dashboard" aria-busy={loading}>
   <header className="future-kpi-heading"><div><span className="future-eyebrow">Intelligence / measurements</span><h2>Evidence activity</h2></div>
    <p>{scopeText} · 12 distinct measures, never additive. Select a term for its definition; expand Info for its counting method.</p></header>
   <p className="future-metric-status" role="status" aria-live="polite">{report}{!loading&&source==='public'?' · public operational summary':''}{!loading&&countsAvailable>0?' · '+countsAvailable+' of 12 measures available':''}</p>
   <div className="future-intelligence-metrics future-intelligence-unified-grid">{headlineMetrics.map(([key,label,definition])=>{
    const value=measurements?.[key];
    const hasValue=value!==null&&value!==undefined&&Number.isFinite(Number(value));
    const isEstimated=estimatedFields.includes(key)||key==='ais_fixes'&&overall&&estimatedFields.includes('ais_fixes');
    const clock=overall?'Retained record inventory':metricClocks[key]||'Source-defined time';
    return <article className={'future-intelligence-metric'+(!loading&&!hasValue?' is-unavailable':'')} key={key}>
     <div className="future-intelligence-metric-top"><span><GlossaryTerm label={label}/></span>
      <button type="button" aria-expanded={expanded===key} aria-label={'Counting method for '+label}
       onClick={()=>setExpanded(expanded===key?null:key)}>{expanded===key?'Close −':'Info +'}</button></div>
     <strong className={loading?'future-metric-loading':''} data-metric={key}>{loading?'Loading…':hasValue?(isEstimated?'≈ ':'')+number(value):'Unavailable'}</strong>
     <p>{definition}</p>
     {expanded===key&&<div className="future-intelligence-legend"><b>Counting method</b>
      <p><b>Time basis:</b> {clock}. {overall?'Counts describe the currently retained database, not every observation ever received.':'Records are assigned to this window using the indicated time field.'}</p>
      <p>{!loading&&!hasValue?'This measure cannot currently be established; it is not zero.':isEstimated?'This is a database estimate, not an exact row count.':'This number describes records or analytical states, not verified maritime incidents.'}</p>
     </div>}
    </article>;
   })}</div>
   <p className="future-data-provenance">{scopeText} · Last source update: {stamp(loadedAt)}{estimatedFields.length?' · Estimates marked ≈':''}. An unavailable value never means zero.</p>
 </section>;
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
 if(!data)return <section className="future-section future-empty-insight"><h2>Quality & stabilization</h2><p>Quality checks show how observations are screened for consistency and how independently sourced information is evaluated. Detailed results are not yet available for this period.</p></section>;
 const entries=Object.entries(data.rates||{});
 const checks=Object.entries(data.invariants||{});
 return <section className="future-section"><h2>Pipeline quality checks</h2><p>These are diagnostics, not scores of vessel behavior or evidence of unlawful activity.</p><div className="future-intelligence-metrics">{entries.map(([k,v])=><article className="future-intelligence-metric" key={k}><span>{k.replaceAll('_',' ')}</span><strong>{typeof v==='number'?Number(v*100).toFixed(1)+'%':String(v??'—')}</strong><p>{qualityHelp[k]||'Process rate for the selected window.'}</p></article>)}{checks.map(([k,v])=><article className="future-intelligence-metric" key={k}><span>{k.replaceAll('_',' ')}</span><strong>{typeof v==='boolean'?(v?'PASS':'CHECK'):number(v)}</strong><p>A consistency check for independent evidence lineages.</p></article>)}</div><h3>Radio decoding threshold</h3><p>The radio receiver network should not be expanded on signal volume alone: decodes must be repeatable and verifiable.</p><p>{data.radio?.scale_gate||'Decode quality threshold not reported.'}</p></section>
}
function SatelliteCandidates({data}) {
 const items=Array.isArray(data?.items)?data.items:[];
 return <section className="future-section"><h2>Satellite coverage review queue</h2><p>These candidates indicate imagery that may overlap a maritime episode in space and time. Coverage is context for analysis; it is not evidence that a particular vessel was detected.</p><p>{number(data?.total_candidates)} candidates in this window · {number(data?.count)} returned for review.</p>{items.length?<div className="future-intelligence-records">{items.map((x,i)=><details key={x.episode_id||i}><summary><strong>{String(x.episode_family||'Episode').replaceAll('_',' ')}</strong><span>Priority {typeof x.priority_score==='number'?x.priority_score.toFixed(2):'unknown'}</span></summary><p>{number(x.scene_count)} relevant scenes · nearest time difference {number(x.nearest_delta_hours)} hours.</p><p>Status: {x.evidence_role||'context only'} · verification: {x.verification_status||'not independently confirmed'}</p><p>Coverage candidates do not identify vessels or corroborate an allegation without additional evidence.</p></details>)}</div>:<p>No satellite coverage candidates were returned, or access is unavailable.</p>}</section>
}
function HumanitarianCorrelation({data}) {
 const items=Array.isArray(data?.items)?data.items:[];
 return <section className="future-section"><h2>Humanitarian reports & AIS context</h2><p>Cross-checks between reports and nearby AIS tracks help investigators prioritize review. Distance and timing alone cannot identify a rescue vessel or prove involvement in an incident.</p><p>{number(data?.count)} geolocated reports with candidate associations. Search radius: {number(data?.radius_nm)} nautical miles; time window: {number(data?.window_hours)} hours.</p>{items.length?<div className="future-intelligence-records">{items.slice(0,30).map((x,i)=><details key={x.event_id||i}><summary><strong>{x.title||'Humanitarian source report'}</strong><span>{stamp(x.timestamp_utc)}</span></summary><p>Reported by {x.source||'source unavailable'} · {number(x.candidate_count)} contextual AIS associations.</p><p>Possible association does not confirm an incident, vessel identity, rescue action or wrongdoing.</p></details>)}</div>:<p>No contextual matches are reported for this window, or protected data are unavailable.</p>}</section>
}
function FleetView({data}) {
 const features=Array.isArray(data?.features)?data.features:[];
 return <section className="future-section"><h2>Civil and state SAR fleet</h2><p>Registered {number(data?.meta?.total_registered)} · Live {number(data?.meta?.live_ais)} · Stale {number(data?.meta?.stale_ais)} · Offline {number(data?.meta?.offline)}. Tracker: {data?.meta?.tracking_stream?.connected?'connected':'not confirmed'}.</p><p>The fleet registry shows monitoring status, not whether a vessel is conducting rescue operations. Only recent positions may be plotted; stale coordinates remain withheld.</p>{features.length?<div className="future-intelligence-metrics">{features.map((f,i)=><article className="future-intelligence-metric" key={f.id||i}><span>{f.properties?.ship_name||f.properties?.name||'SAR asset'}</span><strong className="future-intelligence-date">{f.properties?.ais_status||'Status unknown'}</strong><p>{f.properties?.org||'Fleet registration'} · {f.properties?.operator_type==='state_authority'?'state SAR':'civil SAR'}</p></article>)}</div>:<p>{data?'The fleet response does not expose a readable feature list.':'Fleet data unavailable with current permissions.'}</p>}</section>
}
function AcquisitionHealth({items}) {
 const rows=Array.isArray(items)?items:[];
 const meanings={live:'Feed reporting recent activity; it does not certify every observation.',degraded:'Feed is connected with partial coverage or a known limitation.',offline:'No active telemetry from this feed at the current check.',disabled:'This source has been intentionally disabled.'};
 return <section className="future-section"><h2>Acquisition health</h2><p>Connection states describe ingestion health, not the truth of reports or the safety status of any vessel.</p>{rows.length?<div className="future-intelligence-metrics">{rows.map((r,i)=><article className="future-intelligence-metric" key={r.family||i}><span>{r.label||r.family||'Source'}</span><strong className="future-intelligence-date">{r.state||'unknown'}</strong><p>{meanings[r.state]||'Current connection status is not available.'}</p></article>)}</div>:<p>Acquisition health is not available from this response.</p>}</section>
}
function CaseReview({data}) {
 const cases=Array.isArray(data?.cases)?data.cases:[];
 return <section className="future-section"><h2>Investigation evidence chains</h2><p>Real hypotheses, their evidence lineages and blockers. A candidate is not a criminal allegation, a SAR alert or a published case.</p>{cases.length?cases.slice(0,30).map((c,i)=><details key={c.case_id||i} className="future-intelligence-chain"><summary>{c.label||c.hypothesis_type||'Investigation'} · {c.state||'unreviewed'}</summary><p>Evidence stage: {c.evidence_stage||'not reported'} · Verification: {c.verification_status||'not reported'}</p>{Array.isArray(c.independence_groups)&&<p>Independent lineages: {c.independence_groups.join(', ')||'Not established'}</p>}{Array.isArray(c.blockers)&&<p>Why progress is blocked: {c.blockers.join(' · ')||'No blockers reported'}</p>}{Array.isArray(c.evidence)&&<p>Evidence links: {c.evidence.length} recorded references. Their existence does not establish claim truth.</p>}</details>):<p className="future-empty-description">No reviewable evidence-chain details were returned for this period. This does not imply zero investigations.</p>}</section>
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
 const expectedHours=period==='7d'?168:24;
 const raw=operator.data && (isOverall ? operator.data.scope==='all_time' : operator.data.lookback_hours===expectedHours) ? operator.data : null;
 const status=!isOverall&&ops.status?.window_hours===(period==='7d'?168:24)?ops.status:null;
 const rawStages=Array.isArray(raw?.stages)?Object.fromEntries(raw.stages.map(s=>[stageKeys[s.id]||s.id,s.count])):null;
 const funnelStages=Array.isArray(sections.data?.funnel?.stages)?Object.fromEntries(sections.data.funnel.stages.map(s=>[stageKeys[s.id]||s.id,s.count])):null;
 const pipeline=isOverall?rawStages:(raw?.pipeline_status?.pipeline||status?.pipeline||funnelStages);
 const sensorsData=isOverall?raw?.sensor_activity:(raw?.pipeline_status?.sensor_activity||status?.sensor_activity);
 const breakdown=isOverall?sections.data?.overall?.breakdowns:{
   raw_by_source:raw?.source_observations?.by_source,
   raw_observation_types:raw?.source_observations?.by_type,
   normalized_by_source:raw?.parsed_events?.by_source,
   normalized_event_types:raw?.parsed_events?.by_type,
   hypothesis_states:sections.data?.funnel?.diagnostics?.hypothesis_states,
   hypothesis_evidence_stages:sections.data?.funnel?.diagnostics?.hypothesis_evidence_stages,
   episode_verification:sections.data?.funnel?.diagnostics?.episode_verification,
   episode_families:sections.data?.funnel?.diagnostics?.episode_families,
   hypothesis_types:sections.data?.funnel?.diagnostics?.hypothesis_reason_codes,
   hypothesis_counter_indicators:sections.data?.funnel?.diagnostics?.hypothesis_counter_indicators,
 };
 const allStages=stages.filter(x=>x[0]!=='analysis_outputs'&&(!isOverall||x[0]!=='public_live'));
 const specialSensors=isOverall&&sensorsData?{...sensorsData,active_source_names:sensorsData.source_names}:sensorsData;
 return <><div className="future-intelligence-tagline"><span className="future-eyebrow">SeaCommons / Intelligence</span><span>Collection · inference · review</span></div>
 <div className="future-period-tabs" aria-label="Intelligence time window"><div role="group" aria-label="Intelligence time window">{[['24h','24 hours'],['7d','7 days'],['overall','Overall']].map(([id,label])=><button type="button" aria-pressed={period===id} className={period===id?'is-active':''} onClick={()=>setPeriod(id)} key={id}>{label}</button>)}</div><small>{isOverall?'All records currently retained, irrespective of the age of the source event':period==='7d'?'Rolling seven days':'Rolling 24 hours'}</small></div>

 <div className="future-intelligence-freshness"><span>{operator.loading?'Updating metrics…':operator.data?(operator.source==='public'?'Public evidence summary':'Evidence updated'):operator.error?'Evidence temporarily unavailable':'Loading evidence'}</span><small>{operator.data?.generated_at?'Generated '+stamp(operator.data.generated_at):'Updates pending'}</small><button type="button" onClick={operator.refresh}>Refresh</button></div>
 {operator.error&&<p className="future-inline-note" role="status">{operator.error} Please try refreshing the data.</p>}
 <IntelligenceMetricGrid period={period} pipeline={pipeline} sensorsData={specialSensors} loadedAt={raw?.generated_at||status?.generated_at} loading={operator.loading} source={operator.source} estimatedFields={isOverall?raw?.estimated_fields|| (sensorsData?.ais_fixes_estimated?['ais_fixes']:[]):[]}/>
 <section className="future-intelligence-explainer" aria-label="Intelligence evidence guide"><div><span className="future-eyebrow">Reading the data</span><h2>From signals to assessed evidence</h2></div><p>Raw intake counts information received, normalized records make sources comparable, and analytical cues highlight leads. Episodes group related observations; investigations remain hypotheses until their evidence and uncertainty have been assessed. These layers overlap, so counts are never added together.</p></section>
 <nav className="future-intelligence-subnav" aria-label="Intelligence sections">{TABS.map(([key,title])=><button key={key} type="button" aria-pressed={key===tab} className={key===tab?'is-active':''} onClick={()=>setTab(key)}>{title}</button>)}</nav>
 {tab==='pipeline'&&<section className="future-section future-intelligence-explanation"><h2>How to read the evidence pipeline</h2><p>Read each card according to its measurement clock, source and evidential threshold. Received records describe intake, updated episodes and hypotheses describe processing activity, and corroborated episodes are a separate verification state.</p><details><summary>Measurement clocks, confidence and limitations</summary><p>Received measures ingestion time; created measures new records; updated includes previous records processed again; observed uses the source timestamp. Consequently an investigation updated today is not necessarily new. Missing data never means zero.</p><p>24 hours and 7 days are rolling windows. Overall counts retained records, not immutable lifetime intake. AIS historical counts may use database estimates. Publication requires separate safeguards, so corroboration and review readiness are not public incident totals.</p>{isOverall&&<p>First stored intake: {stamp(raw?.first_last?.raw_first)}. Latest stored intake: {stamp(raw?.first_last?.raw_latest)}.</p>}</details></section>}
 {tab==='sources'&&<>{Object.entries(sourceHelp).slice(0,4).map(([key,help])=><Breakdown key={key} title={key.replaceAll('_',' ')} items={breakdown?.[key]} help={help}/>)}</>}
 {tab==='sensors'&&<><MetricSet heading="Sensors and signal coverage" rows={sensors} data={specialSensors}/><FleetView data={sections.data?.['sar-fleet']}/><SatelliteCandidates data={sections.data?.['satellite-queue']}/><HumanitarianCorrelation data={sections.data?.['humanitarian-ais-correlation']}/></>}
 {tab==='quality'&&<><section className="future-section future-quality-summary"><h2>Evidence quality</h2><p>Verification, independent lineages and investigation readiness. Figures above are evidence activity, not findings.</p>{!sections.data?.stabilization&&!sections.data?.cases&&<p className="future-empty-description">This view compares source reliability, evidence independence and the readiness of cases for human assessment. No detailed quality assessment is available for this period.</p>}</section>{sections.data?.stabilization&&<QualityDiagnostics data={sections.data.stabilization}/>}{sections.data?.cases&&<CaseReview data={sections.data.cases}/>}{Object.entries(sourceHelp).slice(4).filter(([key])=>breakdown?.[key]&&Object.keys(breakdown[key]).length>0).map(([key,help])=><Breakdown key={key} title={key.replaceAll('_',' ')} items={breakdown[key]} help={help}/>)}</>}
 {tab==='activity'&&<><AcquisitionHealth items={raw?.acquisition}/><SimpleRecords title="01 / Raw ingestion" items={sections.data?.observations?.observations} description="Unprocessed source observations. Reappearance after silence is telemetry, not proof of covert activity."/><SimpleRecords title="02 / Normalized events" items={sections.data?.events?.events} description="Parsed events are standardized source observations, not validated incidents."/><SimpleRecords title="Incoming partner signals" items={sections.data?.signals?.signals} description="External connector inputs are source material, not verified humanitarian or maritime incidents."/><SimpleRecords title="03 / Episodes and hypotheses" items={sections.data?.analysis?.items} description="Investigation candidates and recognized episodes; each requires further independent evidence."/><ParserTopology data={sections.data?.['pipeline-map']}/></>}
 {sections.error&&<p role="status">{sections.error}</p>}
 <section className="future-section"><h2>Data provenance and interpretation</h2><p>Operator figures are calculated by the same database aggregation functions as the canonical ingestion dashboard. Public fallback figures are drawn from the canonical status feed. Overall operator counts cover the retained corpus; recent values cover ingestion windows. Sensor counts may be estimated when database statistics are used, especially AIS fixes.</p><p>Source evidence is not the same as an incident. Independent corroboration and human review are required before claims become publishable.</p><button type="button" onClick={()=>navigate('history')}>Explore historical collection →</button></section>
 </>;
}
