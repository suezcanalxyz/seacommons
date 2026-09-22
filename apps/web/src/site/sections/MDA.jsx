import React from 'react';
import { Reveal, TiltCard } from '../../ui/index.js';
import { SectionLabel, Display } from '../bits.jsx';

const CAPABILITIES = [
  {
    n: 'MAR / 01',
    tag: 'Integrity',
    title: 'AIS gaps & dark-activity candidates',
    body: 'Coverage-aware gaps are treated as investigation cues, never as proof of deliberate concealment.',
    points: ['Neighbour coverage context', 'Provider health', 'Gap duration and location'],
    code: 'GAP ≠ INTENT',
    tone: 'blue',
  },
  {
    n: 'MAR / 02',
    tag: 'Identity',
    title: 'Position & identity integrity',
    body: 'Frozen, teleporting or otherwise inconsistent tracks become bounded integrity questions that can be compared with other evidence.',
    points: ['Track consistency', 'Identity context', 'No automatic verdict'],
    code: 'ID ? = ID',
    tone: 'lime',
  },
  {
    n: 'MAR / 03',
    tag: 'Behaviour',
    title: 'Transfers, rendezvous & loitering',
    body: 'Spatial and temporal relationships between vessels are grouped into episodes only when the underlying observations are compatible.',
    points: ['STS context', 'Loiter patterns', 'Independent lineage checks'],
    code: 'OBS × OBS',
    tone: 'paper',
  },
  {
    n: 'MAR / 04',
    tag: 'Context',
    title: 'Safety, infrastructure & security',
    body: 'Navigation status, ports, offshore infrastructure, sanctions references, radio and satellite observations can add context to a case.',
    points: ['Navigation safety', 'Infrastructure proximity', 'Sanctions as context'],
    code: 'CTX + EVID',
    tone: 'amber',
  },
];

export default function MDA() {
  return (
    <section id="maritime-detail" className="section programme maritime-detail">
      <SectionLabel index="Maritime / 006" title="Maritime investigations" tone="light" />
      <div className="maritime-detail__head">
        <Display id="maritime-title">
          Detect the pattern.<br />Preserve the uncertainty.
        </Display>
        <Reveal delay={120}>
          <p>
            SeaCommons combines vessel movement, radio, satellite and contextual observations to
            identify patterns worth investigating. A pattern is not an accusation: the system keeps
            coverage limitations, source lineage and alternative explanations visible throughout.
          </p>
        </Reveal>
      </div>

      <Reveal className="wp-grid" stagger={90}>
        {CAPABILITIES.map((c) => (
          <TiltCard className={`wp-card wp-card--${c.tone}`} key={c.n}>
            <div className="wp-card__top">
              <span>{c.n}</span>
              <span>{c.tag}</span>
            </div>
            <h3>{c.title}</h3>
            <p>{c.body}</p>
            <ul>
              {c.points.map((p) => <li key={p}>{p}</li>)}
            </ul>
            <span className="wp-card__code" aria-hidden="true">{c.code}</span>
          </TiltCard>
        ))}
      </Reveal>

      <Reveal className="maritime-detail__rule">
        <strong>Key rule</strong>
        <p>
          More providers do not automatically mean more independent evidence. One AIS broadcast
          received through two transports remains one AIS lineage. Corroboration requires evidence
          that is genuinely independent of the same underlying observation.
        </p>
      </Reveal>
    </section>
  );
}
