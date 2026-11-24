import {L} from './locale.jsx';
import React, { useState } from 'react';
import GlossaryText from './GlossaryText.jsx';
import KeyFigures from './KeyFigures.jsx';

// The catalogue defines capabilities once. Platform describes the hardware;
// Intelligence shows its observations; Contributions explains how to connect it.
export const deviceCatalogue = [
  { id: 'drifter', name: 'Drifter', maturity: 'Design concept', purpose: 'A floating observation node that follows water movement and records measurements over time.', image: '', specs: [['Location','GNSS/GPS position and timestamp'],['Sensors','Temperature, motion and optional hydrophone'],['Connectivity','Cellular or satellite; LoRa only with reachable gateway'],['Energy','Battery with optional solar charging'],['Reliability','Local queue, waterproof housing, retrieval plan']], flow: 'Drifter → secure telemetry → ingestion → validated positions → map, analysis and historical comparisons.' },
  { id: 'coastal-receiver', name: 'Coastal receiver', maturity: 'Proposed network node', purpose: 'A fixed station that listens for public AIS transmissions and shares reception metadata and vessel positions.', image: 'https://thumb.wikimedia.org/wikipedia/commons/thumb/2/28/DVB-T_USB_dongle_with_RTL2832U_and_R820T.jpg/960px-DVB-T_USB_dongle_with_RTL2832U_and_R820T.jpg', specs: [['Receiver','Dedicated AIS receiver or supported SDR'],['Antenna','Marine VHF antenna with appropriate installation'],['Network','Secure internet connection'],['Data','AIS messages with receiver and capture time'],['Operations','Signal quality, uptime and local buffering']], flow: 'AIS transmissions → coastal receiver → validated message feed → SeaCommons positions and coverage analysis.' },
  { id: 'environment-node', name: 'Environmental node', maturity: 'Proposed network node', purpose: 'A small field station collecting local conditions that help researchers interpret environmental change.', image: 'https://thumb.wikimedia.org/wikipedia/commons/thumb/a/ab/Davis_Instruments_weather_station_-_detail.jpg/960px-Davis_Instruments_weather_station_-_detail.jpg', specs: [['Measurements','Temperature, pressure, humidity, optional water sensors'],['Location','Fixed surveyed position'],['Power','Mains, battery or solar'],['Network','Internet, cellular or gateway'],['Quality','Calibration and sample metadata']], flow: 'Environmental sensors → gateway → time-stamped observations → contextual layers and analysis.' },
  { id: 'edge-gateway', name: 'Edge gateway', maturity: 'Proposed network node', purpose: 'A small computer that receives nearby observations, temporarily stores them and safely forwards them to SeaCommons.', image: 'https://thumb.wikimedia.org/wikipedia/commons/thumb/f/f1/Raspberry_Pi_4_Model_B_-_Side.jpg/960px-Raspberry_Pi_4_Model_B_-_Side.jpg', specs: [['Compute','Low-power Linux mini computer'],['Ingestion','Supported local protocols and input validation'],['Storage','Encrypted buffer for connection outages'],['Security','Device identity and restricted outbound access'],['Maintenance','Remote health checks and signed updates']], flow: 'Local devices → edge gateway → secure connection → canonical SeaCommons API.' },
];

const stages = [
  {
    "title": "Collect",
    "summary": "SeaCommons starts with observations that differ in timing, coverage and reliability. Maritime inputs include AIS vessel messages, humanitarian and public reports, and weather or ocean datasets used to interpret activity at sea.",
    "process": "Each accepted record retains its source, available timestamps, vessel or place identifiers and provenance. Some feeds stream continuously; others arrive through periodic retrieval or partner submissions. Satellite products and remote radio observations depend on authorised, configured access rather than blanket live coverage.",
    "boundary": "An incoming report is not a verified event. Missing AIS positions may indicate reception or provider gaps; proposed field sensors are not yet an operational network."
  },
  {
    "title": "Filter",
    "summary": "Different providers can report the same movement in different formats or at different times. SeaCommons prepares those records for comparison without erasing their origins.",
    "process": "The pipeline normalises fields and timestamps, checks usable positions and uses source identifiers to identify duplicates while preserving upstream lineage. It also considers source health, stale updates and incomplete coverage before an observation contributes to later analysis.",
    "boundary": "Removing duplicates is not the same as disproving a report. A silent or unavailable feed must never be interpreted automatically as a vessel turning off its transponder."
  },
  {
    "title": "Correlate",
    "summary": "A vessel position, a humanitarian report and a weather observation can describe related circumstances without independently proving the same event.",
    "process": "SeaCommons compares time windows, locations, vessel identities and source lineage to propose associations between observations and cases. Corroboration depends on genuinely independent origins, not on how many websites repeat a single upstream message.",
    "boundary": "A proximity match or repeated claim is a lead for investigation, not proof of contact, rescue, intent or wrongdoing."
  },
  {
    "title": "Analyse",
    "summary": "Once observations are organised, SeaCommons can examine sequences of movement, gaps, surrounding conditions and competing explanations.",
    "process": "Analysis builds timelines and spatial comparisons, and can use wind and current fields for drift or reconstruction scenarios. Derived coordinates, model settings and degraded fallback conditions need to remain distinguishable from measured positions.",
    "boundary": "A simulation explores possible trajectories under stated assumptions; it cannot establish the actual route or fate of a vessel or person by itself."
  },
  {
    "title": "Review",
    "summary": "The method separates what a source reported, what software inferred and what an investigator can substantiate.",
    "process": "Cases can be inspected against underlying records, time and location uncertainty, source independence and conflicting evidence. Humanitarian claims require particular care because premature certainty or precise public coordinates can create harm.",
    "boundary": "An anomaly, automated classification or proposed association is not a verified incident or a finding of unlawful behaviour. Review and lifecycle status remain distinct."
  },
  {
    "title": "Publish",
    "summary": "Publication is a controlled decision, not an automatic final step for every observation processed by SeaCommons.",
    "process": "Eligible, privacy-filtered cases can appear in public Live; retained public records can be explored in Play. Documented APIs expose appropriately scoped data while private and sensitive material stays restricted.",
    "boundary": "Public maps may reduce location precision or withhold details. An absence from Live or Play does not mean that no observation or incident exists."
  }
];

export function MethodExplorer() {
  const [selected, setSelected] = useState(0);
  const stage = stages[selected];
  const focusStage = (event, index) => {
    const tabs = event.currentTarget.parentElement.querySelectorAll('[role="tab"]');
    tabs[index]?.focus();
    setSelected(index);
  };
  const handleStageKeyDown = (event, index) => {
    let next;
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') next = (index + 1) % stages.length;
    else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') next = (index - 1 + stages.length) % stages.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = stages.length - 1;
    else return;
    event.preventDefault();
    focusStage(event, next);
  };
  return <section className="future-section future-network-section">
    <header><div><span className="future-eyebrow"><L>What is SeaCommons? / The method</L></span><h2><L>Evidence processing method</L></h2><p><L>SeaCommons builds traceable accounts from uneven maritime and humanitarian information. These six stages explain how an incoming observation can be compared, interpreted and reviewed without turning an uncertain signal into an unsupported claim.</L></p></div></header>
    <div className="future-method-controls" role="tablist" aria-label="Six stages of the SeaCommons method">
      {stages.map((item,index) => <button type="button" role="tab" id={'method-tab-' + index} aria-controls="method-panel" aria-selected={selected===index} tabIndex={selected===index?0:-1} className={selected===index?'is-active':''} key={item.title} onClick={()=>setSelected(index)} onKeyDown={(event)=>handleStageKeyDown(event,index)}><small><L>{String(index+1).padStart(2,'0')}</L></small><span><L>{item.title}</L></span></button>)}
    </div>
    <div className="future-network-detail" id="method-panel" role="tabpanel" aria-labelledby={'method-tab-' + selected} tabIndex={0}>
      <div className="future-method-detail-intro"><span className="future-eyebrow"><L>Stage </L><L>{String(selected+1).padStart(2,'0')}</L> / 06</span><h3><L>{stage.title}</L></h3><p><GlossaryText>{stage.summary}</GlossaryText></p></div>
      <div className="future-method-detail-grid"><div><small><L>HOW IT WORKS</L></small><p><GlossaryText>{stage.process}</GlossaryText></p></div><div><small><L>WHAT IT DOES NOT PROVE</L></small><p><GlossaryText>{stage.boundary}</GlossaryText></p></div></div>
    </div>
    <div className="future-domain-grid">
      <article><small><L>01 / MARITIME</L></small><h3><L>Maritime research</L></h3><p><L>Connect vessel positions, radio observations, weather and satellite context. Build time-based views, compare sources and explore possible movement through modelling.</L></p></article>
      <article><small><L>02 / HUMANITARIAN</L></small><h3><L>Humanitarian evidence</L></h3><p><L>Study reported maritime events and humanitarian evidence without confusing a technical signal with a verified rescue or incident. Support reviewable timelines and protect sensitive information.</L></p></article>
      <article><small><L>03 / ENVIRONMENTAL</L></small><h3><L>Environmental research</L></h3><p><L>Combine environmental observations and satellite datasets to study coastal and ecological change. Expanded use cases require new validated sources and models.</L></p></article>
      <article><small><L>04 / TERRESTRIAL</L></small><h3><L>Terrestrial applications</L></h3><p><L>The same collection, filtering and analysis stages can support land monitoring and civic research. These are possible adaptations, not a claim that each application is already deployed.</L></p></article>
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
  <span className="future-blueprint-label"><L>MARINE CONCEPT / NOT FABRICATED</L></span>
  <span className="future-blueprint-antenna">GNSS · RADIO</span>
  <span className="future-blueprint-float"><L>LOGGER</L><br/><L>POWER</L><br/><L>SENSORS</L></span>
  <span className="future-blueprint-tether"></span>
  <span className="future-blueprint-drogue"><L>DROGUE</L></span>
 </div>;
}

export function PlatformNetwork() {
 const [section,setSection] = useState('software');
 const [active,setActive] = useState('drifter');
 const [tab,setTab] = useState('purpose');
 const device = deviceCatalogue.find(d=>d.id===active) || deviceCatalogue[0];
 const context=deviceGuide[device.id];
 const review=engineeringReview[device.id];
 return <div className="platform-workspace">
 <section className="future-page-head future-platform-intro"><span className="future-eyebrow"><L>SeaCommons / Platform</L></span><h1><L>Platform architecture</L></h1><p><GlossaryText>Four software interfaces share the evidence model. Proposed field instruments extend the research infrastructure after calibration, permissions and independent validation.</GlossaryText></p></section>
 <KeyFigures items={[{value:productGuide.length,title:'Software interfaces',detail:'LIVE, PLAY, API and the authenticated FUTURES workspace.'},{value:deviceCatalogue.length,title:'Instrument concepts',detail:'Proposed designs, not deployed devices.'},{value:stages.length,title:'Evidence stages',detail:'From collection to controlled publication.'}]}/>
 <div className="futures-switcher platform-switcher" role="group" aria-label="Platform section">{[['software','Software'],['devices','Research instruments'],['method','Evidence method']].map(([id,label])=><button key={id} type="button" aria-pressed={section===id} onClick={()=>setSection(id)}><L>{label}</L></button>)}</div>
 {section==='software'&&<section className="future-section platform-section">
 <header><div><h2><L>Software interfaces</L></h2><p><L>Choose the interface according to the research task. Detailed evidence and protected data have separate access boundaries.</L></p></div></header>
 <div className="platform-product-list">{productGuide.map((p,i)=><article key={p.id} className="platform-product-row">
 <span className="platform-index"><L>{String(i+1).padStart(2,'0')}</L></span><div className="platform-product-copy"><span className="platform-pill"><L>{p.status}</L></span><h3><L>{p.name}</L></h3><p className="platform-role"><L>{p.role}</L></p><p><GlossaryText>{p.description}</GlossaryText></p><a href={p.url} target="_blank" rel="noopener noreferrer"><L>Open </L><L>{p.name}</L> ↗</a>
 <details><summary><L>Workflow, evidence and limitations</L></summary><h4><L>Workflow</L></h4><p><GlossaryText>{p.workflow}</GlossaryText></p><h4><L>Available information</L></h4><ul>{p.read.map(item=><li key={item}><GlossaryText>{item}</GlossaryText></li>)}</ul><h4><L>Interpretation limits</L></h4><p><GlossaryText>{p.limits}</GlossaryText></p></details></div>
 {(p.id==='live'||p.id==='play')&&<img className="platform-product-preview" src={'/visualizations/'+p.id+'-visual.png'} alt={'SeaCommons '+p.name+' interface visualization'} loading="lazy"/>}</article>)}</div></section>}
 {section==='devices'&&<section className="future-section platform-section"><header><div><h2><L>Proposed research instruments</L></h2><p><L>Select a device to inspect the design, component references and requirements for a controlled research trial. The four designs are not evidence of installed stations.</L></p></div></header>
 <div className="futures-switcher platform-switcher" role="group" aria-label="Research instrument">{deviceCatalogue.map(d=><button key={d.id} type="button" aria-pressed={active===d.id} onClick={()=>{setActive(d.id);setTab('purpose')}}><L>{d.name}</L></button>)}</div>
 <article className="platform-device-study"><div className="platform-device-heading"><div><span className="platform-pill platform-pill--plan"><L>{device.maturity}</L></span><h3><L>{device.name}</L></h3><p><GlossaryText>{device.purpose}</GlossaryText></p><p className="platform-role"><L>{context.question}</L></p></div><div className="platform-device-image">{device.id==='drifter'?<DrifterBlueprint/>:<img src={device.image} alt={review.reference+'; hardware reference, not SeaCommons deployment'} loading="lazy"/>}</div></div>
 <div className="futures-switcher platform-switcher" role="group" aria-label="Device details">{[['purpose','Research purpose'],['specs','Specifications'],['flow','Data flow'],['validation','Validation']].map(([key,label])=><button key={key} type="button" aria-pressed={tab===key} onClick={()=>setTab(key)}><L>{label}</L></button>)}</div>
 {tab==='purpose'?<div className="platform-facts"><h4><L>Data handling</L></h4><p><GlossaryText>{context.handling}</GlossaryText></p><h4><L>Readiness</L></h4><p><GlossaryText>{context.deployment}</GlossaryText></p><h4><L>Interpretation limit</L></h4><p><GlossaryText>{context.boundary}</GlossaryText></p></div>:tab==='specs'?<dl className="future-device-specs">{device.specs.map(([key,value])=><div key={key}><dt><L>{key}</L></dt><dd><GlossaryText>{value}</GlossaryText></dd></div>)}</dl>:tab==='flow'?<div className="platform-facts"><h4><L>Observation route</L></h4><p><GlossaryText>{device.flow}</GlossaryText></p><ol className="platform-sequence">{review.architecture.map(step=><li key={step}><GlossaryText>{step}</GlossaryText></li>)}</ol><p><GlossaryText>{context.boundary}</GlossaryText></p></div>:<div className="platform-facts"><h4><L>Acceptance sequence</L></h4><p><GlossaryText>{review.readiness}</GlossaryText></p><h4><L>Evidence required before field deployment</L></h4><p><GlossaryText>{review.test}</GlossaryText></p></div>}
 <details className="platform-reference"><summary><L>Component references and attribution</L></summary><p><GlossaryText>{review.reference}</GlossaryText></p><p><GlossaryText>{review.distinction}</GlossaryText></p><a href={review.url} target="_blank" rel="noopener noreferrer"><L>Manufacturer reference ↗</L></a>{review.photoSource&&<p><a href={review.photoSource} target="_blank" rel="noopener noreferrer"><L>Photograph source and licence ↗</L></a></p>}</details>
 </article></section>}
 {section==='method'&&<MethodExplorer/>}
 </div>;
}

export function NetworkContributionsIntro() {
  return <section className="future-section future-network-section"><header><div><span className="future-eyebrow"><L>Contributions / Build the network</L></span><h2><L>A network of shared infrastructure, not a fundraising list.</L></h2><p><L>Platform is the engineering specification of what we would build; Contributions concerns the permission, hosting, labour and resources needed to test it. SeaCommons can grow through small, independently managed contributions: a receiver on a coastline, a field sensor, an available data feed, a secure compute node or a self-hosted deployment. Each contribution should identify what it connects, who operates it, what data it can share, and its recurring costs.</L></p></div></header>
    <div className="future-domain-grid">
      <article><small><L>COMPUTE / IMMEDIATE TEST</L></small><h3>Oracle Cloud VM</h3><p><L>A practical first test node for development, uptime checks and isolated workloads. The Always Free AMD option can cost €0/month within quota (up to two E2.1.Micro VMs, each 1/8 OCPU and 1 GB RAM). A card is normally required for identity verification; do not enable pay-as-you-go services unintentionally. Home-region capacity and availability are not guaranteed. It is suitable for lightweight tests, not our sole production host.</L></p><a href="https://www.oracle.com/cloud/free/" target="_blank" rel="noopener noreferrer"><L>Create a free account ↗</L></a><br/><a href="https://docs.oracle.com/en-us/iaas/Content/Compute/tutorials/first-linux-instance/overview.htm" target="_blank" rel="noopener noreferrer"><L>Official instance walkthrough ↗</L></a><p><L>Select the home region carefully during registration: Frankfurt may be preferable for an EU pilot if capacity and latency are confirmed; never promise that it has more available stock than Milan. Create one or two eligible AMD E2.1.Micro nodes only when offered. Use a dedicated public SSH key to grant access. Never upload a private SSH key into ordinary Futures documents.</L></p></article>
      <article><small><L>MARITIME / FIELD NODES</L></small><h3><L>Coastal stations & Drifter</L></h3><p><GlossaryText>Partners can host an AIS receiver, test a Drifter or connect a weather station. Technical requirements are described in Platform; here the focus is deployment, connectivity, maintenance and who maintains the node.</GlossaryText></p></article>
      <article><small><L>DATA / INTEROPERABILITY</L></small><h3><L>Existing services</L></h3><p><L>Connect compatible existing datasets instead of duplicating expensive equipment. Each connection needs a licence, coverage description, refresh schedule and provenance policy.</L></p></article>
      <article><small><L>LONG-TERM ARCHITECTURE</L></small><h3><L>Distributed & self-hosted</L></h3><p><L>Plan for independent installations and partner-operated nodes. Define portable containers, versioned interfaces, federated source identity and optional synchronisation. A decentralised deployment is an architectural direction, not an existing production guarantee.</L></p></article>
    </div>
  </section>;
}
