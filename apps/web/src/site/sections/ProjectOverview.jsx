import { SectionLabel, Display } from '../bits.jsx';

export default function ProjectOverview() {
  return (
    <section id="overview" className="section project-overview" aria-labelledby="overview-title">
      <SectionLabel index="Project brief" title="Purpose, users and current stage" />
      <div className="project-overview__head">
        <Display id="overview-title">Maritime evidence infrastructure<br />for public-interest research.</Display>
        <p>SeaCommons brings fragmented reports into traceable case records. Researchers can inspect the sources behind an interpretation, compare conflicting evidence and follow later corrections.</p>
      </div>
      <dl className="project-facts">
        <div><dt>Who it serves</dt><dd>Humanitarian organisations, investigative researchers and public-interest institutions working with maritime evidence.</dd></div>
        <div><dt>Public tools</dt><dd>Live shows current public cases. Play preserves case timelines and later updates. Documentation explains sources, methods and the limits of interpretation.</dd></div>
        <div><dt>Partner workspace</dt><dd>Authorised partners share documents, research analysis and delivery plans in a private workspace with workflow steps and milestones.</dd></div>
      </dl>
      <div className="project-evidence">
        <p>Public case totals describe records in the system. They do not measure people assisted, verified incidents or partner adoption.</p>
        <div><a href="/status">Deployment status ↗</a><a href="https://github.com/suezcanalxyz/seacommons">Code and checks ↗</a><a href="/docs">Methods and limits ↗</a></div>
      </div>
    </section>
  );
}
