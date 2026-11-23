import React from 'react';

const sources = [
 {id:'ais',name:'AIS',type:'track',detail:'Time-stamped vessel positions and broadcast identities. Receiver coverage determines which signals are available.'},
 {id:'radio',name:'Radio',type:'coastal',detail:'Received maritime radio messages, with reception time and source metadata.'},
 {id:'satellite',name:'Satellite',type:'satellite',detail:'Available optical or radar imagery, compared using acquisition time and geographic coverage.'},
 {id:'reports',name:'Public reports',type:'research',detail:'Published accounts with their original source, reported time and location precision.'},
];
function EvidenceFlow(){
 const [active,setActive]=React.useState('ais');
 const selected=sources.find(s=>s.id===active);
 return <div className="evidence-interactive">
  <div className="evidence-network">
   <div className="evidence-inputs">{sources.map(s=><button key={s.id} type="button" aria-pressed={active===s.id} onClick={()=>setActive(s.id)} onFocus={()=>setActive(s.id)} className={active===s.id?'is-active':''}><DomainIcon type={s.type}/><span>{s.name}</span></button>)}</div>
   <svg className="evidence-edges" viewBox="0 0 200 300" preserveAspectRatio="none" aria-hidden="true">{sources.map((s,i)=><path key={s.id} className={active===s.id?'is-active':''} d={`M0 ${37.5+i*75} C 90 ${37.5+i*75},110 150,200 150`}/>)}</svg>
   <div className="evidence-core"><div className="evidence-radar"><i/><i/><i/><svg viewBox="0 0 100 100" aria-hidden="true"><path d="M12 68L38 43 58 54 85 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeDasharray="4 4"/><circle cx="38" cy="43" r="4" fill="currentColor"/><circle cx="85" cy="24" r="4" fill="currentColor"/></svg></div><strong>Source comparison</strong><small>Time · location · provenance</small></div>
   <div className="evidence-output-edge" aria-hidden="true"/>
   <div className="evidence-record"><DomainIcon type="research"/><strong>Case record</strong><small>Chronology · uncertainty</small><a href="https://play.seacommons.org">PLAY ↗</a></div>
  </div>
  <div className="evidence-inspector" aria-live="polite"><strong>{selected.name}</strong><p>{selected.detail}</p><a href="/docs">Source documentation ↗</a></div>
 </div>;
}

function DomainIcon({type}) {
  const common={fill:"none",stroke:"currentColor",strokeWidth:2,strokeLinecap:"round",strokeLinejoin:"round"};
  const graphic={
    track:<><path d="M11 70l20-23 20 10 26-42" strokeDasharray="5 5"/><circle cx="11" cy="70" r="4"/><circle cx="77" cy="15" r="4"/><path d="M10 13h23v18M56 68h21V47"/></>,
    rescue:<><path d="M12 67q16-12 32 0t32 0M12 77q16-12 32 0t32 0"/><circle cx="44" cy="33" r="19"/><circle cx="44" cy="33" r="8"/><path d="M44 14v11M44 41v11M25 33h11M52 33h11"/></>,
    environment:<><path d="M10 62q17-20 34 0t34 0M10 74q17-20 34 0t34 0"/><path d="M44 12v36M35 21l9-9 9 9"/><circle cx="44" cy="48" r="5"/><path d="M19 27l12 9-12 9"/></>,
    security:<><circle cx="44" cy="44" r="31"/><circle cx="44" cy="44" r="18"/><path d="M44 7v18M44 63v18M7 44h18M63 44h18"/><circle cx="44" cy="44" r="5" fill="currentColor"/></>,
    ports:<><path d="M9 71h70M17 58h55l-9 13H25zM27 17v41M27 18h39v24H27M27 29h39M49 17v25"/><path d="M9 78q12-8 24 0t24 0t22 0"/></>,
    research:<><rect x="11" y="14" width="66" height="60" rx="3"/><path d="M20 59l14-15 11 9 22-25M20 65h47M20 24h21"/><circle cx="67" cy="28" r="4"/></>,
    satellite:<><path d="M18 18l52 52M22 44l22-22M44 66l22-22M16 51l21 21M51 16l21 21"/><rect x="12" y="43" width="20" height="20" transform="rotate(-45 22 53)"/><rect x="56" y="25" width="20" height="20" transform="rotate(-45 66 35)"/><circle cx="44" cy="44" r="5"/></>,
    coastal:<><path d="M12 75h64M20 65l24-43 24 43M44 22v43M30 47h28M36 36h16"/><path d="M20 16q24-20 48 0M28 21q16-12 32 0" strokeOpacity=".65"/></>,
  };
  return <svg viewBox="0 0 88 88" role="img" aria-label={type} {...common}>{graphic[type]||graphic.research}</svg>;
}

const applications=[
  {type:'rescue',label:'Search & rescue',detail:'Trace reported distress positions, response timelines and later updates.',state:'PUBLIC REPORTS'},
  {type:'environment',label:'Marine environment',detail:'Place vessel activity alongside ocean conditions and environmental observations.',state:'RESEARCH SCOPE'},
  {type:'track',label:'Vessel movements',detail:'Review received positions, gaps in coverage and changes in route.',state:'LIVE + HISTORICAL'},
  {type:'security',label:'Maritime security',detail:'Compare incident reports, vessel identities and available movement records.',state:'SOURCE REVIEW'},
  {type:'ports',label:'Ports & coastal areas',detail:'Study approaches, anchorage activity and the limits of coastal reception.',state:'GEOGRAPHIC CONTEXT'},
  {type:'satellite',label:'Satellite corroboration',detail:'Compare optical or radar imagery with dated maritime observations.',state:'IMAGERY REVIEW'},
  {type:'coastal',label:'Coastal observation',detail:'Evaluate receive-only stations, coverage and field calibration.',state:'PROPOSED HARDWARE'},
  {type:'research',label:'Public research',detail:'Create documented case histories for teaching and independent review.',state:'KNOWLEDGE ACCESS'},
];

export default function ProductShowcase(){
  return <div className="product-showcase">
    <section id="how-it-works" className="product-showcase__intro">
      <div className="product-showcase__intro-label"><h2>Evidence workflow</h2><a href="/docs">Research methods ↗</a></div>
      <EvidenceFlow/>
    </section>
    <section className="product-showcase__surfaces">
      <div className="product-showcase__section-head"><div className="product-showcase__surface-symbols" aria-hidden="true"><DomainIcon type="track"/><DomainIcon type="research"/></div></div>
      <div className="product-showcase__screens">
        <a href="https://live.seacommons.org"><div className="product-showcase__screen"><img src="/visualizations/live-visual.png" alt="SeaCommons LIVE map visualization" loading="lazy"/></div><div className="product-showcase__screen-foot"><div><small>RECENT OBSERVATIONS</small><h3>LIVE</h3><p>Explore public cases and source records.</p></div><span aria-hidden="true">↗</span></div></a>
        <a href="https://play.seacommons.org"><div className="product-showcase__screen"><img src="/visualizations/play-visual.png" alt="SeaCommons PLAY case timeline visualization" loading="lazy"/></div><div className="product-showcase__screen-foot"><div><small>HISTORICAL REVIEW</small><h3>PLAY</h3><p>Examine events and their evidence over time.</p></div><span aria-hidden="true">↗</span></div></a>
      </div>
    </section>
    <section id="examples" className="product-showcase__possibilities">
      <div className="product-showcase__section-head"><span className="product-overline">RESEARCH APPLICATIONS</span><a className="product-showcase__method-link" href="/docs">Methods & source limitations ↗</a></div>
      <div className="product-showcase__applications">{applications.map(item=><article key={item.type} className="product-showcase__application"><div className="product-showcase__application-top"><DomainIcon type={item.type}/><small>{item.state}</small></div><h3>{item.label}</h3><p>{item.detail}</p></article>)}</div>
      <div className="product-showcase__network"><div><span>FIELD RESEARCH / OPEN INFRASTRUCTURE</span><h3>Coastal research infrastructure</h3></div><p>Coastal receivers, vessel observations, field instruments and public archives can contribute to a common research record. Each new site requires a defined scope, local validation and documented data access.</p><a href="/docs">Explore the research framework ↗</a></div>
    </section>
    <section className="product-showcase__feature"><div className="product-showcase__feature-image"><img src="/visualizations/ais-gap-visual.png" alt="SeaCommons research visualization of a vessel position gap and its timeline" loading="lazy"/><span>ILLUSTRATIVE RESEARCH VISUALIZATION</span></div><div className="product-showcase__feature-copy"><span className="product-overline">AIS / HISTORICAL REVIEW</span><h2>AIS reception gaps</h2><p>Review the last received position, the next available signal and receiver coverage.</p><a href="https://play.seacommons.org">Open PLAY ↗</a><a href="/docs">Evidence guide ↗</a></div></section>
    <section className="product-showcase__end"><h2>Explore the record.</h2><div><a href="https://live.seacommons.org">LIVE ↗</a><a href="https://play.seacommons.org">PLAY ↗</a><a href="/docs">DOCS ↗</a></div></section>
  </div>;
}
