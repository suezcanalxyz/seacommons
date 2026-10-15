import React, { useState } from 'react';
import GlossaryText from './GlossaryText.jsx';

// The catalogue defines capabilities once. Platform describes the hardware;
// Intelligence shows its observations; Contributions explains how to connect it.
export const deviceCatalogue = [
  { id: 'drifter', name: 'Drifter', maturity: 'Design concept', purpose: 'A floating observation node that follows water movement and records measurements over time.', image: '', specs: [['Location','GNSS/GPS position and timestamp'],['Sensors','Temperature, motion and optional hydrophone'],['Connectivity','Cellular or satellite; LoRa only with reachable gateway'],['Energy','Battery with optional solar charging'],['Reliability','Local queue, waterproof housing, retrieval plan']], flow: 'Drifter → secure telemetry → ingestion → validated positions → map, analysis and historical comparisons.' },
  { id: 'coastal-receiver', name: 'Coastal receiver', maturity: 'Proposed network node', purpose: 'A fixed station that listens for public AIS transmissions and shares reception metadata and vessel positions.', image: 'https://thumb.wikimedia.org/wikipedia/commons/thumb/2/28/DVB-T_USB_dongle_with_RTL2832U_and_R820T.jpg/960px-DVB-T_USB_dongle_with_RTL2832U_and_R820T.jpg', specs: [['Receiver','Dedicated AIS receiver or supported SDR'],['Antenna','Marine VHF antenna with appropriate installation'],['Network','Secure internet connection'],['Data','AIS messages with receiver and capture time'],['Operations','Signal quality, uptime and local buffering']], flow: 'AIS transmissions → coastal receiver → validated message feed → SeaCommons positions and coverage analysis.' },
  { id: 'environment-node', name: 'Environmental node', maturity: 'Proposed network node', purpose: 'A small field station collecting local conditions that help researchers interpret environmental change.', image: 'https://thumb.wikimedia.org/wikipedia/commons/thumb/a/ab/Davis_Instruments_weather_station_-_detail.jpg/960px-Davis_Instruments_weather_station_-_detail.jpg', specs: [['Measurements','Temperature, pressure, humidity, optional water sensors'],['Location','Fixed surveyed position'],['Power','Mains, battery or solar'],['Network','Internet, cellular or gateway'],['Quality','Calibration and sample metadata']], flow: 'Environmental sensors → gateway → time-stamped observations → contextual layers and analysis.' },
  { id: 'edge-gateway', name: 'Edge gateway', maturity: 'Proposed network node', purpose: 'A small computer that receives nearby observations, temporarily stores them and safely forwards them to SeaCommons.', image: 'https://thumb.wikimedia.org/wikipedia/commons/thumb/f/f1/Raspberry_Pi_4_Model_B_-_Side.jpg/960px-Raspberry_Pi_4_Model_B_-_Side.jpg', specs: [['Compute','Low-power Linux mini computer'],['Ingestion','Supported local protocols and input validation'],['Storage','Encrypted buffer for connection outages'],['Security','Device identity and restricted outbound access'],['Maintenance','Remote health checks and signed updates']], flow: 'Local devices → edge gateway → secure connection → canonical SeaCommons API.' },
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

const productGuide = [
 {id:'live',name:'Live',status:'Operational',url:'https://live.seacommons.org',role:'Current public picture',description:'A privacy-filtered view of maritime cases eligible for public release. Live is not an unfiltered vessel tracker and does not publish every signal collected by SeaCommons.',workflow:'The system evaluates eligible signals, applies category and publication policies, and displays the resulting public information with context and uncertainty.',read:['Publicly eligible maritime and humanitarian cases','Selected evidence, classification and timing','Publication scope and limitations'],limits:'Raw AIS anomalies, routine passenger traffic and unverified hypotheses are not automatically published.'},
 {id:'play',name:'Play',status:'Operational',url:'https://play.seacommons.org',role:'Historical exploration',description:'An archive-oriented interface for reviewing published cases over time, examining geographic context and reconstructing timelines. It answers what is recorded historically, not what is happening at this instant.',workflow:'Filter the archive, explore the map and chronology, open a dossier and compare source-backed information where available.',read:['Historical case records and time context','Mapped and chronological exploration','Case dossiers and available evidence'],limits:'Archive coverage depends on retained and publishable records. Absence from Play is not proof an event did not occur.'},
 {id:'api',name:'API',status:'Operational',url:'https://api.seacommons.org/docs',role:'Evidence infrastructure',description:'The machine-readable layer joining ingestion, processing, case records and carefully scoped access. APIs carry typed data contracts; they are not themselves findings.',workflow:'Authorized services request versioned endpoints, interpret fields with their temporal meaning and preserve provenance in downstream analysis.',read:['Operational and documented API contracts','Structured evidence stages and metadata','Service integration and health information'],limits:'Restricted endpoints require authorized access. API availability does not imply that every sensor or analytical module is complete.'},
 {id:'futures',name:'Futures',status:'Partner workspace',url:'https://futures.seacommons.org',role:'Research and collaboration',description:'The authenticated partner workspace for system-level intelligence, technical documentation, development planning and contributions.',workflow:'Compare rolling and retained metrics, interpret evidence quality, review devices and development dependencies, and identify concrete ways to contribute.',read:['Intelligence measurements and methods','Knowledge and development resources','Partner access and contribution requirements'],limits:'Futures metrics describe record populations and processing activity, not confirmed incident counts. Scheduled tasks displayed here are snapshots.'},
];
const deviceGuide = {
 drifter: {question:'How do waterborne observations move through space and time?',handling:'A recovered or connected buoy can produce geotagged environmental observations. Offline periods require onboard buffering and subsequent synchronization.',deployment:'Proposed engineering concept. Waterproofing, power endurance, communications, safety and retrieval require field validation.',boundary:'Drift trajectories are measurements or model context, never automatic proof of the path followed by another object.'},
 'coastal-receiver': {question:'Where can a local station improve AIS reception coverage?',handling:'Receives compatible broadcast AIS messages and attaches station identity, reception time, and signal-health context before normalization.',deployment:'Proposed partner-operated station. Antenna installation, interference, uptime, permissions and ongoing maintenance must be assessed.',boundary:'No AIS reception can indicate coverage loss or silence; it does not on its own establish intentional concealment.'},
 'environment-node': {question:'Which environmental conditions help explain an observation?',handling:'Captures calibrated time-series measurements with location, sensor metadata and maintenance records, then joins analysis as contextual evidence.',deployment:'Proposed station, requiring calibration, weather protection, a power budget and local stewardship.',boundary:'An environmental sensor gives local conditions; broader inference depends on spatial coverage and uncertainty.'},
 'edge-gateway': {question:'How do field devices keep collecting during connection outages?',handling:'Validates nearby sensor inputs, queues encrypted measurements locally and forwards them when connectivity returns, with device identity and status.',deployment:'Proposed supporting infrastructure. Security updates, access limits, retention and recovery tests are prerequisites.',boundary:'A gateway improves transmission resilience; it does not validate the truth of uncalibrated source measurements.'},
};
const engineeringReview = {
 drifter: {
  reference:'RAK WisBlock Kit 2 / solar GNSS tracker, an actual component example rather than a certified marine buoy',
  url:'https://store.rakwireless.com/products/wisblock-kit-2-lora-based-gps-tracker-with-solar-panel',
  architecture:['GNSS + motion sensors','Onboard logger + clock','Cellular or satellite uplink','Encrypted storage + replay','Drift / environmental analysis'],
  readiness:'Concept → bench prototype → controlled short-range trial → recovery test → approved field pilot.',
  test:'Check waterproofing, electrical safety, buoyancy, drogue geometry, 72-hour telemetry budget, source timestamp drift and physical retrieval. Offshore communication requires coverage validation.',
  distinction:'A GPS tracker is a real part reference. The marine float, drogue, enclosure certification and hydrodynamic behavior remain an engineering design, not an off-the-shelf finished product.',
 },
 'coastal-receiver': {
  reference:'RTL-SDR Blog V3 product family; image shows a generic RTL2832U/R820T SDR-class receiver, not the final station',
  photoSource:'https://commons.wikimedia.org/wiki/File:DVB-T_USB_dongle_with_RTL2832U_and_R820T.jpg',
  url:'https://www.rtl-sdr.com/buy-rtl-sdr-dvb-t-dongles/',
  architecture:['162 MHz marine antenna','Two AIS receive channels','GNSS + station ID','Edge buffer + diagnostics','AIS ingestion + coverage map'],
  readiness:'Site survey → RF baseline → dual-channel bench test → legal installation → reception coverage report.',
  test:'Measure decoding across AIS1/2, station uptime, message loss, co-channel interference and reception range against known geography. Document lightning and roof access protection.',
  distinction:'The SDR photograph is a real receiver-class component. An operational node also needs filtering, cable, enclosure, antenna, power and ongoing stewardship.',
 },
 'environment-node': {
  reference:'Davis Instruments weather-station reference photograph; proposed station will be specified by site and required measurements',
  photoSource:'https://commons.wikimedia.org/wiki/File:Davis_Instruments_weather_station_-_detail.jpg',
  url:'https://www.davisinstruments.com/pages/weather-stations',
  architecture:['Weather / water sensors','Calibration + site metadata','Timestamped logger','Secure telemetry','Environmental context layers'],
  readiness:'Research question → sensor selection → calibration baseline → local installation → season-long drift and maintenance review.',
  test:'Assess sensor precision and bias against a calibrated reference, mounting height and exposure, missing-data rate, location, battery autonomy and field maintenance intervals.',
  distinction:'Weather-station photograph shows an existing hardware category, not a deployed SeaCommons asset or a confirmed procurement item.',
 },
 'edge-gateway': {
  reference:'Raspberry Pi board family, as an example of a real low-power computer; the illustrative photograph is Pi 4, with Pi 5 in the current cost study',
  photoSource:'https://commons.wikimedia.org/wiki/File:Raspberry_Pi_4_Model_B_-_Side.jpg',
  url:'https://www.raspberrypi.com/products/raspberry-pi-5/',
  architecture:['Receivers + local protocols','Input validation + device identity','Durable encrypted queue','Authenticated sync','Health and replay monitoring'],
  readiness:'Architecture design → power-loss replay test → credentials review → field installation → recovery exercises.',
  test:'Verify store-and-forward after a network outage, deduplication on replay, bounded disk usage, signed software updates, remote maintenance and tamper-evident logs.',
  distinction:'A single-board computer is only the compute component. Device identity, durable buffering, security and maintenance make it an edge gateway.',
 },
};
function DrifterBlueprint() {
 return <div className="future-drifter-blueprint" aria-label="Engineering concept diagram: floating enclosure, telemetry, GNSS and underwater drogue, not a photo of a finished product">
  <span className="future-blueprint-label">MARINE CONCEPT / NOT FABRICATED</span>
  <span className="future-blueprint-antenna">GNSS · RADIO</span>
  <span className="future-blueprint-float">LOGGER<br/>POWER<br/>SENSORS</span>
  <span className="future-blueprint-tether"></span>
  <span className="future-blueprint-drogue">DROGUE</span>
 </div>;
}

export function PlatformNetwork() {
 const [active,setActive] = useState('drifter');
 const [tab,setTab] = useState('purpose');
 const device = deviceCatalogue.find(d=>d.id===active) || deviceCatalogue[0];
 const context=deviceGuide[device.id];
 return <>
 <section className="future-page-head future-platform-intro"><span className="future-eyebrow">Platform / connected products</span><h1>One evidence system. Four ways to use it.</h1><p>SeaCommons brings together acquisition, analysis and controlled public release. Live and Play are public-facing outputs, API is the service layer, and Futures is the authenticated partner workspace. Hardware is a proposed extension of the observation network, not an already deployed fleet.</p></section>
 <section className="future-section"><header><div><span className="future-eyebrow">Software / operational surfaces</span><h2>Where information goes, and what each product does.</h2><p>Each surface serves a separate task. They share evidence terminology rather than duplicating records or presenting processing activity as confirmed incidents.</p></div></header>
 <div className="future-product-guide">{productGuide.map(p=><article key={p.id} className="future-product-guide-card"><div className="future-product-guide-top"><span className="future-eyebrow">{p.status} / {p.role}</span><a href={p.url} target="_blank" rel="noopener noreferrer">{p.name} ↗</a></div><p className="future-product-guide-lead">{p.description}</p><div className="future-product-guide-detail"><strong>How it works</strong><p>{p.workflow}</p><strong>What you can examine</strong><ul>{p.read.map(item=><li key={item}>{item}</li>)}</ul></div><p className="future-product-guide-limit"><b>Boundary</b> {p.limits}</p></article>)}</div>
 </section>
 <section className="future-section"><header><div><span className="future-eyebrow">Sensors / proposed observation infrastructure</span><h2>Devices extend coverage, not evidential certainty.</h2><p>Physical instruments need installation, maintenance and calibration before their readings can become dependable sources. No pictured device should be interpreted as an existing SeaCommons deployment.</p></div></header>
 <div className="future-device-grid">{deviceCatalogue.map(d=><button type="button" className={'future-device-card '+(active===d.id?'is-active':'')} onClick={()=>{setActive(d.id);setTab('purpose')}} key={d.id} aria-pressed={active===d.id}>{d.id==='drifter'?<DrifterBlueprint/>:<img src={d.image} alt={engineeringReview[d.id].reference+'; actual external hardware-class reference, not SeaCommons deployment'} loading="lazy"/>}<span><small>{d.maturity}</small><strong>{d.name}</strong><p><GlossaryText>{d.purpose}</GlossaryText></p></span></button>)}</div>
 <article className="future-device-detail"><div><span className="future-eyebrow">Device study / {device.maturity}</span><h3>{device.name}</h3><p className="future-device-question">{context.question}</p></div><div className="future-risk-filters" role="tablist" aria-label="Device details">{[['purpose','Function & constraints'],['specs','Technical specifications'],['flow','Data flow']].map(([key,label])=><button key={key} type="button" role="tab" aria-selected={tab===key} className={tab===key?'is-active':''} onClick={()=>setTab(key)}>{label}</button>)}</div>
 {tab==='purpose'?<div className="future-device-guide"><p><b>Purpose</b><GlossaryText>{device.purpose}</GlossaryText></p><p><b>Data handling</b><GlossaryText>{context.handling}</GlossaryText></p><p><b>Deployment readiness</b>{context.deployment}</p><p><b>Interpretation limit</b><GlossaryText>{context.boundary}</GlossaryText></p></div>:tab==='specs'?<dl className="future-device-specs">{device.specs.map(([key,value])=><div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl>:<div className="future-device-guide"><p><b>Route</b>{device.flow}</p><p><b>Evidence safeguard</b>{context.boundary}</p></div>}
 <div className="future-device-reference"><div><h4>Real components and photographic reference</h4><p><GlossaryText>{engineeringReview[device.id].reference}</GlossaryText></p><a href={engineeringReview[device.id].url} target="_blank" rel="noopener noreferrer">View actual manufacturer product and images ↗</a>{engineeringReview[device.id].photoSource&&<p><a href={engineeringReview[device.id].photoSource} target="_blank" rel="noopener noreferrer">Photograph source, author and license ↗</a></p>}<p className="future-factual-note">{engineeringReview[device.id].distinction} Actual reference photographs are not photographs of SeaCommons installations. Check each source-file attribution and license.</p></div>
 <div><h4>Engineering readiness and acceptance</h4><p>{engineeringReview[device.id].readiness}</p><p><strong>Evidence before claiming readiness:</strong> {engineeringReview[device.id].test}</p></div></div>
 <div className="future-architecture-flow">{engineeringReview[device.id].architecture.map((step,i)=><span key={step}><small>{String(i+1).padStart(2,'0')}</small><GlossaryText>{step}</GlossaryText></span>)}</div>
 </article></section></>;
}

export function NetworkContributionsIntro() {
  return <section className="future-section future-network-section"><header><div><span className="future-eyebrow">Contributions / Build the network</span><h2>A network of shared infrastructure, not a fundraising list.</h2><p>Platform is the engineering specification of what we would build; Contributions concerns the permission, hosting, labour and resources needed to test it. SeaCommons can grow through small, independently managed contributions: a receiver on a coastline, a field sensor, an available data feed, a secure compute node or a self-hosted deployment. Each contribution should identify what it connects, who operates it, what data it can share, and its recurring costs.</p></div></header>
    <div className="future-domain-grid">
      <article><small>COMPUTE / IMMEDIATE TEST</small><h3>Oracle Cloud VM</h3><p>A practical first test node for development, uptime checks and isolated workloads. The Always Free AMD option can cost €0/month within quota (up to two E2.1.Micro VMs, each 1/8 OCPU and 1 GB RAM). A card is normally required for identity verification; do not enable pay-as-you-go services unintentionally. Home-region capacity and availability are not guaranteed. It is suitable for lightweight tests, not our sole production host.</p><a href="https://www.oracle.com/cloud/free/" target="_blank" rel="noopener noreferrer">Create a free account ↗</a><br/><a href="https://docs.oracle.com/en-us/iaas/Content/Compute/tutorials/first-linux-instance/overview.htm" target="_blank" rel="noopener noreferrer">Official instance walkthrough ↗</a><p>Select the home region carefully during registration: Frankfurt may be preferable for an EU pilot if capacity and latency are confirmed; never promise that it has more available stock than Milan. Create one or two eligible AMD E2.1.Micro nodes only when offered. Use a dedicated public SSH key to grant access. Never upload a private SSH key into ordinary Futures documents.</p></article>
      <article><small>MARITIME / FIELD NODES</small><h3>Coastal stations & Drifter</h3><p>Partners can host an AIS receiver, test a Drifter or connect a weather station. Technical requirements are described in Platform; here the focus is deployment, connectivity, maintenance and who maintains the node.</p></article>
      <article><small>DATA / INTEROPERABILITY</small><h3>Existing services</h3><p>Connect compatible existing datasets instead of duplicating expensive equipment. Each connection needs a licence, coverage description, refresh schedule and provenance policy.</p></article>
      <article><small>LONG-TERM ARCHITECTURE</small><h3>Distributed & self-hosted</h3><p>Plan for independent installations and partner-operated nodes. Define portable containers, versioned interfaces, federated source identity and optional synchronisation. A decentralised deployment is an architectural direction, not an existing production guarantee.</p></article>
    </div>
  </section>;
}
