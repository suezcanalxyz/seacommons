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
        <div><dt>Intended users</dt><dd>Humanitarian organisations, investigative researchers and public-interest institutions. Adoption and research benefit will be evaluated through a scoped pilot.</dd></div>
        <div><dt>Current stage</dt><dd>Open-source software with public Live, archive and documentation surfaces. Code availability does not establish current deployment health or validated operational effectiveness.</dd></div>
        <div><dt>Funding priority</dt><dd>A proposed six-month pilot to establish reliable source coverage, validate case reconstruction and document the cost of continued operation.</dd></div>
      </dl>
      <div className="project-evidence">
        <p>Public case totals describe records in the system. They do not measure people assisted, verified incidents or partner adoption.</p>
        <div><a href="/status">Deployment status ↗</a><a href="https://github.com/suezcanalxyz/seacommons">Code and checks ↗</a><a href="/docs">Methods and limits ↗</a></div>
      </div>
    </section>
  );
}
