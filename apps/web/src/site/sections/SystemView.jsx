import React from 'react';
import { Reveal, SpotlightCard } from '../../ui/index.js';
import { SectionLabel, Display } from '../bits.jsx';

const STEPS = [
  { n: '01', tag: 'IN', title: 'Observe', body: 'Receive a public, partner, environmental or manually entered signal.', foot: 'Raw acquisition' },
  { n: '02', tag: 'QC', title: 'Qualify', body: 'Extract position, assess confidence, deduplicate and flag ambiguity.', foot: 'Human review boundary' },
  { n: '03', tag: 'SIM', title: 'Simulate', body: 'Run versioned environmental and drift models with explicit parameters.', foot: 'Ensemble output' },
  { n: '04', tag: 'LOG', title: 'Preserve', body: 'Link evidence, result and actor in a reviewable forensic chain.', foot: 'Signed audit record' },
];

const METHOD = [
  { n: '01', title: 'Provenance', body: 'Where the observation came from, when it arrived and how it was obtained.' },
  { n: '02', title: 'Transformation', body: 'Software version, environmental source, parameters and computational path.' },
  { n: '03', title: 'Uncertainty', body: 'Confidence, missing fields, disagreement and sensitivity to assumptions.' },
  { n: '04', title: 'Contestability', body: 'Corrections, alternative interpretations and the record of human decisions.' },
];

function DriftFigure() {
  return (
    <figure className="drift-figure">
      <figcaption>
        <span>Drift surface / illustrative</span>
        <span>Not for operational use</span>
      </figcaption>
      <svg viewBox="0 0 1200 300" role="img" aria-label="Illustrative ensemble of drift trajectories with widening uncertainty">
        <defs>
          <pattern id="scGrid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M 40 0 L 0 0 0 40" fill="none" stroke="currentColor" strokeWidth=".5" opacity=".22" />
          </pattern>
          <linearGradient id="scCone" x1="0" x2="1">
            <stop offset="0" stopColor="#c7dcf5" stopOpacity=".05" />
            <stop offset="1" stopColor="#c7dcf5" stopOpacity=".24" />
          </linearGradient>
        </defs>
        <rect width="1200" height="300" fill="url(#scGrid)" />
        <path
          className="df-bathy"
          d="M-60 96C220 46 360 210 620 150s330-16 470 62 260 44 410 4M-40 236c220-118 400 58 600-14s330-2 470 72 260 40 420-16"
        />
        <path className="df-cone df-cone--24" d="M110 246C230 190 400 100 610 66c150-24 360-18 480 14 108 62 40 150-110 190-230 62-540 74-980-24Z" />
        <path className="df-cone df-cone--12" d="M110 246c96-64 210-160 330-256 88-70 210-66 258 6 46 74-24 158-124 190-150 48-320 66-464 60Z" />
        <g className="df-ensemble">
          <path d="M110 246c110-58 200-146 320-208 110-56 260-70 420-40" />
          <path d="M110 246c98-72 176-172 292-232 116-60 268-58 424-16" />
          <path d="M110 246c86-46 176-118 268-186 122-88 292-96 452-52" />
        </g>
        <path className="df-trace" d="M110 246c100-64 188-160 300-224 116-66 264-72 420-30" />
        <g className="df-points">
          <polygon className="df-vessel" transform="translate(110,246) rotate(-32)" points="0,-8 6.5,6 -6.5,6" />
          <polygon className="df-vessel" transform="translate(340,148) rotate(-30)" points="0,-6 5,4.5 -5,4.5" />
          <polygon className="df-vessel" transform="translate(560,80) rotate(-18)" points="0,-6 5,4.5 -5,4.5" />
          <polygon className="df-vessel df-vessel--now" transform="translate(830,16) rotate(-10)" points="0,-9 7,7 -7,7" />
        </g>
        <g className="df-labels">
          <text x="86" y="278">T+00</text>
          <text x="316" y="182">T+06</text>
          <text x="536" y="114">T+12</text>
          <text x="806" y="50">T+24</text>
        </g>
        <circle className="df-marker" r="5">
          <animateMotion dur="9s" repeatCount="indefinite" path="M110 246c100-64 188-160 300-224 116-66 264-72 420-30" />
        </circle>
      </svg>
      <div className="drift-figure__legend">
        <span><i className="ln" /> Median trajectory</span>
        <span><i className="en" /> Ensemble members</span>
        <span><i className="ar" /> Uncertainty envelope</span>
      </div>
    </figure>
  );
}

export default function SystemView() {
  return (
    <section id="system" className="section systemview">
      <SectionLabel index="System / 004" title="Current research architecture" tone="dark" />
      <div className="systemview__head">
        <Display id="system-title">From intake to<br />an auditable trace.</Display>
        <Reveal delay={120}>
          <p>
            The interface never becomes the source of truth. Inputs, transformations, parameters and
            outputs are preserved as linked records that can be inspected independently.
          </p>
        </Reveal>
      </div>

      <Reveal as="ol" className="pipeline" stagger={80}>
        {STEPS.map((s) => (
          <li key={s.n}>
            <div><span>{s.n}</span><i>{s.tag}</i></div>
            <h3>{s.title}</h3>
            <p>{s.body}</p>
            <small>{s.foot}</small>
          </li>
        ))}
      </Reveal>

      <Reveal className="systemview__views" stagger={120}>
        <DriftFigure />
        <SpotlightCard as="article" className="evidence-panel">
          <header><span>Evidence packet</span><span>SC-EV-00041</span></header>
          <div className="evidence-panel__wave" aria-hidden="true">
            {Array.from({ length: 26 }).map((_, i) => <i key={i} />)}
          </div>
          <dl>
            <div><dt>Classification</dt><dd>Illustrative distress signal</dd></div>
            <div><dt>Position source</dt><dd>Explicit coordinate pair</dd></div>
            <div><dt>Confidence</dt><dd>0.82 / requires review</dd></div>
            <div><dt>Transformation</dt><dd>drift.engine / versioned</dd></div>
            <div><dt>Record status</dt><dd>Append-only / traceable</dd></div>
          </dl>
          <p>This packet is a design specimen. It contains no real person, vessel or event.</p>
        </SpotlightCard>
      </Reveal>

      <div id="method" className="method">
        <SectionLabel index="Method / 005" title="Proof before presentation" />
        <div className="method__head">
          <Display id="method-title">Explainability is a methodological requirement.</Display>
          <Reveal delay={120}>
            <p>
              Analytical authority does not come from visual polish. A useful result must expose what
              entered the system, what changed, what remains unknown and who can contest it.
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
