import React from 'react';
import { Reveal } from '../../ui/index.js';
import { SectionLabel, Display } from '../bits.jsx';

const STEPS = [
  { n: '01', tag: 'SRC', title: 'Sources', body: 'Public reports, partner inputs, AIS, radio, satellite and environmental observations enter with provenance attached.', foot: 'Raw observations' },
  { n: '02', tag: 'NORM', title: 'Normalization', body: 'Provider-specific payloads become shared event records without erasing precision, authority or source identity.', foot: 'Canonical events' },
  { n: '03', tag: 'CUE', title: 'Derived analysis', body: 'Rules and models produce bounded cues such as integrity, rendezvous, coverage or response context.', foot: 'Cues are not findings' },
  { n: '04', tag: 'CORR', title: 'Correlation', body: 'Identity, time, space and evidence lineage are evaluated before observations are grouped into episodes or hypotheses.', foot: 'Independent lineage matters' },
  { n: '05', tag: 'PUB', title: 'Public projection', body: 'Privacy, source policy, lifecycle and location precision determine what can cross into the public Live surface.', foot: 'Fail closed' },
  { n: '06', tag: 'ARC', title: 'Persistent record', body: 'Play preserves public case timelines so later evidence can enrich the record without rewriting what was known before.', foot: 'Traceable history' },
];

const METHOD = [
  { n: '01', title: 'Provenance', body: 'Every record keeps where it came from, when it arrived and which transformations produced later outputs.' },
  { n: '02', title: 'Source independence', body: 'Two transports carrying the same underlying observation do not count as two independent confirmations.' },
  { n: '03', title: 'Uncertainty', body: 'Missing fields, approximate locations, conflicting evidence and degraded coverage remain visible.' },
  { n: '04', title: 'Contestability', body: 'A case can accumulate support, contradiction or correction without hiding the earlier evidentiary state.' },
];

export default function SystemView() {
  return (
    <section id="system" className="section systemview">
      <SectionLabel index="Architecture / 005" title="From evidence to public record" tone="dark" />
      <div className="systemview__head">
        <Display id="system-title">
          One pipeline.<br />No parallel truth.
        </Display>
        <Reveal delay={120}>
          <p>
            The database is the durable source of record. Live and Play are projections of the same
            canonical evidence model, not separate analytical pipelines. Public surfaces receive only
            the subset allowed by publication and privacy policy.
          </p>
        </Reveal>
      </div>

      <Reveal as="ol" className="pipeline pipeline--six" stagger={70}>
        {STEPS.map((s) => (
          <li key={s.n}>
            <div><span>{s.n}</span><i>{s.tag}</i></div>
            <h3>{s.title}</h3>
            <p>{s.body}</p>
            <small>{s.foot}</small>
          </li>
        ))}
      </Reveal>

      <div id="method" className="method">
        <SectionLabel index="Method / 005A" title="What the system refuses to collapse" />
        <div className="method__head">
          <Display id="method-title">
            Evidence stays distinguishable from interpretation.
          </Display>
          <Reveal delay={120}>
            <p>
              SeaCommons is useful only if a reader can inspect the chain. Observation, normalized
              event, derived cue, episode, hypothesis and public case are intentionally different
              objects with different evidentiary meanings.
            </p>
          </Reveal>
        </div>
        <Reveal className="method__grid" stagger={90}>
          {METHOD.map((m) => (
            <article key={m.n}>
              <span>{m.n}</span>
              <h3>{m.title}</h3>
              <p>{m.body}</p>
            </article>
          ))}
        </Reveal>
      </div>
    </section>
  );
}
