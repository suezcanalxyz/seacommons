import { createRoot } from 'react-dom/client';
import '../ui/ui.css';
import './funding-deck.css';
import { FUNDING_WORK, PILOT_PHASES, PILOT_METRICS } from './fundingContent.js';

function Slide({ number, title, children, cover = false, note }) {
  return <section id={`slide-${number}`} className={`deck-slide${cover ? ' deck-slide--cover' : ''}`} aria-labelledby={`title-${number}`}>
    <header><span>SeaCommons</span><span>{String(number).padStart(2, '0')} / 10</span></header>
    <div className="deck-slide__body">{cover ? <h1 id={`title-${number}`}>{title}</h1> : <h2 id={`title-${number}`}>{title}</h2>}{children}</div>
    <footer>{note || 'Funding brief / October 2026'}</footer>
  </section>;
}

function FundingDeck() {
  return <>
    <nav className="deck-toolbar" aria-label="Presentation controls"><a href="/site.html">← Project site</a><a href="#slide-10">Pilot discussion</a><button type="button" onClick={() => window.print()}>Print / Save PDF</button></nav>
    <main id="main" className="deck">
      <Slide number={1} title="Maritime evidence infrastructure" cover note="Proposed pilot / Funding scope subject to agreement">
        <p className="deck-lead">Open-source research infrastructure for humanitarian incidents and maritime investigations.</p>
        <p className="deck-cover-meta">SeaCommons / Sponsor and grant discussions / October 2026</p>
      </Slide>
      <Slide number={2} title="The research problem">
        <p className="deck-lead">Maritime observations arrive through separate systems with different timestamps, precision and source authority.</p>
        <div className="deck-columns"><div><h3>Fragmented inputs</h3><p>Public reports, vessel tracks, radio transmissions and satellite observations require reconciliation before they can support an interpretation.</p></div><div><h3>Uncertain conclusions</h3><p>Repeated reports can share one origin. Gaps in vessel data can reflect missing coverage. A credible case record must preserve these distinctions.</p></div></div>
      </Slide>
      <Slide number={3} title="The SeaCommons approach">
        <p className="deck-lead">A case record connects observations while preserving what each source can establish.</p>
        <ol className="deck-process"><li><strong>Receive</strong><span>Keep the original source and timestamps.</span></li><li><strong>Compare</strong><span>Check time, location, identity and source independence.</span></li><li><strong>Review</strong><span>Retain uncertainty and competing explanations.</span></li><li><strong>Publish</strong><span>Apply privacy and public release rules.</span></li></ol>
        <p className="deck-caption">Method reference: <a href="/docs">SeaCommons documentation</a></p>
      </Slide>
      <Slide number={4} title="Intended users and research value">
        <div className="deck-rows"><div><h3>Humanitarian organisations</h3><p>Reconstruct reported distress and response timelines with sensitive information restricted.</p></div><div><h3>Investigative researchers</h3><p>Inspect vessel behaviour against source coverage and alternative explanations.</p></div><div><h3>Public-interest institutions</h3><p>Review traceable records and methods that support correction and scrutiny.</p></div></div>
        <p className="deck-caption">These are intended use cases. The pilot would evaluate adoption and usefulness.</p>
      </Slide>
      <Slide number={5} title="Current stage and evidence">
        <div className="deck-columns"><div><h3>Available to inspect</h3><p>Open-source code, public Live and archive interfaces, documented evidence methods and automated engineering checks.</p><p className="deck-links"><a href="https://github.com/suezcanalxyz/seacommons">Repository</a><a href="/docs">Documentation</a><a href="/status">Deployment status</a></p></div><div><h3>Requires validation</h3><p>Current deployment health, geographic source coverage, case quality, research usefulness and the cost of sustained operation.</p></div></div>
        <p className="deck-caption">Public record totals describe system activity. They do not establish verified outcomes or people assisted.</p>
      </Slide>
      <Slide number={6} title="Proposed six-month pilot">
        <div className="deck-phases">{PILOT_PHASES.map((phase) => <article key={phase.period}><span>{phase.period}</span><h3>{phase.title}</h3><p>{phase.output}</p></article>)}</div>
        <p className="deck-caption">Schedule starts after scope, resources and participant responsibilities are agreed. Each phase has a review before continuation.</p>
      </Slide>
      <Slide number={7} title="What funding would support">
        <div className="deck-rows">{FUNDING_WORK.map((item) => <div key={item.title}><h3>{item.title}</h3><p>{item.body}</p></div>)}</div>
        <p className="deck-caption">A costed proposal will specify staff effort, source licences, hosting, review and maintenance. The amount remains subject to scope and supplier costs.</p>
      </Slide>
      <Slide number={8} title="Evaluation and reporting">
        <dl className="deck-metrics">{PILOT_METRICS.map((metric) => <div key={metric.title}><dt>{metric.title}</dt><dd>{metric.definition}</dd></div>)}</dl>
        <p className="deck-caption">Proposed measures. Baselines, sample selection and thresholds require agreement before evaluation.</p>
      </Slide>
      <Slide number={9} title="Delivery responsibility and safeguards">
        <div className="deck-columns"><div><h3>Project development</h3><p>SeaCommons is developed by suezcanal.xyz. Matteo Messina leads the proposed technical delivery. The pilot agreement must assign case review, participant coordination and ongoing maintenance.</p></div><div><h3>Research safeguards</h3><p>Sensitive information stays outside public records. Model outputs retain assumptions and uncertainty. Open-source AGPL-3.0 licensing supports inspection of the software.</p></div></div>
        <p className="deck-caption">Research infrastructure. Emergency response authority and operational adoption require separate arrangements.</p>
      </Slide>
      <Slide number={10} title="A defined pilot funding agreement">
        <p className="deck-lead">The next decision is the research scope and the resources needed to deliver it.</p>
        <ul className="deck-next"><li>Agree the geography, case sample and participant roles.</li><li>Confirm data access, review conditions and evaluation criteria.</li><li>Cost delivery and maintenance before setting the funding amount.</li></ul>
        <a className="deck-contact" href="mailto:research@seacommons.org?subject=SeaCommons%20pilot%20discussion">research@seacommons.org ↗</a>
        <p className="deck-caption">Sponsorship and grant support can fund defined deliverables. Commercial or equity terms need a separate proposal.</p>
      </Slide>
    </main>
  </>;
}

createRoot(document.getElementById('funding-root')).render(<FundingDeck />);
