import React from 'react';
import { Reveal, TiltCard } from '../../ui/index.js';
import { SectionLabel, Display } from '../bits.jsx';

const WP = [
  {
    n: '01',
    tag: 'Observe',
    title: 'Collect heterogeneous evidence',
    body: 'Public reporting, AIS, maritime radio, satellite observations and environmental context enter as source-bound records.',
    points: ['Source identity', 'Time and location provenance', 'Privacy classification'],
    code: 'SOURCE → OBS',
    tone: 'blue',
  },
  {
    n: '02',
    tag: 'Normalize',
    title: 'Translate without flattening',
    body: 'Provider-specific fields are mapped into a shared vocabulary while authority, precision and lineage remain attached.',
    points: ['Canonical vocabulary', 'Coordinate precision', 'Transport ≠ source'],
    code: 'OBS → EVENT',
    tone: 'lime',
  },
  {
    n: '03',
    tag: 'Correlate',
    title: 'Build episodes and hypotheses',
    body: 'Compatible observations are grouped using identity, time, space and lineage constraints. Derived cues remain distinguishable from facts.',
    points: ['Episodes', 'Investigation hypotheses', 'Independent corroboration'],
    code: 'EVENT → CASE?',
    tone: 'paper',
  },
  {
    n: '04',
    tag: 'Publish',
    title: 'Project only what is safe',
    body: 'A reduced public projection powers Live, while Play preserves the persistent public case record and timeline.',
    points: ['Public publication gate', 'Lifecycle integrity', 'Persistent archive'],
    code: 'CASE → LIVE / PLAY',
    tone: 'amber',
  },
];

export default function Programme() {
  return (
    <section id="research" className="section programme">
      <SectionLabel index="Pipeline / 004" title="How SeaCommons works" tone="light" />
      <div className="programme__head">
        <Display id="research-title">
          From source material<br />to a traceable public case.
        </Display>
        <Reveal delay={120}>
          <p>
            SeaCommons does not collapse every signal into one confidence score. Each transformation
            remains attributable, so a reader can distinguish source material, normalization,
            derived analysis, correlation and publication.
          </p>
        </Reveal>
      </div>

      <Reveal className="wp-grid" stagger={90}>
        {WP.map((w) => (
          <TiltCard className={`wp-card wp-card--${w.tone}`} key={w.n}>
            <div className="wp-card__top">
              <span>{w.n}</span>
              <span>{w.tag}</span>
            </div>
            <h3>{w.title}</h3>
            <p>{w.body}</p>
            <ul>{w.points.map((p) => <li key={p}>{p}</li>)}</ul>
            <span className="wp-card__code" aria-hidden="true">{w.code}</span>
          </TiltCard>
        ))}
      </Reveal>
    </section>
  );
}
