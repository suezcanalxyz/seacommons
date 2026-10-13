import React, { useState } from 'react';

// The catalogue defines capabilities once. Platform describes the hardware;
// Intelligence shows its observations; Contributions explains how to connect it.
export const deviceCatalogue = [
  { id: 'drifter', name: 'Drifter', maturity: 'Design concept', purpose: 'A floating observation node that follows water movement and records measurements over time.', image: 'https://images.unsplash.com/photo-1518837695005-2083093ee35b?auto=format&fit=crop&w=900&q=80', specs: [['Location','GNSS/GPS position and timestamp'],['Sensors','Temperature, motion and optional hydrophone'],['Connectivity','Cellular or satellite; LoRa only with reachable gateway'],['Energy','Battery with optional solar charging'],['Reliability','Local queue, waterproof housing, retrieval plan']], flow: 'Drifter → secure telemetry → ingestion → validated positions → map, analysis and historical comparisons.' },
  { id: 'coastal-receiver', name: 'Coastal receiver', maturity: 'Proposed network node', purpose: 'A fixed station that listens for public AIS transmissions and shares reception metadata and vessel positions.', image: 'https://images.unsplash.com/photo-1516939884455-1445c8652f83?auto=format&fit=crop&w=900&q=80', specs: [['Receiver','Dedicated AIS receiver or supported SDR'],['Antenna','Marine VHF antenna with appropriate installation'],['Network','Secure internet connection'],['Data','AIS messages with receiver and capture time'],['Operations','Signal quality, uptime and local buffering']], flow: 'AIS transmissions → coastal receiver → validated message feed → SeaCommons positions and coverage analysis.' },
  { id: 'environment-node', name: 'Environmental node', maturity: 'Proposed network node', purpose: 'A small field station collecting local conditions that help researchers interpret environmental change.', image: 'https://images.unsplash.com/photo-1500534623283-312aade485b7?auto=format&fit=crop&w=900&q=80', specs: [['Measurements','Temperature, pressure, humidity, optional water sensors'],['Location','Fixed surveyed position'],['Power','Mains, battery or solar'],['Network','Internet, cellular or gateway'],['Quality','Calibration and sample metadata']], flow: 'Environmental sensors → gateway → time-stamped observations → contextual layers and analysis.' },
  { id: 'edge-gateway', name: 'Edge gateway', maturity: 'Proposed network node', purpose: 'A small computer that receives nearby observations, temporarily stores them and safely forwards them to SeaCommons.', image: 'https://images.unsplash.com/photo-1558494949-ef010cbdcc31?auto=format&fit=crop&w=900&q=80', specs: [['Compute','Low-power Linux mini computer'],['Ingestion','Supported local protocols and input validation'],['Storage','Encrypted buffer for connection outages'],['Security','Device identity and restricted outbound access'],['Maintenance','Remote health checks and signed updates']], flow: 'Local devices → edge gateway → secure connection → canonical SeaCommons API.' },
];

const stages = [
  ['Collect', 'Connect satellite, AIS, radio, environmental and public-report sources. Every observation is stored with its origin and time.'],
  ['Filter', 'Standardise formats, check completeness, identify duplicates and keep uncertainty visible.'],
  ['Correlate', 'Compare location, time and independent evidence to discover possible relationships, not automatic proof.'],
  ['Analyse', 'Build timelines, spatial comparisons and simulations such as drift models, with recorded assumptions.'],
  ['Review', 'Distinguish observations, hypotheses and reviewed findings before presenting a claim.'],
  ['Publish', 'Share appropriate outcomes through Live, Play, research reports and APIs, with privacy controls.'],
];

export function MethodExplorer() {
  const [selected, setSelected] = useState(0);
  return <section className="future-section future-network-section">
    <header><div><span className="future-eyebrow">What is SeaCommons? / The method</span><h2>From scattered observations to evidence people can inspect.</h2><p>SeaCommons is software for collecting and comparing information from many different places. Instead of treating every signal as a fact, it records where the information came from, filters noise and helps people review what the information can actually support.</p></div></header>
    <div className="future-method-controls" role="tablist" aria-label="Data processing method">
      {stages.map(([title],index) => <button type="button" role="tab" aria-selected={selected===index} className={selected===index?'is-active':''} key={title} onClick={()=>setSelected(index)}><small>0{index+1}</small>{title}</button>)}
    </div>
    <div className="future-network-detail" role="tabpanel"><strong>{stages[selected][0]}</strong><p>{stages[selected][1]}</p></div>
    <div className="future-domain-grid">
      <article><small>01 / MARITIME</small><h3>Understand activity at sea.</h3><p>Connect vessel positions, radio observations, weather and satellite context. Build time-based views, compare sources and explore possible movement through modelling.</p></article>
      <article><small>02 / HUMANITARIAN</small><h3>Investigate with care.</h3><p>Study reported maritime events and humanitarian evidence without confusing a technical signal with a verified rescue or incident. Support reviewable timelines and protect sensitive information.</p></article>
      <article><small>03 / ENVIRONMENTAL</small><h3>Monitor changing conditions.</h3><p>Combine environmental observations and satellite datasets to study coastal and ecological change. Expanded use cases require new validated sources and models.</p></article>
      <article><small>04 / TERRESTRIAL</small><h3>Reuse the method on land.</h3><p>The same collection, filtering and analysis stages can support land monitoring and civic research. These are possible adaptations, not a claim that each application is already deployed.</p></article>
    </div>
  </section>;
}

export function PlatformNetwork() {
  const [active,setActive] = useState('drifter');
  const [tab,setTab] = useState('purpose');
  const device = deviceCatalogue.find(d=>d.id===active) || deviceCatalogue[0];
  return <><section className="future-page-head"><span className="future-eyebrow">Platform / product ecology</span><h1>Software, devices and a shared method.</h1><p>SeaCommons combines public information, software services and, progressively, devices that can provide observations from the field. This catalogue separates operational software from proposed or experimental hardware.</p></section>
    <section className="future-section"><header><h2>Explore the software</h2></header><div className="future-network-products">
      {[['Live','Public, privacy-filtered maritime information','https://live.seacommons.org'],['Play','Historical cases, timelines and exploration','https://play.seacommons.org'],['API','Contracts, data services and Swagger reference','https://api.seacommons.org/docs'],['Futures','Partner intelligence, project knowledge and collaboration','https://futures.seacommons.org']].map(([label,description,url])=><a key={label} href={url} target="_blank" rel="noopener noreferrer"><strong>{label} ↗</strong><p>{description}</p></a>)}
    </div></section>
    <section className="future-section"><header><div><span className="future-eyebrow">Devices / expandable network</span><h2>Physical observation nodes</h2><p>Illustrative imagery and proposed engineering specifications; do not treat these cards as installed stations or verified prototypes.</p></div></header>
      <div className="future-device-grid">{deviceCatalogue.map(d=><button type="button" className={'future-device-card '+(active===d.id?'is-active':'')} onClick={()=>{setActive(d.id);setTab('purpose')}} key={d.id}><img src={d.image} alt={d.name+' illustrative reference'} loading="lazy"/><span><small>{d.maturity}</small><strong>{d.name}</strong><p>{d.purpose}</p></span></button>)}</div>
      <article className="future-device-detail"><div><span className="future-eyebrow">Device specification / {device.id}</span><h3>{device.name}</h3></div><div className="future-risk-filters" role="tablist" aria-label="Device details">{[['purpose','Purpose'],['specs','Specifications'],['flow','Data flow']].map(([key,label])=><button key={key} type="button" role="tab" aria-selected={tab===key} className={tab===key?'is-active':''} onClick={()=>setTab(key)}>{label}</button>)}</div>
        {tab==='purpose'?<p>{device.purpose} Current maturity: {device.maturity}. Its deployment must be tested before it can be counted as an active data source.</p>:tab==='specs'?<dl className="future-device-specs">{device.specs.map(([key,value])=><div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl>:<p>{device.flow}</p>}
      </article>
    </section>
  </>;
}

export function NetworkContributionsIntro() {
  return <section className="future-section future-network-section"><header><div><span className="future-eyebrow">Contributions / Build the network</span><h2>A network of shared infrastructure, not a fundraising list.</h2><p>SeaCommons can grow through small, independently managed contributions: a receiver on a coastline, a field sensor, an available data feed, a secure compute node or a self-hosted deployment. Each contribution should identify what it connects, who operates it, what data it can share, and its recurring costs.</p></div></header>
    <div className="future-domain-grid">
      <article><small>COMPUTE / IMMEDIATE TEST</small><h3>Oracle Cloud VM</h3><p>A practical first test node for development, uptime checks and isolated workloads. Oracle has an Always Free tier, subject to eligibility and available capacity. It is not the intended permanent central point of failure.</p><a href="https://www.oracle.com/cloud/free/" target="_blank" rel="noopener noreferrer">Create a free account ↗</a><br/><a href="https://docs.oracle.com/en-us/iaas/Content/Compute/tutorials/first-linux-instance/overview.htm" target="_blank" rel="noopener noreferrer">Official instance walkthrough ↗</a><p>Use a dedicated public SSH key to grant access. Never upload a private SSH key into ordinary Futures documents.</p></article>
      <article><small>MARITIME / FIELD NODES</small><h3>Coastal stations & Drifter</h3><p>Partners can host an AIS receiver, test a Drifter or connect a weather station. Technical requirements are described in Platform; here the focus is deployment, connectivity, maintenance and who maintains the node.</p></article>
      <article><small>DATA / INTEROPERABILITY</small><h3>Existing services</h3><p>Connect compatible existing datasets instead of duplicating expensive equipment. Each connection needs a licence, coverage description, refresh schedule and provenance policy.</p></article>
      <article><small>LONG-TERM ARCHITECTURE</small><h3>Distributed & self-hosted</h3><p>Plan for independent installations and partner-operated nodes. Define portable containers, versioned interfaces, federated source identity and optional synchronisation. A decentralised deployment is an architectural direction, not an existing production guarantee.</p></article>
    </div>
  </section>;
}
