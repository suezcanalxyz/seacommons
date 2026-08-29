import React from 'react';
import { Reveal, TiltCard } from '../../ui/index.js';
import { SectionLabel, Display } from '../bits.jsx';

const CAPABILITIES = [
  {
    n: 'MDA / 01',
    tag: 'Identity',
    title: 'Vessel identity & spoofing',
    body: 'AIS trace anomalies — circular, teleporting or frozen tracks — flagged as identity questions, not identity conclusions.',
    points: ['Pattern detection', 'GNSS jamming index', 'Confidence, not verdict'],
    code: 'ID ? = ID',
    tone: 'blue',
  },
  {
    n: 'MDA / 02',
    tag: 'Correlation',
    title: 'Shadow-fleet correlation',
    body: 'Ship-to-ship rendezvous, infrastructure loiter and gap-in-track patterns correlated across public sources before a case is opened.',
    points: ['STS rendezvous', 'Corroboration required', 'No single-source cases'],
    code: 'OBS × OBS',
    tone: 'lime',
  },
  {
    n: 'MDA / 03',
    tag: 'Context',
    title: 'Grey-zone corroboration',
    body: 'Sanctions and grey-zone context is surfaced as a fusion input alongside other evidence, gated to reduce false-positive alerting.',
    points: ['Multi-source rule', 'Alert suppression', 'Reviewable rationale'],
    code: 'CTX + EVID',
    tone: 'paper',
  },
  {
    n: 'MDA / 04',
    tag: 'Infrastructure',
    title: 'Chokepoint & infrastructure analytics',
    body: 'Cables, pipelines, platforms and ports indexed as a geographic reference layer for proximity and traffic-pattern analysis.',
    points: ['Reference index', 'Traffic patterns', 'Read-only layer'],
    code: 'GEO / REF',
    tone: 'amber',
  },
];

export default function MDA() {
  return (
    <section id="mda" className="section programme">
      <SectionLabel index="MDA / 007" title="Maritime domain awareness" tone="light" />
      <Display id="mda-title">
        The same fusion discipline,<br />applied to a wider signal set.
      </Display>
      <Reveal delay={120}>
        <p>
          Alongside distress fusion, SeaCommons develops maritime domain awareness (MDA) methods —
          vessel identity, shadow-fleet behaviour, sanctions context and infrastructure proximity —
          built on the same corroboration and human-review rules described in Governance. MDA
          outputs are not published as a real-time public feed: access follows the OPERATIONAL / O2
          tier, and no case is opened from a single uncorroborated source.
        </p>
      </Reveal>

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
              {c.points.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
            <span className="wp-card__code" aria-hidden="true">{c.code}</span>
          </TiltCard>
        ))}
      </Reveal>
    </section>
  );
}
