import React from 'react';
import { Reveal, SpotlightCard } from '../../ui/index.js';
import { SectionLabel, Display } from '../bits.jsx';

const HUMANITARIAN = [
  'Distress and rescue reports',
  'Missing persons and shipwrecks',
  'Pushbacks and migration incidents',
  'SAR activity and resolution evidence',
  'NGO and civil-fleet verification',
];

const MARITIME = [
  'AIS gaps and dark-activity candidates',
  'Position and identity integrity',
  'Transfers, rendezvous and loitering',
  'Navigation safety and port-call context',
  'Infrastructure, sanctions and security context',
];

const SURFACES = [
  {
    label: 'Live',
    href: 'https://live.seacommons.org',
    meta: 'Current public cases',
    body: 'A case-first operational view of Humanitarian and Maritime events that satisfy the public publication gate.',
  },
  {
    label: 'Play',
    href: 'https://play.seacommons.org',
    meta: 'Persistent case archive',
    body: 'The public catalogue of cases, timelines and evidence records. Cases remain inspectable as new information arrives.',
  },
  {
    label: 'Docs',
    href: '/docs',
    meta: 'Technical reference',
    body: 'Architecture, provenance, verification, source independence, API contracts, privacy boundaries and system limits.',
  },
];

export default function Domains() {
  return (
    <section className="section domains" aria-labelledby="domains-title">
      <SectionLabel index="Scope / 001" title="Two domains, one evidence model" />
      <div className="domains__head">
        <Display id="domains-title">
          Humanitarian incidents<br />and maritime investigations.
        </Display>
        <Reveal delay={120}>
          <p>
            SeaCommons collects fragmented maritime evidence and turns it into traceable public
            cases. The system separates what was observed from what was derived, keeps source
            lineage visible, and never treats an analytical cue as a factual finding.
          </p>
        </Reveal>
      </div>

      <Reveal className="domains__grid" stagger={100}>
        <article id="humanitarian" className="domain-card domain-card--humanitarian">
          <div className="domain-card__top">
            <span>Humanitarian</span>
            <small>People · distress · rescue</small>
          </div>
          <h3>Events where human safety and rescue context are central.</h3>
          <p>
            Humanitarian records combine operational reports, civil SAR information, public
            testimony, vessel context and resolution evidence under stricter privacy and
            publication rules.
          </p>
          <ul>
            {HUMANITARIAN.map((item) => <li key={item}>{item}</li>)}
          </ul>
          <a href="#humanitarian-detail">How Humanitarian cases are built ↓</a>
        </article>

        <article id="maritime" className="domain-card domain-card--maritime">
          <div className="domain-card__top">
            <span>Maritime</span>
            <small>Vessels · behaviour · context</small>
          </div>
          <h3>Investigations into vessel behaviour, identity and maritime context.</h3>
          <p>
            Maritime cases combine AIS, radio, satellite and contextual sources to surface
            patterns worth investigating while keeping uncertainty, coverage limitations and
            source independence explicit.
          </p>
          <ul>
            {MARITIME.map((item) => <li key={item}>{item}</li>)}
          </ul>
          <a href="#maritime-detail">How Maritime investigations are built ↓</a>
        </article>
      </Reveal>

      <div className="domains__surfaces">
        <SectionLabel index="Access / 002" title="Three ways to read SeaCommons" />
        <Reveal className="domains__surface-grid" stagger={90}>
          {SURFACES.map((surface) => (
            <SpotlightCard as="a" className="surface-card" href={surface.href} key={surface.label}>
              <span>{surface.meta}</span>
              <strong>{surface.label}</strong>
              <p>{surface.body}</p>
              <i aria-hidden="true">↗</i>
            </SpotlightCard>
          ))}
        </Reveal>
      </div>
    </section>
  );
}
