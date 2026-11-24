import {L} from './locale.jsx';
import React, {useEffect,useState} from 'react';
import GlossaryText from './GlossaryText.jsx';
import KeyFigures from './KeyFigures.jsx';
import {retainedEvidence,nonnegativeCount} from './retainedEvidence.js';
import {contributionNeeds} from './contributionNeeds.js';
import KnowledgeLibrary from './KnowledgeLibrary.jsx';
import './overview-editorial.css';

const tabs=['Overview','Applications','Resources','Governance','Development'];
const maturity=[
 ['LIVE','Pilot','Public interface for maritime observations; current availability is shown in Operations.','operations'],
 ['PLAY','Pilot','Historical incident archive; publication depends on evidence review.','history'],
 ['Evidence archive','Implemented','Retained normalized records measured by the aggregate API.','intelligence'],
 ['Satellite evidence','Research','Scene availability, acquisition time and interpretation require case-level verification.','platform'],
 ['Interactive dossiers','Proposed','Historical evidence timeline, source references and explicit observation gaps.','roadmap'],
 ['Coastal nodes','Proposed','Site permission, calibration and maintenance are prerequisites for field tests.','hardware'],
 ['Drifter','Research','Recoverable instrument prototype; endurance and accuracy require validation.','hardware'],
 ['Agent workflows','Partial','Read-only scheduled-task snapshot; automated editorial publication is not enabled.','agents']
];
const applications=[
 ['Environment','Historical environmental incidents and ocean conditions','Historical imagery and independent environmental measurements','A reproducible case review with source dates and uncertainty.','Research partner with oceanographic expertise'],
 ['Humanitarian','Documented maritime distress and response','Reviewed public reports and historical evidence','A chronology preserving source provenance and privacy.','Humanitarian research organisation'],
 ['Maritime','Civil navigation safety and sanctions accountability','Official designations and reviewed historical records','A documented administrative and incident history, with no inferred attribution.','Maritime law or safety specialist'],
 ['Education','Open research and critical data literacy','Methods, source documentation and case studies','Teaching material with reproducible methods and explicit limitations.','University or cultural institution'],
 ['Economy','Historical disruption to maritime trade','Public economic records and documented incidents','A comparative assessment of documented impacts.','Economics or logistics researcher'],
 ['Territory','Coastal research infrastructure','Permitted field sites and calibrated instruments','A site assessment and field validation report.','Local institution or community']
];
const governance=[
 ['Evidence and publication','Original sources, timestamps and uncertainty remain visible. Distinguish reported claims from independently corroborated observations; release case reports only after review.'],
 ['Privacy and access','Public research material must exclude sensitive personal data and operationally sensitive locations. Restricted research data requires defined access and retention rules.'],
 ['Licensing and reproducibility','Source permissions govern reuse. Record dataset licence, acquisition date and processing steps; consult the repository for software licence and documentation.'],
 ['Accountability','Agree on a named technical owner, research reviewer and partner contact for each collaboration. Formal governance and named responsibilities require confirmation by Suez Republic.'],
 ['Risk and continuity','Coverage gaps, conflicting identities, source outages and storage failures affect interpretation and availability. Operational metrics and restore tests support evaluation.'],
 ['Financial transparency','Planning estimates are separate from incurred expenditure. Confirm procurement scope, maintenance, actual costs and funding commitments before approval.']
];
const pathways=[
 ['Foundations','Fund a bounded work package with an agreed budget, deliverables and evaluation criteria.'],
 ['Universities','Co-design a reproducible study, teaching module or independent methodology review.'],
 ['Maritime institutions','Contribute lawful historical documentation and specialist safety or legal review.'],
 ['NGOs','Review historical cases, publication safeguards and public-interest research questions.'],
 ['Technology partners','Provide isolated compute, backup capacity or documented data access with agreed acceptance tests.'],
 ['Local communities','Explore a permitted field research site with local maintenance and shared evaluation.']
];
const fmt=n=>n===null||n===undefined?'Unavailable':new Intl.NumberFormat('en-GB').format(n);
function Pill({children}){return <span className={'partner-pill '+(['Proposed','Research','Partial'].includes(children)?'partner-pill--plan':'')}><L>{children}</L></span>}
function Copy({children}){return <p><GlossaryText>{children}</GlossaryText></p>}
function Section({title,children}){return <section className="partner-section"><h2><L>{title}</L></h2><L>{children}</L></section>}
function Expand({title,tag,children}){return <details className="partner-detail"><summary>{tag&&<Pill>{tag}</Pill>}<strong><L>{title}</L></strong><span aria-hidden="true">+</span></summary><div><L>{children}</L></div></details>}
function Jump({navigate,to,children}){return <button className="partner-link" type="button" onClick={()=>navigate(to)}><L>{children}</L> ↗</button>}
function Evidence({overall,ops,navigate}){
 const data=retainedEvidence(overall?.history);
 const total=data?.total??null,located=data?.positioned??null;
 const percent=total>0?100*located/total:null;
 const published=nonnegativeCount(ops?.counts?.total_count);
 return <Section title="Archive and data quality"><Copy>Current retained normalized records are counted separately from raw archive exports and published cases. Coordinates describe stored fields; they do not establish accuracy or independent verification.</Copy>
 <KeyFigures items={[
 {value:overall?.loading?'Loading…':total===null?null:fmt(total),title:'Retained records',detail:'Normalized source records currently held in the database.'},
 {value:percent===null?null:percent.toFixed(1)+'%',title:'Coordinate completeness',detail:'Share of records with stored coordinates; accuracy is assessed separately.'},
 {value:published===null?null:fmt(published),title:'PLAY archive records',detail:'Separate archive inventory. Do not add to retained records.'}
 ]}/>
 <p className="future-data-provenance">Evidence snapshot: <L>{data?new Date(data.generatedAt).toLocaleString():'Unavailable'}</L> · PLAY count: <L>{ops?.counts?.generated_at?new Date(ops.counts.generated_at).toLocaleString():'Timestamp unavailable'}</L></p>
 <div className="partner-bar" role="img" aria-label={percent===null?'Position coverage unavailable':percent.toFixed(1)+' percent of retained records have coordinates'}>{percent!==null&&<span style={{width:percent+'%'}}/>}</div>
 <div className="partner-legend"><span>With coordinates: <L>{fmt(located)}</L></span><span>Without coordinates: <L>{fmt(data?total-located:null)}</L></span></div>
 <dl className="partner-facts"><div><dt>Geographic coverage and distinct identities</dt><dd>See detailed metrics; no aggregate asserted here</dd></div></dl>
 <Jump navigate={navigate} to="intelligence">Inspect evidence metrics</Jump><Jump navigate={navigate} to="operations">Service status</Jump></Section>
}
function Releases(){
 const [state,setState]=useState({loading:true,entries:[],error:false});
 useEffect(()=>{let active=true;let controller;const refresh=async()=>{controller?.abort();controller=new AbortController();try{const r=await fetch('https://api.github.com/repos/suezcanalxyz/seacommons/releases?per_page=10',{signal:controller.signal,headers:{Accept:'application/vnd.github+json'}});if(!r.ok)throw Error('release feed');const data=await r.json();if(!Array.isArray(data))throw Error('format');if(active)setState({loading:false,error:false,entries:data.filter(x=>!x.draft&&!x.prerelease&&typeof x.published_at==='string'&&typeof x.tag_name==='string').map(x=>({tag:x.tag_name,date:x.published_at,name:x.name||x.tag_name}))});}catch(e){if(active&&e.name!=='AbortError')setState({loading:false,error:true,entries:[]});}};refresh();const timer=setInterval(()=>{if(document.visibilityState==='visible')refresh()},300000);return()=>{active=false;clearInterval(timer);controller?.abort()}},[]);
 return <Section title="Published releases"><Copy>The public GitHub release feed refreshes every five minutes while this view is visible. Only published stable releases are shown; release metadata does not certify operational performance.</Copy>{state.loading?<p role="status">Loading releases…</p>:state.error?<p role="status">Release feed unavailable.</p>:state.entries.length===0?<p>No stable releases returned by GitHub.</p>:state.entries.map(x=><article className="partner-release" key={x.tag}><Pill>Published</Pill><strong><L>{x.name}</L></strong><time dateTime={x.date}><L>{x.date.slice(0,10)}</L></time><a href={'https://github.com/suezcanalxyz/seacommons/releases/tag/'+encodeURIComponent(x.tag)}>Release notes ↗</a></article>)}<a href="https://github.com/suezcanalxyz/seacommons/releases">GitHub releases ↗</a></Section>
}
export default function FuturesOverview({navigate,ops,overall}){
 const [tab,setTab]=useState('Overview');
 const [sector,setSector]=useState('Environment');
 const app=applications.find(a=>a[0]===sector);
 return <div className="futures-public partner-workspace">
 <section className="futures-plain-intro"><Pill>Research pilot</Pill><h2>SeaCommons FUTURES</h2><Copy>Open maritime research infrastructure for historical evidence, environmental research and public accountability. Explore current capabilities, methodological limits, development priorities and collaboration opportunities.</Copy><nav aria-label="Platform links"><a href="https://live.seacommons.org">LIVE ↗</a><a href="https://play.seacommons.org">PLAY ↗</a><a href="https://seacommons.org/docs">Documentation ↗</a><a href="https://github.com/suezcanalxyz/seacommons">Repository ↗</a></nav></section>
 <div className="futures-switcher partner-tabs" role="group" aria-label="Partner information">{tabs.map(t=><button key={t} aria-pressed={tab===t} onClick={()=>setTab(t)} type="button"><L>{t}</L></button>)}</div>
 {tab==='Overview'&&<>
 <Evidence overall={overall} ops={ops} navigate={navigate}/>
 <Section title="Development priorities"><Copy>Ordered resource requirements from the project contribution register. These priorities are planning decisions; progress must be verified in the delivery record.</Copy><div className="partner-priority-list">{[...contributionNeeds].sort((a,b)=>a.rank-b.rank).slice(0,3).map(n=><article key={n.name}><strong className="partner-priority-number"><L>{String(n.rank).padStart(2,'0')}</L></strong><div><h3><L>{n.name}</L></h3><Copy>{n.plainReason}</Copy><details><summary>Expected result and acceptance</summary><Copy>{n.use}</Copy><Copy>{n.acceptance}</Copy></details></div><div><Pill>{n.urgency}</Pill><p className="partner-price"><L>{n.cost}</L></p></div></article>)}</div><Jump navigate={navigate} to="roadmap">Delivery sequence</Jump><Jump navigate={navigate} to="contributions">All resource requirements</Jump></Section>
 <Section title="Technology readiness"><Copy>These are editorial maturity descriptions based on the current project scope. Operational availability and test results are documented separately.</Copy><div className="partner-table-wrap"><table className="partner-table"><thead><tr><th>Component</th><th>Maturity</th><th>Scope and evidence</th></tr></thead><tbody>{maturity.map(([name,status,desc,to])=><tr key={name}><td><Jump navigate={navigate} to={to}>{name}</Jump></td><td><Pill>{status}</Pill></td><td><GlossaryText>{desc}</GlossaryText></td></tr>)}</tbody></table></div></Section>
 <Section title="Developer access"><Copy>Developers can inspect the source repository, compile the public frontend and run evidence-contract tests. The developer guide lists package manifests, dependency requirements and the release checks still required for a reproducible standalone distribution.</Copy><Jump navigate={navigate} to="tools">Developer resources</Jump><a href="https://seacommons.org/docs#developer-guide">Public quickstart ↗</a></Section>
 <Section title="Research interfaces">{[['LIVE','live','Available observations and source context.'],['PLAY','play','Historical incident records and evidence review.']].map(([title,key,description])=><article className="partner-interface" key={key}><img src={'/visualizations/'+key+'-visual.png'} alt={'SeaCommons '+title+' interface visualization'} loading="lazy"/><div><h3><L>{title}</L></h3><Copy>{description}</Copy><a href={'https://'+key+'.seacommons.org'}><L>Open </L><L>{title}</L> ↗</a></div></article>)}</Section>
 </>}
 {tab==='Applications'&&<Section title="Research applications"><div className="futures-switcher" role="group" aria-label="Research sector">{applications.map(a=><button key={a[0]} type="button" aria-pressed={sector===a[0]} onClick={()=>setSector(a[0])}><L>{a[0]}</L></button>)}</div><h3><L>{app[1]}</L></h3><dl className="partner-facts">{['Evidence requirements','Expected output','Potential collaborator'].map((label,i)=><div key={label}><dt><L>{label}</L></dt><dd><GlossaryText>{app[i+2]}</GlossaryText></dd></div>)}</dl><Copy>Applications are potential research collaborations; outcomes and partners require a defined study and agreement.</Copy></Section>}
 {tab==='Resources'&&<Section title="Resource requirements"><Copy>Existing project planning estimates are shown below. They are not actual expenditure, committed funding or procurement quotations. Costs may overlap and should not be summed without a scoped budget.</Copy>{[...contributionNeeds].sort((a,b)=>a.rank-b.rank).map(n=><Expand key={n.name} title={n.name} tag={n.urgency}><Copy>{n.plainReason}</Copy><dl className="partner-facts"><div><dt>Planning estimate</dt><dd><L>{n.cost}</L></dd></div><div><dt>Partner role</dt><dd><GlossaryText>{n.partnerRole}</GlossaryText></dd></div><div><dt>Acceptance criteria</dt><dd><GlossaryText>{n.acceptance}</GlossaryText></dd></div></dl></Expand>)}<Jump navigate={navigate} to="contributions">Contribution catalogue</Jump><Jump navigate={navigate} to="hardware">Hardware specifications</Jump></Section>}
 {tab==='Governance'&&<><Section title="Governance and research safeguards"><Copy>Proposed evaluation criteria for partner due diligence. Formal commitments and named responsibilities must be confirmed before a collaboration begins.</Copy>{governance.map(([title,body])=><Expand key={title} title={title}><Copy>{body}</Copy><p className="future-data-provenance">Partner review: identify the accountable owner, supporting documents and acceptance conditions before agreeing a work package.</p></Expand>)}</Section><Section title="Collaboration pathways">{pathways.map(([title,body])=><Expand key={title} title={title}><Copy>{body}</Copy><a href={'mailto:republic@suezcanal.xyz?subject='+encodeURIComponent('SeaCommons collaboration — '+title)}>Discuss a pilot ↗</a></Expand>)}</Section></>}
 {tab==='Development'&&<><Section title="Development and agents"><Copy>Existing operations and scheduled-task views provide technical evidence and a protected read-only snapshot. Automated editorial release generation and planning remain proposed capabilities.</Copy>{[['Engineering review','Proposed','Summarise reviewed tests, commits and release records.'],['Data quality','Partial','Existing aggregate metrics describe retained data; further independent review is required.'],['Planning review','Proposed','Record dependencies, acceptance criteria and versioned proposed plans.'],['Publication review','Proposed','Review public claims against source documentation and approval criteria.']].map(([title,status,body])=><Expand key={title} title={title} tag={status}><Copy>{body}</Copy></Expand>)}<Jump navigate={navigate} to="agents">Scheduled tasks</Jump><Jump navigate={navigate} to="roadmap">Development roadmap</Jump><Jump navigate={navigate} to="updates">Reviewed updates</Jump></Section><Releases/></>}
 {tab==='Overview'&&<KnowledgeLibrary compact/>}
 <section className="partner-section"><h2>Discuss a collaboration</h2><Copy>Define a research question, deliverable, budget and review process with Suez Republic.</Copy><a href="mailto:republic@suezcanal.xyz?subject=SeaCommons%20research%20partnership">republic@suezcanal.xyz ↗</a></section>
 </div>
}
