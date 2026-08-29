import React from 'react';
import { Reveal, SpotlightCard, AnimatedNumber } from '../../ui/index.js';
import { SectionLabel, Display } from '../bits.jsx';

const CARDS = [
  {
    tag: 'Operational',
    host: 'live.seacommons.org',
    name: 'LIVE',
    tone: 'lime',
    body: 'A public console that aggregates maritime signals — vessel tracking, marine weather, distress reports and civil-monitoring feeds — into one timestamped record of source health and observed activity. Provenance and confidence travel with each entry; sources are never silently merged into a single asserted position. Positional and case-level detail is limited to authorised research and rescue-support teams under documented access conditions.',
    href: 'https://live.seacommons.org',
    cta: 'Open the console ↗',
  },
  {
    tag: 'Public / browser',
    host: 'play.seacommons.org',
    name: 'PLAY',
    tone: 'paper',
    body: 'An interactive demonstrator that reconstructs a selected trace as a drift simulation, computed in the browser with CesiumJS from bounded or synthetic scenarios. It exposes the environmental fields, model parameters and uncertainty behind each trajectory, so a result can be inspected rather than taken on trust. PLAY does not use live distress data.',
    href: 'https://play.seacommons.org',
    cta: 'Open the demonstrator ↗',
  },
  {
    tag: 'In development',
    host: 'Accredited access planned',
    name: 'ENGINE',
    tone: 'sea',
    body: 'A companion Unreal Engine renderer for the same drift-scene record used by PLAY. Where PLAY favours accessibility, ENGINE favours physical fidelity: a calibrated sea state, weather and vessel response driven by the persisted wave height, period and direction, delivered through browser-based streaming. It renders the scene; it does not alter the underlying trajectory.',
    href: null,
    cta: null,
  },
];

const STATS = [
  { value: 3, label: 'environments, one dataset' },
  { value: 24, suffix: ' / 7', label: 'signal aggregation window' },
  { value: 100, suffix: ' %', label: 'transformations preserved as records' },
];

export default function Environments() {
  return (
    <section id="environments" className="section environments">
      <SectionLabel index="Surfaces / 001" title="One dataset, three environments" />
      <div className="environments__head">
        <Display id="environments-title">
          LIVE observes.<br />PLAY reconstructs.<br />ENGINE renders.
        </Display>
        <Reveal delay={120}>
          <p>
            The three environments read the same underlying signal and drift-scene records. They
            differ in what they are for, not in what they claim to know: LIVE is operational today,
            PLAY is a public research demonstrator, ENGINE is in development with restricted access
            planned.
          </p>
        </Reveal>
      </div>

      <Reveal className="environments__grid" stagger={90}>
        {CARDS.map((c) => (
          <SpotlightCard as="article" className={`env-card env-card--${c.tone}`} key={c.name}>
            <div className="env-card__top">
              <span>{c.tag}</span>
              <span>{c.host}</span>
            </div>
            <h3>{c.name}</h3>
            <p>{c.body}</p>
            {c.href ? (
              <a className="env-card__link" href={c.href}>{c.cta}</a>
            ) : (
              <span className="env-card__link is-muted">No public endpoint yet</span>
            )}
          </SpotlightCard>
        ))}
      </Reveal>

      <Reveal className="statband" stagger={110}>
        {STATS.map((s) => (
          <div className="statband__item" key={s.label}>
            <strong>
              <AnimatedNumber value={s.value} suffix={s.suffix || ''} />
            </strong>
            <span>{s.label}</span>
          </div>
        ))}
      </Reveal>

      <div className="thesis">
        <SectionLabel index="Position / 002" title="Why this infrastructure" />
        <div className="thesis__layout">
          <Display id="thesis-title">
            Maritime distress rarely produces a complete evidentiary record.
          </Display>
          <Reveal className="thesis__copy" delay={120}>
            <p>
              Distress evidence arrives as partial coordinates, delayed vessel tracks, changing
              weather, public testimony, messages and institutional reports. Each source has a
              different clock, resolution, bias and risk.
            </p>
            <p>
              SeaCommons studies how these heterogeneous fragments can be related to one another
              without converting uncertainty into unwarranted certainty, and without compromising
              the safety of the people they describe.
            </p>
          </Reveal>
          <Reveal as="blockquote" delay={200}>
            <span>Research question</span>
            How can heterogeneous maritime signals support timely action while remaining
            explainable, correctable and safe?
          </Reveal>
        </div>
      </div>
    </section>
  );
}
