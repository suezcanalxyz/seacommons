import {L} from './locale.jsx';
import React, {useState} from 'react';
import GlossaryText from './GlossaryText.jsx';
import KeyFigures from './KeyFigures.jsx';
import {useT,useLocale} from './locale.jsx';
import EvidenceDomains from './EvidenceDomains.jsx';
import { retainedEvidence, retainedMetricFallback } from './retainedEvidence.js';

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
function MetricSet({heading,rows,data}) {const [expanded,setExpanded]=useState(null);return <section className="future-section"><header><h2><L>{heading}</L></h2></header><div className="future-intelligence-metrics">{rows.map(([key,label,meaning])=><article key={key} className="future-intelligence-metric"><div className="future-intelligence-metric-top"><span><GlossaryTerm label={label}/></span><button type="button" aria-expanded={expanded===key} aria-label={'Explain '+label} onClick={()=>setExpanded(expanded===key?null:key)}><L>What is this? </L><L>{expanded===key?'−':'+'}</L></button></div><strong><L>{number(data?.[key])}</L></strong><p><L>{meaning}</L></p>{expanded===key&&<div className="future-intelligence-legend"><b><L>How to read it</L></b><p><L>{meaning}</L><L> The number belongs to its own evidence stage; it is not directly comparable to a case or vessel count. Missing means unavailable, not zero.</L></p><small><L>API field: </L><L>{key}</L></small></div>}</article>)}</div></section>}

import { fetchJson } from '../services/api/client.js';
import { resolveSiteApiBase } from '../site/liveApi.js';


const stageKeys={raw:'raw_observations',normalized:'parsed_events',derived:'derived_cues',episodes:'maritime_episodes',hypotheses:'investigation_hypotheses',corroborated:'corroborated_episodes',review_ready:'review_ready',live:'public_live'};

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
 return <section className="future-section future-intelligence-breakdown"><h2><L>{title}</L></h2><p><L>{help}</L></p>{entries.length?<div className="future-intelligence-bars">{entries.map(([key,value])=><div className="future-intelligence-bar" key={key}><span title={key}><L>{key.replaceAll('_',' ')}</L></span><div><i style={{width:Math.max(1,100*Number(value)/max)+'%'}}/></div><strong><L>{number(value)}</L></strong><small><L>{termDescription(key)}</L></small></div>)}</div>:<p><L>No breakdown currently available for this period.</L></p>}</section>
}
function useOperatorMetrics(period){
 const [snapshot,setSnapshot]=React.useState({period:null,data:null,loading:true,error:'',source:null,errorKind:null,warning:''});
 const seq=React.useRef(0);
 const refresh=React.useCallback(async()=>{
  const request=++seq.current;
  // Never show a previous window's numbers or timestamp as current.
  setSnapshot({period,data:null,loading:true,error:'',source:null,errorKind:null,warning:''});
  const accept=(data,source,warning='')=>{
   if(request===seq.current)setSnapshot({period,data,source,loading:false,error:'',errorKind:null,warning});
  };
  const fail=(errorKind='unavailable')=>{
   if(request===seq.current)setSnapshot({period,data:null,source:null,loading:false,
    error: errorKind==='authentication'?'The protected evidence service rejected this session. Sign out and sign in again, or ask an administrator to verify your access.':'The requested evidence service is temporarily unavailable.',
    errorKind,warning:''});
  };
  try{
   const url=period==='overall'?'/api/v1/futures/intelligence-overall':`/api/v1/operator/ingestion/overview?hours=${period==='7d'?168:24}`;
   const result=await fetchJson(resolveSiteApiBase(),url,undefined,period==='overall'?35000:30000);
   const valid=period==='overall'
    ? result?.scope==='all_time'&&result?.access==='public_aggregate'&&Array.isArray(result?.stages)&&result?.stages.length===7&&result?.sensor_activity&&Number.isFinite(Date.parse(result?.generated_at))
    : result?.lookback_hours===(period==='7d'?168:24)&&result?.pipeline_status?.pipeline;
   if(!valid)throw new Error('Unexpected measurement contract');
   accept(result,period==='overall'?'public-aggregate':'operator');
  }catch(error){
   const authRejected=error?.status===401||error?.status===403;
   // A denied OIDC identity cannot be repaired by retrying a second protected endpoint.
   if(period==='overall'){
    // Public aggregate failed. The independent retained IntelEvent contract can
    // still populate only the normalized record tile; never ask for OIDC.
    fail('unavailable');
    return;
   }
   try{
    {
     const hours=period==='7d'?168:24;
     const status=await fetchJson(resolveSiteApiBase(),'/api/v1/status?hours='+hours,undefined,30000);
     if(status?.window_hours!==hours||!status?.pipeline)throw new Error('Unexpected public status contract',{cause:error});
     accept({lookback_hours:hours,generated_at:status.generated_at,pipeline_status:{pipeline:status.pipeline,sensor_activity:status.sensor_activity},fallback_public:true},'public',
      authRejected?'The protected service rejected this session; only public operational measures are shown.':'The protected service is unavailable; only public operational measures are shown.');
    }
   }catch{fail(authRejected?'authentication':'unavailable');}
  }
 },[period]);
 React.useEffect(()=>{refresh();return()=>{seq.current+=1;};},[refresh]);
 return snapshot.period===period?{...snapshot,refresh}:{period,data:null,source:null,loading:true,error:'',errorKind:null,warning:'',refresh};
}
function useOperatorSections(period,tab) {
 const [snapshot,setSnapshot]=React.useState({data:null,error:'',key:''});
 React.useEffect(()=>{
   let active=true;
   if(period==='overall'){
    // The twelve aggregate measurements are public. Raw-source names and case
    // evidence remain private, and must never be fetched for a public period.
    setSnapshot({data:null,error:tab==='sources'||tab==='quality'
      ? 'Overall publishes summary counts only. Source-specific records and case evidence remain restricted.': '',key:period+':'+tab});
    return()=>{active=false;};
   }
   const hours=period==='7d'?168:24;
   const paths=tab==='pipeline'?[]:tab==='sources'?[]:tab==='quality'?['funnel','stabilization','cases']:tab==='sensors'?['sar-fleet','satellite-queue','humanitarian-ais-correlation']:tab==='activity'?['observations','events','signals','analysis','pipeline-map']:null;
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
  <h2><L>Measurement contract / what these numbers actually mean</L></h2>
  <p><L>One as-of time, distinct clocks. A new investigation is not the same as an updated one. The current open total is a stock, not a windowed activity total.</L></p>
  {period==='overall'?<p><L>Overall shows retained records. It is not an immutable historical ingestion total. Created-versus-updated measures apply to the 24-hour and 7-day windows.</L></p>:<>
   <p className="future-data-provenance"><L>{state.loading?'Loading canonical measurements…':state.error||'As of '+stamp(data?.as_of)+' · window start '+stamp(data?.window_start)+' · contract v'+(data?.contract_version||'?')}</L></p>
   <div className="future-intelligence-metrics">{measurementRows.map(([key,title,desc])=><article className="future-intelligence-metric" key={key}>
    <span><L>{title}</L></span><strong><L>{state.loading?'Loading…':number(data?.counts?.[key])}</L></strong>
    <p><L>{desc}</L></p><small><L>Clock: </L><L>{data?.definitions?.[key]?.clock||'not available'}</L></small>
   </article>)}</div>
   {data?.sources&&<Breakdown title="Contributing raw sources" items={data.sources} help="Source groups count original observations received within the same period. Multiple source families need not generate equivalent numbers of normalized events."/>}
  </>}
  <p className="future-data-provenance"><L>Rows are not additive. Historical data, current states, model cues and published cases represent different populations. Updated rows can reflect automated reprocessing without new evidence.</L></p>
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
   onBlur={()=>setExpanded(false)}><L>{label}</L></button>
  <span className="future-glossary-definition" id={tooltipId} role="tooltip"><L>{meaning}</L></span>
 </span>;
}
const metricInterpretation = {
 raw_observations: {how:'Count of incoming source envelopes registered within the selected period. A collected post and a receiver packet are separate envelopes; duplicates and repeated arrivals can still contribute.',example:'This measures collection workload, not distinct vessels or confirmed events.',limits:'Received-at time. Do not divide it by the number of investigations to calculate a detection rate.'},
 parsed_events: {how:'Normalized Intel-event records received or retained after source-specific parsing. Several records can describe the same real-world occurrence.',example:'A report and a position message may each become normalized events without representing two incidents.',limits:'Received-at time in 24h/7d; retained normalized-event inventory in the public Overall fallback.'},
 derived_cues: {how:'Rule- or model-generated observations suggesting a possible pattern worthy of closer examination.',example:'An AIS discontinuity can create a cue even when shore reception is poor.',limits:'Received-at time. A cue is not independent corroboration or evidence of intent.'},
 maritime_episodes: {how:'Recognized groups of related observations assembled into one time-and-place context.',example:'Multiple position observations might be grouped into one possible continuity episode.',limits:'Updated-at time for rolling periods, including previously created episodes revisited today.'},
 investigation_hypotheses: {how:'Non-expired, non-rejected propositions being evaluated against evidence and alternative explanations.',example:'An unusual track might justify testing a reception hypothesis, not publishing wrongdoing.',limits:'Updated-at time. This is not a count of newly opened investigations.'},
 corroborated_episodes: {how:'Episodes whose supporting inputs come from genuinely independent evidence origins after lineage checks.',example:'Two websites copying one original AIS feed are not two independent witnesses.',limits:'Updated-at time. Corroboration is not an institutional or legal finding.'},
 review_ready: {how:'Hypotheses that reached an internal review stage, including records reassessed during the selected period.',example:'A reviewer can receive a dossier with supporting sources and known counter-indicators.',limits:'Updated-at time. Ready for review is not the same as reviewed, approved or publicly released.'},
 ais_fixes: {how:'Stored AIS vessel position rows with an observation timestamp in the window; historical totals may use database planner estimates.',example:'A single vessel can transmit hundreds of position messages in one day.',limits:'Source observation time, not unique vessels. ≈ marks an estimated inventory rather than an exact count.'},
 radio_bursts: {how:'Radio-frequency bursts captured by receivers before decoding or message validation.',example:'A burst may be noise or an incomplete transmission and produce no usable message.',limits:'Capture/creation time. Never present radio bursts as verified distress calls.'},
 radio_events: {how:'Radio observations successfully decoded and stored as structured events.',example:'A valid DSC message can become an event; several other captured bursts cannot.',limits:'Creation time. One decoded radio event does not prove a rescue or emergency.'},
 satellite_observations: {how:'Satellite scenes or observation records actually discovered and registered for contextual analysis.',example:'A candidate satellite scene can cover the area without identifying a specific vessel.',limits:'Discovery time. The count is not the number of verified detections.'},
 active_source_names: {how:'Number of distinct source-name identifiers contributing received raw material during the window.',example:'One active feed can supply thousands of records while another supplies one.',limits:'Distinct-source count, not a count of independent lineages or continuously healthy sensors.'},
};
function IntelligenceMetricGrid({period,pipeline,sensorsData,loadedAt,estimatedFields=[],loading=false,source=null}) {
 const [expanded,setExpanded]=useState(null);
 const measurements={...sensorsData,...pipeline};
 const overall=period==='overall';
 const scopeText=overall?'Retained records, subject to data retention':period==='7d'?'Rolling 7 days':'Rolling 24 hours';
 const countsAvailable=headlineMetrics.filter(([key])=>measurements?.[key]!==null&&measurements?.[key]!==undefined).length;
 const report=loading?(countsAvailable?'Updating measurements · available values shown':'Updating measurements'):countsAvailable===0?'Measurements unavailable':countsAvailable<12?'Partial measurements':'Measurements available';
 return <section className="future-section future-intelligence-headline" aria-label="Intelligence metric dashboard" aria-busy={loading}>
   <header className="future-kpi-heading"><div><span className="future-eyebrow"><L>Intelligence / measurements</L></span><h2><L>Evidence activity</L></h2></div>
    <p><L>{scopeText}</L><L> · Twelve separate measurements. Select Info for the counting method, example and limits.</L></p></header>
   <p className="future-metric-status" role="status" aria-live="polite"><L>{report}</L><L>{!loading&&source==='public'?' · public operational summary':''}</L><L>{!loading&&countsAvailable>0?' · '+countsAvailable+' of 12 measures available':''}</L></p>
   <KeyFigures label="Principal evidence measures" items={['parsed_events','corroborated_episodes','review_ready'].map(key=>{const [,,detail]=headlineMetrics.find(x=>x[0]===key);const value=measurements?.[key];return {title:headlineMetrics.find(x=>x[0]===key)[1],value:typeof value==='number'&&Number.isFinite(value)&&value>=0?(estimatedFields.includes(key)?'≈ ':'')+number(value):loading?'Loading…':null,detail}})}/>
   <h3 className="future-measure-subheading"><L>Full measurement register</L></h3>
   <div className="future-intelligence-metrics future-intelligence-unified-grid">{headlineMetrics.map(([key,label,definition])=>{
    const value=measurements?.[key];
    const hasValue=value!==null&&value!==undefined&&Number.isFinite(Number(value));
    const isEstimated=estimatedFields.includes(key)||key==='ais_fixes'&&overall&&estimatedFields.includes('ais_fixes');
    const clock=overall?'Retained record inventory':metricClocks[key]||'Source-defined time';
    const teaching=metricInterpretation[key];
    return <article className={'future-intelligence-metric'+(!loading&&!hasValue?' is-unavailable':'')} key={key}>
     <div className="future-intelligence-metric-top"><span><GlossaryTerm label={label}/></span>
      <button type="button" aria-expanded={expanded===key} aria-label={'Counting method for '+label}
       onClick={()=>setExpanded(expanded===key?null:key)}><L>{expanded===key?'Close −':'Info +'}</L></button></div>
     <strong className={!hasValue&&loading?'future-metric-loading':''} data-metric={key}><L>{hasValue?(isEstimated?'≈ ':'')+number(value):loading?'Loading…':'Unavailable'}</L></strong>
     <p><GlossaryText>{definition}</GlossaryText></p>
     {expanded===key&&<div className="future-intelligence-legend"><b><L>How to read this measure</L></b>
      <p><GlossaryText>{teaching.how}</GlossaryText></p>
      <p><b><L>Concrete example:</L></b> <GlossaryText>{teaching.example}</GlossaryText></p>
      <p><b><L>Counting clock:</L></b> <L>{clock}</L>. <GlossaryText>{teaching.limits}</GlossaryText></p>
      <p><L>{!loading&&!hasValue?'Source missing: this is unknown, not zero.':isEstimated?'Approximate historical database estimate.':'A recorded value, subject to the source and temporal scope above.'}</L></p>
     </div>}
    </article>;
   })}</div>
   <p className="future-data-provenance"><L>{scopeText}</L><L> · Last source update: </L><L>{stamp(loadedAt)}</L><L>{estimatedFields.length?' · Estimates marked ≈':''}</L><L>. An unavailable value never means zero.</L></p>
 </section>;
}
function SimpleRecords({title,items,description}) {
 if(!Array.isArray(items)||!items.length)return <section className="future-section"><h2><L>{title}</L></h2><p><L>{description}</L></p><p><L>No records currently available.</L></p></section>;
 return <section className="future-section"><h2><L>{title}</L></h2><p><L>{description}</L></p><div className="future-intelligence-records">{items.slice(0,60).map((row,i)=><details key={row.observation_id||row.event_id||row.id||i}><summary><strong><L>{row.semantic_label||row.title||row.kind||row.type||'Observation'}</L></strong><span><L>{stamp(row.received_at||row.timestamp_utc||row.updated_at||row.observed_at)}</L></span></summary><p><L>Source: </L><L>{row.source_name||row.source||row.kind||'Unknown'}</L><L> · Evidence stage: </L><L>{row.pipeline_role||row.kind||'Unspecified'}</L></p><p><L>Category: </L><L>{row.observation_type||row.type||row.family||row.status||'Unspecified'}</L></p><p><L>Records in this view are observations or hypotheses, not proven incidents.</L></p></details>)}</div></section>
}
const qualityHelp={
 episode_to_multi_lineage:'Share of recognized episodes independently corroborated. A low rate is not a software failure by itself.',
 multi_lineage_to_review_ready:'Share of independently corroborated episodes that reached human-review readiness.',
 derived_to_episode:'Share of derived cues grouped into recognized episodes. A descriptive process ratio.',
};
function QualityDiagnostics({data}) {
 if(!data)return <section className="future-section future-empty-insight"><h2><L>Quality & stabilization</L></h2><p><L>Quality checks show how observations are screened for consistency and how independently sourced information is evaluated. Detailed results are not yet available for this period.</L></p></section>;
 const entries=Object.entries(data.rates||{});
 const checks=Object.entries(data.invariants||{});
 return <section className="future-section"><h2><L>Pipeline quality checks</L></h2><p><L>These are diagnostics, not scores of vessel behavior or evidence of unlawful activity.</L></p><div className="future-intelligence-metrics">{entries.map(([k,v])=><article className="future-intelligence-metric" key={k}><span><L>{k.replaceAll('_',' ')}</L></span><strong><L>{typeof v==='number'?Number(v*100).toFixed(1)+'%':String(v??'—')}</L></strong><p><L>{qualityHelp[k]||'Process rate for the selected window.'}</L></p></article>)}{checks.map(([k,v])=><article className="future-intelligence-metric" key={k}><span><L>{k.replaceAll('_',' ')}</L></span><strong><L>{typeof v==='boolean'?(v?'PASS':'CHECK'):number(v)}</L></strong><p><L>A consistency check for independent evidence lineages.</L></p></article>)}</div><h3><L>Radio decoding threshold</L></h3><p><L>The radio receiver network should not be expanded on signal volume alone: decodes must be repeatable and verifiable.</L></p><p><L>{data.radio?.scale_gate||'Decode quality threshold not reported.'}</L></p></section>
}
function SatelliteCandidates({data}) {
 const items=Array.isArray(data?.items)?data.items:[];
 return <section className="future-section"><h2><L>Satellite coverage review queue</L></h2><p><L>These candidates indicate imagery that may overlap a maritime episode in space and time. Coverage is context for analysis; it is not evidence that a particular vessel was detected.</L></p><p><L>{number(data?.total_candidates)}</L><L> candidates in this window · </L><L>{number(data?.count)}</L><L> returned for review.</L></p>{items.length?<div className="future-intelligence-records">{items.map((x,i)=><details key={x.episode_id||i}><summary><strong><L>{String(x.episode_family||'Episode').replaceAll('_',' ')}</L></strong><span><L>Priority </L><L>{typeof x.priority_score==='number'?x.priority_score.toFixed(2):'unknown'}</L></span></summary><p><L>{number(x.scene_count)}</L><L> relevant scenes · nearest time difference </L><L>{number(x.nearest_delta_hours)}</L><L> hours.</L></p><p><L>Status: </L><L>{x.evidence_role||'context only'}</L><L> · verification: </L><L>{x.verification_status||'not independently confirmed'}</L></p><p><L>Coverage candidates do not identify vessels or corroborate an allegation without additional evidence.</L></p></details>)}</div>:<p><L>No satellite coverage candidates were returned, or access is unavailable.</L></p>}</section>
}
function HumanitarianCorrelation({data}) {
 const items=Array.isArray(data?.items)?data.items:[];
 return <section className="future-section"><h2><L>Humanitarian reports & AIS context</L></h2><p><GlossaryText>Cross-checks between reports and nearby AIS tracks help investigators prioritize review. Distance and timing alone cannot identify a rescue vessel or prove involvement in an incident.</GlossaryText></p><p><L>{number(data?.count)}</L><L> geolocated reports with candidate associations. Search radius: </L><L>{number(data?.radius_nm)}</L><L> nautical miles; time window: </L><L>{number(data?.window_hours)}</L><L> hours.</L></p>{items.length?<div className="future-intelligence-records">{items.slice(0,30).map((x,i)=><details key={x.event_id||i}><summary><strong><L>{x.title||'Humanitarian source report'}</L></strong><span><L>{stamp(x.timestamp_utc)}</L></span></summary><p><L>Reported by </L><L>{x.source||'source unavailable'}</L> · <L>{number(x.candidate_count)}</L><L> contextual AIS associations.</L></p><p><L>Possible association does not confirm an incident, vessel identity, rescue action or wrongdoing.</L></p></details>)}</div>:<p><L>No contextual matches are reported for this window, or protected data are unavailable.</L></p>}</section>
}
function FleetView({data}) {
 const features=Array.isArray(data?.features)?data.features:[];
 return <section className="future-section"><h2><L>Civil and state SAR fleet</L></h2><p><L>Registered </L><L>{number(data?.meta?.total_registered)}</L><L> · Live </L><L>{number(data?.meta?.live_ais)}</L><L> · Stale </L><L>{number(data?.meta?.stale_ais)}</L><L> · Offline </L><L>{number(data?.meta?.offline)}</L><L>. Tracker: </L><L>{data?.meta?.tracking_stream?.connected?'connected':'not confirmed'}</L>.</p><p><L>The fleet registry shows monitoring status, not whether a vessel is conducting rescue operations. Only recent positions may be plotted; stale coordinates remain withheld.</L></p>{features.length?<div className="future-intelligence-metrics">{features.map((f,i)=><article className="future-intelligence-metric" key={f.id||i}><span><L>{f.properties?.ship_name||f.properties?.name||'SAR asset'}</L></span><strong className="future-intelligence-date"><L>{f.properties?.ais_status||'Status unknown'}</L></strong><p><L>{f.properties?.org||'Fleet registration'}</L> · <L>{f.properties?.operator_type==='state_authority'?'state SAR':'civil SAR'}</L></p></article>)}</div>:<p><L>{data?'The fleet response does not expose a readable feature list.':'Fleet data unavailable with current permissions.'}</L></p>}</section>
}
function AcquisitionHealth({items}) {
 const rows=Array.isArray(items)?items:[];
 const meanings={live:'Feed reporting recent activity; it does not certify every observation.',degraded:'Feed is connected with partial coverage or a known limitation.',offline:'No active telemetry from this feed at the current check.',disabled:'This source has been intentionally disabled.'};
 return <section className="future-section"><h2><L>Acquisition health</L></h2><p><L>Connection states describe ingestion health, not the truth of reports or the safety status of any vessel.</L></p>{rows.length?<div className="future-intelligence-metrics">{rows.map((r,i)=><article className="future-intelligence-metric" key={r.family||i}><span><L>{r.label||r.family||'Source'}</L></span><strong className="future-intelligence-date"><L>{r.state||'unknown'}</L></strong><p><L>{meanings[r.state]||'Current connection status is not available.'}</L></p></article>)}</div>:<p><L>Acquisition health is not available from this response.</L></p>}</section>
}
function CaseReview({data}) {
 const cases=Array.isArray(data?.cases)?data.cases:[];
 return <section className="future-section"><h2><L>Investigation evidence chains</L></h2><p><GlossaryText>Real hypotheses, their evidence lineages and blockers. A candidate is not a criminal allegation, a SAR alert or a published case.</GlossaryText></p>{cases.length?cases.slice(0,30).map((c,i)=><details key={c.case_id||i} className="future-intelligence-chain"><summary><L>{c.label||c.hypothesis_type||'Investigation'}</L> · <L>{c.state||'unreviewed'}</L></summary><p><L>Evidence stage: </L><L>{c.evidence_stage||'not reported'}</L><L> · Verification: </L><L>{c.verification_status||'not reported'}</L></p>{Array.isArray(c.independence_groups)&&<p><L>Independent lineages: </L><L>{c.independence_groups.join(', ')||'Not established'}</L></p>}{Array.isArray(c.blockers)&&<p><L>Why progress is blocked: </L><L>{c.blockers.join(' · ')||'No blockers reported'}</L></p>}{Array.isArray(c.evidence)&&<p><L>Evidence links: </L><L>{c.evidence.length}</L><L> recorded references. Their existence does not establish claim truth.</L></p>}</details>):<p className="future-empty-description"><L>No reviewable evidence-chain details were returned for this period. This does not imply zero investigations.</L></p>}</section>
}
function ParserTopology({data}) {
 const chains=Array.isArray(data?.chains)?data.chains:[];
 return <section className="future-section"><h2><L>Source → observation → episode</L></h2><p><L>Each source passes through specific normalization, validation and correlation steps.</L></p>{chains.length?chains.map((c,i)=><details key={c.id||i} className="future-intelligence-chain"><summary><L>{c.label||c.title||c.id||'Pipeline'}</L></summary><p><L>Inputs: </L><L>{(c.inputs||[]).join(' · ')||'Not specified'}</L></p><p><L>Raw observations: </L><L>{(c.raw_observations||[]).join(' · ')||'Not specified'}</L></p><p><L>Checks: </L><L>{(c.controls||[]).join(' · ')||'Not specified'}</L></p></details>):<p><L>Parser metadata unavailable.</L></p>}</section>
}
function StagePanels({rows,lookup}){
 return <div className="future-intelligence-metrics">{rows.map(([key,title,help])=><article className="future-intelligence-metric" key={key}><span><L>{title}</L></span><strong><L>{number(lookup?.[key])}</L></strong><p><L>{help}</L></p></article>)}</div>
}
function ComparisonColumn(period,snapshot,overall){
 const raw=snapshot.data;
 const retained=period==='overall'&&!raw?retainedMetricFallback(overall?.history):null;
 const pipeline=period==='overall'?(Array.isArray(raw?.stages)?Object.fromEntries(raw.stages.map(s=>[stageKeys[s.id]||s.id,s.count])):retained):raw?.pipeline_status?.pipeline;
 const sensors=period==='overall'?raw?.sensor_activity:raw?.pipeline_status?.sensor_activity;
 const values={...sensors,...pipeline};
 if(period==='overall'&&sensors)values.active_source_names=sensors.source_names;
 return {period,values,loading:snapshot.loading,refresh:snapshot.refresh,source:retained?'retained':snapshot.source,at:raw?.generated_at||(retained?overall?.history?.generated_at:null),estimated:period==='overall'?(raw?.estimated_fields||(sensors?.ais_fixes_estimated?['ais_fixes']:[])):[]};
}
function ComparisonDashboard({overall,navigate}){
 const t=useT(),lang=useLocale();
 const a=useOperatorMetrics('24h'),b=useOperatorMetrics('7d'),c=useOperatorMetrics('overall');
 const columns=[ComparisonColumn('24h',a,overall),ComparisonColumn('7d',b,overall),ComparisonColumn('overall',c,overall)];
 const [metric,setMetric]=useState(null);
 const row=headlineMetrics.find(r=>r[0]===metric);
 const fmt=new Intl.NumberFormat(lang==='it'?'it-IT':'en-GB');
 const dateFmt=new Intl.DateTimeFormat(lang==='it'?'it-IT':'en-GB',{dateStyle:'short',timeStyle:'short'});
 const sourceLabel=col=>col.loading?'Updating measurements':col.source==='operator'?'Protected evidence API':col.source==='public'?'Public operational status':col.source==='public-aggregate'?'Public historical aggregates':col.source==='retained'?'Public retained Intel-event inventory':'No verified source';
 const display=(col,key)=>{const n=col.values[key];return typeof n==='number'&&Number.isFinite(n)&&n>=0?(col.estimated.includes(key)?'≈ ':'')+fmt.format(n):col.loading?'…':'—'};
 return <section className="intel-compare" aria-label={t('Evidence comparison')}>
 <header className="intel-compare-head"><div><span className="future-eyebrow">{t('Evidence inventory and activity')}</span><h1>Intelligence</h1><p>{t('Compare the same measures across the three time windows. Overall describes retained records, not lifetime ingestion.')}</p></div><button type="button" onClick={()=>columns.forEach(col=>col.refresh())} disabled={columns.some(col=>col.loading)}>{t('Refresh all')}</button></header>
 <table className="intel-matrix"><thead><tr><th scope="col">{t('Measure')}</th><th scope="col">{t('24 hours')}<small>{t('Rolling window')}</small></th><th scope="col">{t('7 days')}<small>{t('Rolling window')}</small></th><th scope="col">{t('Overall')}<small>{t('Retained inventory')}</small></th></tr></thead><tbody>{headlineMetrics.map(([key,label,definition],i)=><tr key={key} className={i===7?'intel-matrix-divider':''}><th scope="row"><button type="button" aria-haspopup="dialog" onClick={()=>setMetric(key)} title={t(definition)}>{t(label)} <span aria-hidden="true">ⓘ</span></button></th>{columns.map(col=><td key={col.period} className={display(col,key)==='—'?'is-missing':''} data-metric={key}><L>{display(col,key)}</L></td>)}</tr>)}</tbody><tfoot><tr><th scope="row">{t('Source and update')}</th>{columns.map(col=><td key={col.period}><small>{t(sourceLabel(col))}</small><small><L>{col.at&&Number.isFinite(Date.parse(col.at))?dateFmt.format(new Date(col.at)):'—'}</L></small></td>)}</tr></tfoot></table>
 <footer className="intel-compare-foot"><p>{t('Counts are not additive. Received, updated, observed and retained records have different meanings. — unavailable; … loading; ≈ estimate.')}</p><button type="button" onClick={()=>navigate('intel-measures')}>{t('Measurement definitions')} ↗</button><button type="button" onClick={()=>navigate('intel-sensors')}>{t('Research domains')} ↗</button></footer>
 {row&&<MetricDefinition row={row} close={()=>setMetric(null)}/>}
 </section>
}
function MetricDefinition({row,close}){
 const t=useT();
 const ref=React.useRef(null);
 React.useEffect(()=>{const el=ref.current;if(el&&!el.open)el.showModal();return()=>{if(el?.open)el.close()}},[]);
 const teaching=metricInterpretation[row[0]];
 return <dialog ref={ref} className="intel-definition-dialog" onCancel={e=>{e.preventDefault();close()}}><header><h2>{t(row[1])}</h2><button type="button" onClick={close} aria-label={t('Close')}>×</button></header><p>{t(row[2])}</p><h3>{t('Counting method')}</h3><p>{t(teaching.how)}</p><h3>{t('Concrete example')}</h3><p>{t(teaching.example)}</p><h3>{t('Limits')}</h3><p>{t(teaching.limits)}</p></dialog>;
}
function DomainDashboard(){
 const a=useOperatorMetrics('24h'),b=useOperatorMetrics('7d'),c=useOperatorMetrics('overall');
 return <EvidenceDomains snapshots={[a,b,c]}/>;
}
export default function IntelligenceDashboard(props){
 if(!props.section||props.section==='compare')return <ComparisonDashboard {...props}/>;
 if(props.section==='sensors')return <DomainDashboard/>;
 return <IntelligenceDetail key={props.section} {...props}/>;
}
function IntelligenceDetail({ops,overall,period:requestedPeriod,setPeriod,navigate,section}){
 const tab=section==='measures'?'pipeline':section;
 const rollingOnly=['sources','quality','activity'].includes(tab);
 const period=rollingOnly&&requestedPeriod==='overall'?'7d':requestedPeriod;
 const [detail,setDetail]=useState(0);
 const t=useT();
 const operator=useOperatorMetrics(period);
 const sections=useOperatorSections(period,tab);
 const isOverall=period==='overall';
 const expectedHours=period==='7d'?168:24;
 const raw=operator.data && (isOverall ? operator.data.scope==='all_time' : operator.data.lookback_hours===expectedHours) ? operator.data : null;
 const status=!isOverall&&ops.status?.window_hours===(period==='7d'?168:24)?ops.status:null;
 const rawStages=Array.isArray(raw?.stages)?Object.fromEntries(raw.stages.map(s=>[stageKeys[s.id]||s.id,s.count])):null;
 const funnelStages=Array.isArray(sections.data?.funnel?.stages)?Object.fromEntries(sections.data.funnel.stages.map(s=>[stageKeys[s.id]||s.id,s.count])):null;
 // The public retained IntelEvent inventory remains a reliable, narrowly scoped
 // Overall reference when the expensive private all-time metric endpoint fails.
 // Only the normalized-event tile is populated: never invent the other 11.
 const retained=overall?.history?.scope==='retained_intel_events' ? overall.history : null;
 const validRetained=retainedEvidence(retained);
 const retainedFallback=isOverall&&!raw?retainedMetricFallback(retained):null;
 const pipeline=isOverall?(rawStages||retainedFallback):(raw?.pipeline_status?.pipeline||status?.pipeline||funnelStages);
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

 const specialSensors=isOverall&&sensorsData?{...sensorsData,active_source_names:sensorsData.source_names}:sensorsData;
 const dataSource=raw?operator.source:(retainedFallback?'public-retained':(!isOverall&&status?'public':null));
 const evidenceSourceLabel=dataSource==='public-aggregate'?'Public historical aggregates':dataSource==='operator'?'Protected evidence API':dataSource==='historical'?'Historical evidence inventory':dataSource==='public'?'Public operational status':dataSource==='public-retained'?'Public retained Intel-event inventory':'No verified source';
 const evidenceWindowLabel=isOverall?'Retained record inventory':period==='7d'?'Rolling 168 hours':'Rolling 24 hours';
 const evidenceTimestamp=raw?.generated_at||(isOverall?retained?.generated_at:status?.generated_at);

 return <><section className="future-page-head"><h1>{t({pipeline:"Measurement definitions",sources:"Sources & types",quality:"Evidence quality",sensors:"Sensors & SAR",activity:"Acquisition & logs"}[tab])}</h1><p><L>Evidence collection, processing and review metrics. Choose a time window and inspect the counting method for each measure.</L></p></section>
 <div className="future-period-tabs" aria-label="Intelligence time window"><div role="group" aria-label="Intelligence time window">{[['24h','24 hours'],['7d','7 days'],['overall','Overall']].filter(([id])=>!rollingOnly||id!=='overall').map(([id,label])=><button type="button" aria-pressed={period===id} className={period===id?'is-active':''} onClick={()=>setPeriod(id)} key={id}><L>{label}</L></button>)}</div><small><L>{isOverall?'All records currently retained, irrespective of the age of the source event':period==='7d'?'Rolling seven days':'Rolling 24 hours'}</L></small></div>

 {rollingOnly&&<p className="future-data-provenance">{t('Detailed sources and quality records use authorized rolling windows. Historical aggregates remain in Comparison and Research domains.')}</p>}
 <div className="future-intelligence-freshness future-evidence-provenance" aria-label="Evidence data provenance">
  <div className="future-evidence-provenance-main">
   <strong><L>{operator.loading&&!retainedFallback?'Loading evidence…':retainedFallback?'Partial historical evidence':dataSource?'Evidence available':'Evidence unavailable'}</L></strong>
   <span><L>{evidenceWindowLabel}</L> · <L>{evidenceSourceLabel}</L></span>
  </div>
  <small><L>{evidenceTimestamp?'Updated '+stamp(evidenceTimestamp):operator.loading?'Request in progress':'No verified update time'}</L></small>
  <button type="button" disabled={operator.loading} onClick={operator.refresh}><L>{operator.loading?'Loading…':operator.error?'Retry':'Refresh'}</L></button>
 </div>
 {operator.error&&<p className="future-inline-note" role="alert"><L>{operator.error}</L> {operator.errorKind==='authentication'&&<button type="button" onClick={()=>navigate('access')}><L>Review account access →</L></button>}</p>}
 {operator.warning&&<p className="future-inline-note" role="status"><L>{operator.warning}</L><L> Protected and public records must not be treated as equivalent.</L></p>}
 {retainedFallback&&<p className="future-evidence-partial" role="status"><L>Partial Overall evidence: </L><L>{number(validRetained?.total)}</L><L> retained normalized Intel-event records are independently available. The remaining measures are temporarily unavailable from the public aggregate service and are shown as unavailable rather than invented. </L><button type="button" disabled={operator.loading} onClick={operator.refresh}><L>Retry full inventory</L></button></p>}
 {tab==='pipeline'&&<><div className="futures-switcher" role="group" aria-label={t('Measurement definitions')}>{['Evidence measures','Measurement contract'].map((v,i)=><button key={v} type="button" aria-pressed={detail===i} onClick={()=>setDetail(i)}>{t(v)}</button>)}</div>{detail===0?<IntelligenceMetricGrid period={period} pipeline={pipeline} sensorsData={specialSensors} loadedAt={evidenceTimestamp} loading={operator.loading&&!retainedFallback} source={dataSource} estimatedFields={isOverall?raw?.estimated_fields||(sensorsData?.ais_fixes_estimated?['ais_fixes']:[]):[]}/>:<MeasurementContract period={period}/>}</>}
 {tab==='sources'&&<DetailSwitcher labels={Object.keys(sourceHelp).slice(0,4).map(k=>k.replaceAll('_',' '))} selected={detail} setSelected={setDetail}>{Object.entries(sourceHelp).slice(0,4).map(([key,help])=><Breakdown key={key} title={key.replaceAll('_',' ')} items={breakdown?.[key]} help={help}/>)}</DetailSwitcher>}
 {tab==='sensors'&&<DetailSwitcher labels={['Sensors and signal coverage','Civil and state SAR fleet','Satellite coverage review queue','Humanitarian reports & AIS context']} selected={detail} setSelected={setDetail}>{[<MetricSet key="metrics" heading="Sensors and signal coverage" rows={sensors} data={specialSensors}/>,<FleetView key="fleet" data={sections.data?.['sar-fleet']}/>,<SatelliteCandidates key="satellite" data={sections.data?.['satellite-queue']}/>,<HumanitarianCorrelation key="context" data={sections.data?.['humanitarian-ais-correlation']}/>]}</DetailSwitcher>}
 {tab==='quality'&&<DetailSwitcher labels={['Quality & stabilization','Investigation evidence chains',...Object.keys(sourceHelp).slice(4).map(k=>k.replaceAll('_',' '))]} selected={detail} setSelected={setDetail}>{[<QualityDiagnostics key="quality" data={sections.data?.stabilization}/>,<CaseReview key="cases" data={sections.data?.cases}/>,...Object.entries(sourceHelp).slice(4).map(([key,help])=><Breakdown key={key} title={key.replaceAll('_',' ')} items={breakdown?.[key]} help={help}/>)]}</DetailSwitcher>}
 {tab==='activity'&&<DetailSwitcher labels={['Acquisition health','Raw ingestion','Normalized events','Incoming partner signals','Episodes and hypotheses','Parser topology']} selected={detail} setSelected={setDetail}>{[<AcquisitionHealth key="health" items={raw?.acquisition}/>,<SimpleRecords key="raw" title="01 / Raw ingestion" items={sections.data?.observations?.observations} description="Unprocessed source observations. Reappearance after silence is telemetry, not proof of covert activity."/>,<SimpleRecords key="events" title="02 / Normalized events" items={sections.data?.events?.events} description="Parsed events are standardized source observations, not validated incidents."/>,<SimpleRecords key="signals" title="Incoming partner signals" items={sections.data?.signals?.signals} description="External connector inputs are source material, not verified humanitarian or maritime incidents."/>,<SimpleRecords key="analysis" title="03 / Episodes and hypotheses" items={sections.data?.analysis?.items} description="Investigation candidates and recognized episodes; each requires further independent evidence."/>,<ParserTopology key="map" data={sections.data?.['pipeline-map']}/>]}</DetailSwitcher>}
 {sections.error&&<p role="status"><L>{sections.error}</L></p>}
 <details className="future-section intel-provenance-details"><summary><L>Data provenance and interpretation</L></summary><p><GlossaryText>Operator figures are calculated by the same database aggregation functions as the canonical ingestion dashboard. Public fallback figures are drawn from the canonical status feed. Overall headline counts come from a public, privacy-safe retained inventory. Recent detailed metrics may use protected operator endpoints. All figures refer to different stages and clocks. Sensor counts may be estimated when database statistics are used, especially AIS fixes.</GlossaryText></p><p><L>Source evidence is not the same as an incident. Independent corroboration and human review are required before claims become publishable.</L></p><button type="button" onClick={()=>navigate('history')}><L>Explore historical collection →</L></button></details>
 </>;
}

function DetailSwitcher({labels,selected,setSelected,children}){
 const t=useT();
 return <><nav className="futures-switcher intel-detail-switch" aria-label={t('Detail sections')}>{labels.map((label,i)=><button type="button" key={label} aria-pressed={selected===i} onClick={()=>setSelected(i)}>{t(label)}</button>)}</nav>{React.Children.toArray(children)[selected]}</>;
}
