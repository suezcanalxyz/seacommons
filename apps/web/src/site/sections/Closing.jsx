import React from 'react';
import { Reveal, SpotlightCard } from '../../ui/index.js';

export default function Closing() {
  return (
    <section className="section closing">
      <Reveal className="closing__intro" y={14}>
        <span>Choose a surface</span>
        <h2>Inspect the project from the level you need.</h2>
      </Reveal>
      <Reveal className="closing__cards" stagger={110}>
        <SpotlightCard as="a" className="closing-card closing-card--play" href="https://play.seacommons.org">
          <span>Public / synthetic</span>
          <strong>Play</strong>
          <p>Explore bounded drift scenarios without operational data.</p>
          <i aria-hidden="true">↗</i>
        </SpotlightCard>
        <SpotlightCard as="a" className="closing-card closing-card--live" href="https://live.seacommons.org">
          <span>Controlled / authenticated</span>
          <strong>Live</strong>
          <p>Enter the research console with authorised institutional access.</p>
          <i aria-hidden="true">↗</i>
        </SpotlightCard>
      </Reveal>
    </section>
  );
}
