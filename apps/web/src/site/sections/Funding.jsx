import { SectionLabel, Display } from '../bits.jsx';
import { FUNDING_WORK, PILOT_PHASES, PILOT_METRICS } from '../fundingContent.js';

export default function Funding() {
  return (
    <section id="funding" className="section funding" aria-labelledby="funding-title">
      <SectionLabel index="Funding and delivery" title="Proposed pilot / subject to agreement" />
      <div className="project-overview__head">
        <Display id="funding-title">A scoped pilot.<br />Inspectable results.</Display>
        <p>Support would fund infrastructure reliability and evidence validation for a defined research use case. The proposal sets out deliverables and evaluation criteria before expansion.</p>
      </div>
      <div className="funding-work">
        {FUNDING_WORK.map((item) => <article key={item.title}><h3>{item.title}</h3><p>{item.body}</p><small>Evidence of delivery</small><p>{item.evidence}</p></article>)}
      </div>
      <h3 className="funding-subtitle">Proposed delivery schedule</h3>
      <ol className="funding-phases">
        {PILOT_PHASES.map((phase) => <li key={phase.period}><span>{phase.period}</span><h4>{phase.title}</h4><p>{phase.work}</p><p className="funding-output"><strong>Deliverable</strong> {phase.output}</p></li>)}
      </ol>
      <h3 className="funding-subtitle">How the pilot would be evaluated</h3>
      <dl className="funding-metrics">
        {PILOT_METRICS.map((metric) => <div key={metric.title}><dt>{metric.title}</dt><dd>{metric.definition}</dd></div>)}
      </dl>
      <div className="funding-contact">
        <div><h3>Scope and budget</h3><p>The funding amount, participants and performance targets require agreement. A costed proposal should specify engineering effort, source licences, infrastructure, case review and maintenance responsibilities.</p></div>
        <div className="hero__actions"><a className="btn btn--primary" href="/funding.html">Read the funding deck <span aria-hidden="true">→</span></a><a className="btn btn--ghost" href="mailto:research@seacommons.org?subject=SeaCommons%20pilot%20discussion">Discuss a pilot <span aria-hidden="true">↗</span></a></div>
      </div>
    </section>
  );
}
