import React from 'react';

function EvidenceFlow() {
  return <svg className="product-flow product-flow--detailed" viewBox="0 0 1120 270" role="img" aria-label="Evidence process: time-stamped vessel signals, radio and reports are aligned, cross-checked and documented in case records">
    <defs>
      <pattern id="sc-flow-grid" width="18" height="18" patternUnits="userSpaceOnUse"><path d="M18 0H0V18" stroke="#8bb6a8" strokeOpacity=".13" fill="none"/></pattern>
      <marker id="sc-flow-arrow" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto"><path d="M0 0L7 4 0 8" fill="none" stroke="#a5d3bd" strokeWidth="1.3"/></marker>
    </defs>
    {[0,380,760].map((x,i)=><g key={x}><rect x={x+8} y="10" width="344" height="248" rx="2" fill="#0c1c21" stroke="#54766d" strokeWidth="1"/><rect x={x+9} y="11" width="342" height="246" fill="url(#sc-flow-grid)"/><text x={x+28} y="38" fill="#9abeb0" fontSize="11" letterSpacing="2">{['01 / INPUT','02 / REVIEW','03 / RECORD'][i]}</text></g>)}
    <g fill="none" stroke="#aed4c4" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <path d="M42 93h53l15-25 23 47 23-31 19 10h44" />
      <path d="M42 153h40l13-15 18 27 21-15 23 6h62" strokeOpacity=".7"/>
      <path d="M42 210h177" strokeDasharray="4 6"/>
      <circle cx="110" cy="68" r="4" fill="#aed4c4"/>
      <path d="M420 73h275M420 123h275M420 173h275M420 223h275" stroke="#52746b"/>
      <path d="M450 123l38-28 42 22 43-38 42 35 40-24" />
      <path d="M450 173l38 17 42-25 43 16 42-26 40 16" strokeOpacity=".65"/>
      <path d="M530 57v175" stroke="#6f9686" strokeDasharray="4 6"/>
      <circle cx="530" cy="117" r="7" fill="#0c1c21"/><circle cx="530" cy="165" r="7" fill="#0c1c21"/>
      <rect x="803" y="66" width="248" height="156" rx="2" stroke="#72988a"/>
      <path d="M826 100h95M826 120h185M826 140h149M826 160h185M826 180h120" stroke="#72988a"/>
      <path d="M993 92l12 12 22-25" stroke="#bce1c5" strokeWidth="2.5"/>
      <path d="M354 137h22M734 137h22" stroke="#a5d3bd" markerEnd="url(#sc-flow-arrow)"/>
    </g>
    <g fill="#dcebe2" fontSize="12"><text x="42" y="244">AIS · radio · public reports</text><text x="420" y="244">Timestamp · location · source</text><text x="826" y="203">Case chronology</text></g>
    <g fill="#95b9ac" fontSize="10"><text x="826" y="86">EVIDENCE FILE</text><text x="42" y="54">SOURCE OBSERVATIONS</text></g>
  </svg>;
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
