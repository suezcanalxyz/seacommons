import React from 'react';
import KnowledgeLibrary from './KnowledgeLibrary.jsx';
import './overview-editorial.css';
export const needs=[
{title:'Virtual machines & storage',tag:'Compute',description:'Keep ingestion, historical queries and backups reliable.',examples:'Cloud credits, CPU/RAM, PostgreSQL hosting, storage',request:'I can support compute or storage.'},
{title:'Radio & coastal receivers',tag:'Signals',description:'Expand responsible maritime radio and AIS reception.',examples:'AIS/VHF/DSC receivers, SDR, antenna, permitted coastal sites',request:'I would like to contribute or host a radio receiver.'},
{title:'Satellite & geospatial',tag:'Imagery',description:'Help cross-check events using documented imagery and spatial methods.',examples:'SAR/optical access, processing credits, GIS expertise',request:'I can contribute satellite or geospatial resources.'},
{title:'Maritime archives & data',tag:'Evidence',description:'Make vessel histories and documentary evidence traceable.',examples:'Historical AIS, port calls, registries, public records',request:'I can share maritime archives or data.'},
{title:'Field nodes & hardware',tag:'Hardware',description:'Prototype maintainable, low-power monitoring stations.',examples:'Solar power, enclosures, connectivity, maintenance',request:'I would like to help with a field node.'},
{title:'Research & partnerships',tag:'Community',description:'Support verification, methodology and critical public research.',examples:'OSINT, maritime law, engineering, translation, institutions',request:'I would like to propose a research partnership.'},
];
const Icon=({name,size=25})=>{
const shapes={
ship:<><path d="M3 17l2 3h14l2-3-2-2H5z"/><path d="M7 15V7h10v8M10 7V4h4v3"/></>,
radio:<><circle cx="12" cy="12" r="2"/><path d="M8 8a6 6 0 0 0 0 8m8-8a6 6 0 0 1 0 8M5 5a10 10 0 0 0 0 14m14-14a10 10 0 0 1 0 14"/></>,
server:<><rect x="4" y="3" width="16" height="8" rx="2"/><rect x="4" y="13" width="16" height="8" rx="2"/><path d="M8 7h.01M8 17h.01M12 7h5M12 17h5"/></>,
satellite:<><path d="m5 9 4-4 10 10-4 4zM4 4l5 5M15 15l5 5M2 12a10 10 0 0 0 10 10M12 2a10 10 0 0 1 10 10"/></>,
archive:<><rect x="3" y="4" width="18" height="5" rx="1"/><path d="M5 9v11h14V9M10 13h4"/></>,
sun:<><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M4.9 4.9l1.4 1.4m11.4 11.4 1.4 1.4M2 12h2m16 0h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></>,
people:<><circle cx="9" cy="8" r="3"/><path d="M3 20v-2a6 6 0 0 1 12 0v2M17 5a3 3 0 0 1 0 6M17 14a5 5 0 0 1 4 5v1"/></>,
leaf:<><path d="M20 4C9 4 4 8 4 15a5 5 0 0 0 5 5c7 0 11-5 11-16ZM4 20c3-5 7-8 12-10"/></>,
chart:<><path d="M4 20V4M4 20h16M7 16l4-5 4 2 5-8"/></>,
shield:<><path d="m12 2 8 4v6c0 5-3 8-8 10-5-2-8-5-8-10V6zM9 12l2 2 4-4"/></>,
download:<><path d="M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4"/></>
};
return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{shapes[name]||shapes.ship}</svg>
};
const iconNames=['server','radio','satellite','archive','sun','people'];
const email=item=>'mailto:republic@suezcanal.xyz?subject='+encodeURIComponent('SeaCommons FUTURES — '+item.title)+'&body='+encodeURIComponent('Hello Suez Republic,\n\n'+item.request+'\n\nName / organisation:\nContribution:\nLocation:\nContact:\n');
const JOURNAL=[
{date:'2026-11-23',type:'Engineering log',title:'Maritime evidence and historical investigations',description:'Built internal evidence dossiers from X and maritime RSS sources; added historical AIS context and a first bounded designated-vessel monitoring sample.',status:'Internal pilot',reference:'Commits 0c2d81cd, 5ab64ca1, 7c6327e6'},
{date:'2026-11-23',type:'Product update',title:'FUTURES contribution pathways',description:'Added targeted requests for compute, radio receivers, satellite resources, archives, field nodes and research partners.',status:'Frontend change',reference:'Commit 1836a194'},
];
const PARTNER_UPDATES=[
{date:'2026-11-23',title:'Investigation engine: what partners can test',summary:'The pilot now contains internal maritime investigation dossiers and bounded sanctioned-vessel monitoring. These are evidence-review tools, not published findings of unlawful activity.',action:'Interested in contributing shipping registries, AIS history or independent source verification?'},
{date:'2026-11-23',title:'Coastal receiver collaboration',summary:'SeaCommons is preparing a model for coastal AIS/VHF/DSC receiver nodes. Site permissions, signal coverage, hardware reliability and maintenance remain prerequisites.',action:'Partners with suitable coastal sites or receiver expertise can propose a technical assessment.'},
];
function PartnerUpdates(){return <section className="futures-journal" id="partner-updates" aria-labelledby="partner-updates-title"><small>PARTNER BRIEFINGS / REVIEWED MILESTONES</small><h2 id="partner-updates-title">Updates for partners</h2><p>Concrete opportunities and project changes, dated and clearly separated from verified maritime findings. This section is editorially maintained, not a live newswire.</p><div className="futures-journal-list">{PARTNER_UPDATES.map(entry=><article key={entry.title}><div><time dateTime={entry.date}>{entry.date}</time><small>Partner update</small></div><div><h3>{entry.title}</h3><p>{entry.summary}</p><p>{entry.action}</p><a href={'mailto:republic@suezcanal.xyz?subject='+encodeURIComponent('SeaCommons partner response — '+entry.title)}>Respond to this update ↗</a></div></article>)}</div></section>}
function FuturesJournal(){return <section className="futures-journal" id="futures-journal" aria-labelledby="futures-journal-title"><small>DOCUMENTED WORK / PARTNER BRIEFINGS</small><h2 id="futures-journal-title">Development log & partner updates</h2><p>Entries below refer to documented engineering work, not automatically verified field outcomes. This is a curated development log, not a complete daily activity feed; days without an entry should not be interpreted as inactive.</p><div className="futures-journal-list">{JOURNAL.map(entry=><article key={entry.title}><div><time dateTime={entry.date}>{entry.date}</time><small>{entry.type} · {entry.status}</small></div><div><h3>{entry.title}</h3><p>{entry.description}</p><small>{entry.reference}</small></div></article>)}</div><p className="futures-journal-note">For partner-specific progress, deployment evidence or collaboration requests, contact <a href="mailto:republic@suezcanal.xyz?subject=SeaCommons%20FUTURES%20partner%20update">republic@suezcanal.xyz</a>. Future entries should be published only after review against logs and source records.</p></section>}
function ResearchIndex(){
 const [tab,setTab]=React.useState('Methods');
 const items={
 Methods:[['AIS','Vessel observations','Broadcast positions and identity fields are retained with reception timestamps. Coverage and identity conflicts limit interpretation.'],['RADIO','Maritime communications','Received messages retain source and time metadata. Interpretation requires independent corroboration.'],['IMAGERY','Satellite evidence','Acquisition time, resolution and coverage determine whether an image supports a historical observation.'],['REPORTS','Public documentation','Original documents and reported claims are preserved separately from independently verified observations.']],
 Roadmap:[['PROPOSED','Historical dossier player','A reusable map and timeline for reviewed historical evidence, with explicit gaps and source references.'],['PROPOSED','Coastal infrastructure','Site assessment, power, reception and maintenance requirements for experimental receiver nodes.'],['PROPOSED','Drifter','Field instrumentation research and calibration before operational use.']],
 Agents:[['PLANNED','Engineering review','Derive release notes from reviewed commits, tests and deployment records.'],['PLANNED','Planning review','Record dependencies and proposed work separately from completed milestones.'],['PLANNED','Publication review','Validate public claims against source records before release.']]};
 return <section className="futures-index"><h2>Research & development</h2><p>Methods, planned work and publication controls for the SeaCommons pilot.</p><div className="futures-switcher" role="group" aria-label="Research section">{Object.keys(items).map(k=><button key={k} type="button" aria-pressed={tab===k} onClick={()=>setTab(k)}>{k}</button>)}</div>{items[tab].map(([tag,title,body])=><details key={title}><summary><span className="futures-pill">{tag}</span><strong>{title}</strong><span aria-hidden="true">+</span></summary><p>{body}</p></details>)}</section>
}
export default function FuturesOverview({onStatus}){
return <div className="futures-public">
<section className="futures-intro" aria-labelledby="futures-intro-title">
  <div className="futures-intro__masthead"><span>SEA COMMONS <i>/</i> A SUEZ REPUBLIC PROJECT</span><span>RESEARCH PLATFORM · PILOT 2026</span></div>
  <div className="futures-intro__hero">
    <div className="futures-intro__copy">
      <span className="futures-pill">Research pilot</span>
      <h2 id="futures-intro-title">Maritime research<br/><em>infrastructure</em></h2>
      <p className="futures-lead">SeaCommons is an open maritime research platform. It brings together vessel signals, public reports and geospatial evidence to investigate what happens at sea — and make clear what remains unknown.</p>
      <div className="futures-intro__links"><a href="https://live.seacommons.org">Explore LIVE <span>↗</span></a><a href="https://play.seacommons.org">Explore PLAY <span>↗</span></a></div>
    </div>
    <figure className="futures-intro__visual"><img src="/visualizations/live-visual.png" alt="SeaCommons LIVE interface showing maritime observations on a map" loading="eager"/></figure>
  </div>
</section>
<section className="futures-story" aria-labelledby="futures-story-title">
  <div className="futures-story__heading"><div><h2 id="futures-story-title">Data sources and verification</h2><p>SeaCommons connects observations without treating them as interchangeable. A vessel position, a radio message, a satellite image and a public report each establish something different.</p></div></div>
  <div className="futures-story__sources">
    <article><span>01 / AIS</span><h3>Vessel positions</h3><p>Received broadcasts describe a vessel at a specific time. A gap in reception is not proof of where it travelled.</p></article>
    <article><span>02 / RADIO</span><h3>Communications</h3><p>Time-stamped transmissions help reconstruct a chronology. Attribution and interpretation require review.</p></article>
    <article><span>03 / SATELLITE</span><h3>Imagery</h3><p>Optical and radar scenes can corroborate visible features at acquisition time, subject to coverage and resolution.</p></article>
    <article><span>04 / REPORTS</span><h3>Documented claims</h3><p>Public reports and distress alerts establish what was reported, not automatically what was independently verified.</p></article>
  </div>
  <div className="futures-story__principle"><span>OUR METHOD</span><p>Collect the source. Preserve the timestamp. Compare the evidence. <strong>Publish the uncertainty.</strong></p></div>
</section>
<section className="futures-surfaces" aria-labelledby="futures-surfaces-title">
  <div className="futures-surfaces__heading"><h2 id="futures-surfaces-title">Research interfaces</h2></div>
  <div className="futures-surfaces__grid">
    <a href="https://live.seacommons.org" className="futures-surface"><div className="futures-surface__image"><img src="/visualizations/live-visual.png" alt="SeaCommons LIVE maritime map" loading="lazy"/></div><div className="futures-surface__body"><span>01 / OBSERVE</span><h3>LIVE <b>↗</b></h3><p>Explore the latest available vessel observations and contextual reports, with their source and temporal limitations.</p></div></a>
    <a href="https://play.seacommons.org" className="futures-surface"><div className="futures-surface__image"><img src="/visualizations/play-visual.png" alt="SeaCommons PLAY historical investigation map" loading="lazy"/></div><div className="futures-surface__body"><span>02 / INVESTIGATE</span><h3>PLAY <b>↗</b></h3><p>Examine past events through historical positions, timelines, conflicting sources and gaps in the record.</p></div></a>
  </div>
</section>
<section className="futures-purpose" aria-labelledby="futures-purpose-title">
  <div className="futures-purpose__heading"><div><h2 id="futures-purpose-title">Research applications</h2><p>The same research infrastructure can support different questions. Each application has its own evidentiary threshold and requires specialist review.</p></div></div>
  <div className="futures-purpose__list">
    <article><span>01</span><h3>Humanitarian</h3><p>Document distress reports, maritime response and unresolved questions without turning approximate coordinates into confirmed positions.</p></article>
    <article><span>02</span><h3>Environmental</h3><p>Relate maritime activity to independently measured ocean conditions, imagery and future field instruments.</p></article>
    <article><span>03</span><h3>Security & accountability</h3><p>Review incident chronologies and vessel identities while keeping reports, observations and attribution distinct.</p></article>
    <article><span>04</span><h3>Coastal infrastructure</h3><p>Develop receiver stations and experimental drifters through site surveys, documented tests and local partnerships.</p></article>
  </div>
  <div className="futures-purpose__closing"><div><span>THE NEXT CHAPTER</span><h3>Development priorities</h3></div><p>The next stage focuses on improved reception coverage, reproducible case reviews, calibrated field instruments and partner-led evaluation.</p></div>
</section>
<ResearchIndex/><KnowledgeLibrary compact/>
<FuturesJournal/>
<PartnerUpdates/>
<section className="futures-needs" id="futures-needs" aria-labelledby="futures-needs-title">
<small>CONTRIBUTE TO THE COMMONS</small><h2 id="futures-needs-title">What SeaCommons needs next</h2>
<p>These are concrete infrastructure and research needs. Select a resource to send a targeted contribution proposal to republic@suezcanal.xyz.</p>
<div className="futures-needs-grid">{needs.map((item,i)=><article className="futures-need" key={item.title}>
<div className="futures-need-top"><span className="futures-need-icon"><Icon name={iconNames[i]}/></span><small>{item.tag}</small></div>
<h3>{item.title}</h3><p>{item.description}</p><p className="futures-examples"><strong>Useful contributions</strong>{item.examples}</p>
<a className="futures-need-cta" href={email(item)} aria-label={'Offer support: '+item.title}>Offer support ↗</a>
</article>)}</div>
<div className="futures-contact"><div><h3>Have a different idea?</h3><p>Share a dataset, propose a collaboration or ask a question. The button opens your email app with a draft; nothing is sent automatically.</p></div><a className="futures-need-cta" href="mailto:republic@suezcanal.xyz?subject=SeaCommons%20FUTURES%20collaboration">Contact Suez Republic ↗</a></div>
</section></div>
}
