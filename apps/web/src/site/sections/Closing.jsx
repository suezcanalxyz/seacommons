import React from 'react';
import { Reveal, SpotlightCard } from '../../ui/index.js';

const CARDS = [
  {
    cls: 'closing-card--live',
    href: 'https://live.seacommons.org',
    meta: 'Current public cases',
    title: 'Live',
    body: 'See Humanitarian and Maritime cases that currently satisfy the public publication gate.',
  },
  {
    cls: 'closing-card--play',
    href: 'https://play.seacommons.org',
    meta: 'Persistent public archive',
    title: 'Play',
    body: 'Inspect case records, timelines and evidence as the public archive grows over time.',
  },
  {
    cls: 'closing-card--docs',
    href: '/docs',
    meta: 'Architecture and method',
    title: 'Docs',
    body: 'Read the technical reference for provenance, correlation, privacy, API contracts and limitations.',
  },
];

export default function Closing() {
  return (
    <section className="section closing">
      <Reveal className="closing__intro" y={14}>
        <span>Choose a surface</span>
        <h2>Start simple, then inspect the evidence model in depth.</h2>
      </Reveal>
      <Reveal className="closing__cards" stagger={110}>
        {CARDS.map((card) => (
          <SpotlightCard as="a" className={`closing-card ${card.cls}`} href={card.href} key={card.title}>
            <span>{card.meta}</span>
            <strong>{card.title}</strong>
            <p>{card.body}</p>
            <i aria-hidden="true">↗</i>
          </SpotlightCard>
        ))}
      </Reveal>
    </section>
  );
}
