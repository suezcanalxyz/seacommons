import React from 'react';
import { Reveal, SpotlightCard } from '../../ui/index.js';
import { SectionLabel, Display } from '../bits.jsx';

const HUMANITARIAN = [
  'Distress and rescue reports',
  'Missing persons and shipwrecks',
  'Pushbacks and migration incidents',
  'SAR activity and rescue outcomes',
  'Civil SAR and NGO verification',
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
    meta: 'Explore recent cases',
    body: 'Explore recent public cases on a map. Each one is shown with the information available and its limitations.',
  },
  {
    label: 'Play',
    href: 'https://play.seacommons.org',
    meta: 'Revisit the past',
    body: 'Go back through maritime events, follow their timelines and see what later evidence adds.',
  },
  {
    label: 'Docs',
    href: '/docs',
    meta: 'Understand the evidence',
    body: 'Find out where the information comes from, how it is checked and why some questions remain open.',
  },
];

export default function Domains() {
  return (
    <section className="section domains" aria-labelledby="domains-title">
      <SectionLabel index="Scope / 001" title="What SeaCommons follows" />
      <div className="domains__head">
        <Display id="domains-title">
          What can we learn<br />from the sea?
        </Display>
        <Reveal delay={120}>
          <p>
            Some records concern people in distress. Others concern vessels, navigation and maritime security. SeaCommons brings them into one research environment, while keeping different kinds of evidence and privacy needs separate.
          </p>
        </Reveal>
      </div>

      <Reveal className="domains__grid" stagger={100}>
        <article id="humanitarian" className="domain-card domain-card--humanitarian">
          <div className="domain-card__top">
            <span>Humanitarian</span>
            <small>People · distress · rescue</small>
          </div>
          <h3>When someone reports an emergency at sea, what can we verify?</h3>
          <p>
            A humanitarian case can begin with a call, a public report or a rescue organisation's
            update. Coordinates may be exact, approximate, area-level or absent. SeaCommons keeps
            that precision visible and restricts sensitive material before anything becomes public.
          </p>
          <ul>
            {HUMANITARIAN.map((item) => <li key={item}>{item}</li>)}
          </ul>
          <a href="#humanitarian-detail">Read the humanitarian method ↓</a>
        </article>

        <article id="maritime" className="domain-card domain-card--maritime">
          <div className="domain-card__top">
            <span>Maritime</span>
            <small>Vessels · behaviour · context</small>
          </div>
          <h3>What can vessel movements tell us — and what can't they?</h3>
          <p>
            A gap in AIS, a close approach between vessels or a sanctions match is not a conclusion.
            SeaCommons treats these as reasons to look closer, checks coverage and source lineage,
            and keeps ordinary explanations visible alongside the suspicious ones.
          </p>
          <ul>
            {MARITIME.map((item) => <li key={item}>{item}</li>)}
          </ul>
          <a href="#maritime-detail">Read the maritime method ↓</a>
        </article>
      </Reveal>

      <div className="domains__preview" aria-label="SeaCommons product previews"><a href="https://live.seacommons.org"><img src="/og/seacommons-live.png" alt="Preview of the SeaCommons LIVE map" loading="lazy"/><span>LIVE / Explore recent maritime observations ↗</span></a><a href="https://play.seacommons.org"><img src="/og/seacommons-play.png" alt="Preview of the SeaCommons PLAY investigation map" loading="lazy"/><span>PLAY / Investigate an event over time ↗</span></a></div><div className="domains__surfaces">
        <SectionLabel index="Access / 002" title="Live, archive and technical reference" />
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
