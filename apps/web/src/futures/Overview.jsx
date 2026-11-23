import React from 'react';
import KnowledgeLibrary from './KnowledgeLibrary.jsx';
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
export default function FuturesOverview({onStatus}){
return <div className="futures-public">
<section className="futures-intro" aria-labelledby="futures-intro-title">
<small>SEA COMMONS / AN OPEN MARITIME OBSERVATORY</small>
<h2 id="futures-intro-title">Understand what happens at sea. Make better decisions on land.</h2>
<p className="futures-lead">SeaCommons brings together ship movements, radio signals, satellite images and documented reports in one place. It helps people understand maritime activity, investigate risks and make better-informed decisions. The platform is currently in its pilot phase.</p>
<div className="futures-journey">
<a href="https://live.seacommons.org"><Icon name="radio"/><small>01 / LIVE</small><strong>See the sea today</strong><span>Explore current observations and reported incidents.</span><b>Explore LIVE ↗</b></a>
<a href="https://play.seacommons.org"><Icon name="ship"/><small>02 / PLAY</small><strong>Explore past events</strong><span>Follow historical events, timelines and supporting evidence.</span><b>Explore PLAY ↗</b></a>
<a href="#futures-needs"><Icon name="people"/><small>03 / FUTURES</small><strong>Build the next step</strong><span>Understand the infrastructure and contribute to its future.</span><b>Explore FUTURES ↓</b></a>
</div>
<p className="futures-method">We show where information comes from and what remains uncertain. SeaCommons supports research and informed action; it does not replace emergency services or maritime authorities.</p>
<button className="futures-secondary" onClick={onStatus}>View live operational diagnostics ↗</button>
</section>
<section className="futures-impact" aria-labelledby="futures-impact-title">
<small>WHY THIS MATTERS</small>
<h2 id="futures-impact-title">A shared tool for people, the economy and the environment</h2>
<p>The sea connects trade, communities and ecosystems. Better information helps researchers, public institutions and local partners understand what is happening and decide where action is needed.</p>
<div className="futures-impact-grid">
<article><Icon name="chart" size={30}/><h3>Economic</h3><p>Improve the traceability of shipping activity, identify evidence gaps in trade and sanctions investigations, and reduce duplicated research work. The project does not claim to measure economic losses without validated datasets.</p></article>
<article><Icon name="people" size={30}/><h3>Social</h3><p>Make humanitarian distress reports, search-and-rescue evidence and public maritime records more accessible to researchers, civil society and responsible institutions.</p></article>
<article><Icon name="leaf" size={30}/><h3>Environmental</h3><p>Investigate vessel movements, suspected spills and maritime risks using observations and satellite data, distinguishing documented impacts from modelled scenarios.</p></article>
</div>
<h3>From information to practical action</h3>
<ol className="futures-steps"><li><strong>Observe:</strong> collect lawful AIS, radio, satellite and public documentary signals with provenance.</li><li><strong>Corroborate:</strong> connect independent evidence and explicitly flag contradictions and missing coverage.</li><li><strong>Publish:</strong> expose qualified findings through LIVE and PLAY, with dates, sources and uncertainty.</li><li><strong>Deploy locally:</strong> test coastal receivers, solar-powered nodes, partner data agreements and maintenance responsibilities.</li><li><strong>Evaluate:</strong> measure uptime, data quality, response usefulness, costs and documented outcomes before scaling.</li></ol>
<p>The goal is a model that local partners can operate and maintain: clear responsibilities, affordable equipment, transparent methods and measurable results.</p>
</section>
<KnowledgeLibrary compact/>
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
