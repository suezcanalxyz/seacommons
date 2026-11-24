import {L,useT} from './locale.jsx';
import GlossaryText from './GlossaryText.jsx';
import { useMemo, useState } from 'react';
import './knowledge-library.css';

export const libraryVolumes = [
  {id:'project',number:'01',title:'SeaCommons',subtitle:'Project & evidence model',category:'Research',pages:9,file:'01-seacommons-project.pdf',accent:'#8acbd1',summary:'A technical introduction to the observatory, its operating surfaces and the distinction between observed maritime signals, reported events and analytical interpretations.',topics:['LIVE & PLAY','AIS gaps','Source provenance'],reading:'Start here to understand how a maritime observation becomes a reviewable research record.'},
  {id:'hardware',number:'02',title:'Coastal Hardware',subtitle:'Receivers & field systems',category:'Infrastructure',pages:10,file:'02-seacommons-coastal-hardware.pdf',accent:'#caff41',summary:'Coastal AIS and radio receivers, site selection, power, buffering, receiver health and maintenance. Explains why missing coverage must be separated from missing vessel transmissions.',topics:['AIS / VHF','Coastal stations','Coverage diagnostics'],reading:'For engineering teams, coastal hosts and partners assessing an instrumented site.'},
  {id:'sectors',number:'03',title:'Sector Applications',subtitle:'Economic, social & environmental',category:'Applications',pages:9,file:'03-seacommons-sector-applications.pdf',accent:'#b1d6bb',summary:'Specific uses for vessel identity research, humanitarian incident documentation, environmental inquiries and maritime security, with limits on what the evidence can establish.',topics:['Environmental evidence','Humanitarian','Maritime activity'],reading:'For institutions and researchers evaluating concrete use cases.'},
  {id:'verticals',number:'04',title:'Markets & Verticals',subtitle:'Environmental pathways & positioning',category:'Applications',pages:10,file:'04-seacommons-market-verticals.pdf',accent:'#c6d9aa',summary:'Potential research and service pathways in coastal resilience, surface drift, pollution investigation and environmental data integration. Opportunities are distinguished from validated products.',topics:['Coastal resilience','Pollution inquiries','Market positioning'],reading:'For prospective funders, environmental partners and product strategy discussions.'},
  {id:'drifter',number:'05',title:'Drifter',subtitle:'Experimental marine instrument',category:'Infrastructure',pages:10,file:'05-seacommons-drifter.pdf',accent:'#ad9bff',summary:'A standalone hardware dossier covering GNSS positioning, telemetry, enclosure, energy budget, field trials, recovery procedures and the difference between measured drift and modelled trajectories.',topics:['GNSS & telemetry','Field testing','Drift validation'],reading:'For field research, marine engineering and experimental deployments.'}
];

function VolumeMark({volume}) {
  return <svg className="knowledge-mark" viewBox="0 0 180 130" role="img" aria-label={volume.title+' schematic'}>
    <defs><pattern id={'kn-grid-'+volume.id} width="18" height="18" patternUnits="userSpaceOnUse"><path d="M18 0H0V18" fill="none" stroke="currentColor" opacity=".13" strokeWidth=".6"/></pattern></defs>
    <rect width="180" height="130" fill={'url(#kn-grid-'+volume.id+')'}/>
    {volume.id==='hardware' ? <><path d="M90 105V34M73 105h34M78 32l12-16 12 16M62 45q28-30 56 0M49 52q41-45 82 0" fill="none" stroke="currentColor" strokeWidth="2"/><circle cx="90" cy="35" r="4" fill="currentColor"/></>
    : volume.id==='drifter' ? <><path d="M90 18v23m-23 10h46l-8 34H75zM61 90q14-12 29 0t29 0M61 102q14-12 29 0t29 0" fill="none" stroke="currentColor" strokeWidth="2"/><circle cx="90" cy="19" r="5" fill="none" stroke="currentColor" strokeWidth="2"/></>
    : volume.id==='verticals' ? <><path d="M22 93Q48 41 75 72T131 58t27-13M22 112Q48 60 75 91T131 77t27-13" fill="none" stroke="currentColor" strokeWidth="2"/><circle cx="75" cy="72" r="5" fill="currentColor"/><circle cx="131" cy="58" r="5" fill="currentColor"/></>
    : volume.id==='sectors' ? <><circle cx="90" cy="64" r="36" fill="none" stroke="currentColor" strokeWidth="2"/><path d="M90 28v72M54 64h72M64 39l52 50M64 89l52-50" stroke="currentColor" opacity=".65"/><circle cx="90" cy="64" r="9" fill="currentColor"/></>
    : <><path d="M19 94L50 61l24 15 30-46 51 23" fill="none" stroke="currentColor" strokeWidth="2"/><path d="M19 113L50 80l24 15 30-46 51 23" fill="none" stroke="currentColor" opacity=".4"/>{[[19,94],[50,61],[74,76],[104,30],[155,53]].map(([x,y])=><circle key={x} cx={x} cy={y} r="4" fill="currentColor"/>)}</>}
  </svg>;
}

export default function KnowledgeLibrary({compact=false}) {
 const t=useT();
 const [filter,setFilter]=useState('All');
 const [query,setQuery]=useState('');

 const shown=useMemo(()=>libraryVolumes.filter(v=>(filter==='All'||v.category===filter)&&[v.title,v.subtitle,v.summary,...v.topics].map(x=>x+' '+t(x)).join(' ').toLowerCase().includes(query.toLowerCase())),[filter,query,t]);
 return <section className={'knowledge-library'+(compact?' knowledge-library--compact':'')} id="seacommons-library" aria-labelledby="knowledge-library-heading">
   <div className="knowledge-library__head"><div><span className="knowledge-library__eyebrow">SUEZ REPUBLIC / SEACOMMONS / KNOWLEDGE SERIES 2026</span><h2 id="knowledge-library-heading"><L>Research dossiers</L></h2><p><L>Five illustrated dossiers. Open a PDF in its own tab or download it for offline reading. Read the research model, examine the coastal hardware, explore environmental and social applications, or study the Drifter prototype. These documents describe a pilot and proposed extensions, not a catalogue of fully deployed products.</L></p></div><div className="knowledge-library__count"><strong>05</strong><span><L>VOLUMES</L><br/><L>48 PAGES</L><br/>PDF / 16:9</span></div></div>
   <div className="knowledge-library__toolbar"><div className="knowledge-library__filters" role="group" aria-label="Filter library">{['All','Research','Infrastructure','Applications'].map(name=><button key={name} type="button" aria-pressed={filter===name} className={filter===name?'is-selected':''} onClick={()=>setFilter(name)}><L>{name}</L></button>)}</div><label className="knowledge-library__search"><span><L>Search the series</L></span><input type="search" value={query} onChange={e=>setQuery(e.target.value)} placeholder={t("e.g. AIS, environment, telemetry")} /></label></div>
   <div className="knowledge-library__grid">{shown.map(v=><article key={v.id} className="knowledge-volume" style={{'--volume-accent':v.accent}}><div className="knowledge-volume__cover"><span>SC / <L>{v.number}</L></span><VolumeMark volume={v}/><small><L>{t(v.category).toUpperCase()}</L></small></div><div className="knowledge-volume__body"><div className="knowledge-volume__meta"><span><L>VOLUME </L><L>{v.number}</L></span><span><L>{v.pages}</L><L> PAGES · PDF</L></span></div><h3><L>{v.title}</L></h3><h4><L>{v.subtitle}</L></h4><p><GlossaryText>{v.summary}</GlossaryText></p><div className="knowledge-volume__topics">{v.topics.map(t=><span key={t}><L>{t}</L></span>)}</div><details className="knowledge-volume__reading"><summary><L>Reading guide</L></summary><p><GlossaryText>{v.reading}</GlossaryText></p></details><div className="knowledge-volume__actions"><a href={'/documents/'+v.file} target="_blank" rel="noopener noreferrer"><L>Open PDF ↗</L></a><a href={'/documents/'+v.file} download={v.file}><L>Download ↓</L></a></div></div></article>)}</div>
   {!shown.length&&<p className="knowledge-library__empty"><L>No dossier matches this search. Try a different term or category.</L></p>}
   <div className="knowledge-library__foot"><span>EDITORIAL NOTE / NOV 2026</span><p><L>Source-derived observations, proposed instrumentation and anticipated applications are identified separately. Environmental and commercial pathways require field validation and partner-specific assessment.</L></p></div>

 </section>;
}
