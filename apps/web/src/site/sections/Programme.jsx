import React from 'react';
import { Reveal, TiltCard } from '../../ui/index.js';
import { SectionLabel, Display } from '../bits.jsx';

const WP = [
  {
    n: 'WP / 01',
    tag: 'Corpus',
    title: 'Governed observations',
    body: 'Canonical signal records, provenance, sensitivity tiers, consent and retention rules.',
    points: ['Source lineage', 'Idempotent intake', 'Access boundaries'],
    code: 'OBS → REC',
    tone: 'blue',
  },
  {
    n: 'WP / 02',
    tag: 'Fusion',
    title: 'Calibrated inference',
    body: 'Reliability, missingness and conflicting evidence remain visible throughout analysis.',
    points: ['Confidence', 'Human review', 'Source comparison'],
    code: 'SIG ≠ FACT',
    tone: 'lime',
  },
  {
    n: 'WP / 03',
    tag: 'Drift',
    title: 'Ensemble trajectories',
    body: 'Search surfaces shaped by ocean and atmosphere forcing, expressed as probabilistic ranges rather than point estimates.',
    points: ['OpenDrift', 'CMEMS forcing', 'Uncertainty cones'],
    code: 'T₀ → T₊₂₄',
    tone: 'paper',
  },
  {
    n: 'WP / 04',
    tag: 'Decision',
    title: 'Accountable interfaces',
    body: 'Human-centred views that support scrutiny, correction and proportionate action.',
    points: ['Case timelines', 'Audit trails', 'Operational limits'],
    code: 'ACT + TRACE',
    tone: 'amber',
  },
];

export default function Programme() {
  return (
    <section id="research" className="section programme">
      <SectionLabel index="Programme / 003" title="Four connected workstreams" tone="light" />
      <Display id="research-title">
        Four workstreams,<br />one accountable pipeline.
      </Display>

      <Reveal className="wp-grid" stagger={90}>
        {WP.map((w) => (
          <TiltCard className={`wp-card wp-card--${w.tone}`} key={w.n}>
            <div className="wp-card__top">
              <span>{w.n}</span>
              <span>{w.tag}</span>
            </div>
            <h3>{w.title}</h3>
            <p>{w.body}</p>
            <ul>
              {w.points.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
            <span className="wp-card__code" aria-hidden="true">{w.code}</span>
          </TiltCard>
        ))}
      </Reveal>
    </section>
  );
}
