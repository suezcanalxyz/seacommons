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
      <svg viewBox="0 0 760 460" role="img" aria-label="Illustrative uncertainty cones around a simulated drift trajectory">
        <defs>
          <pattern id="scGrid" width="38" height="38" patternUnits="userSpaceOnUse">
            <path d="M 38 0 L 0 0 0 38" fill="none" stroke="currentColor" strokeWidth=".5" opacity=".25" />
          </pattern>
          <linearGradient id="scCone" x1="0" x2="1">
            <stop offset="0" stopColor="#c7dcf5" stopOpacity=".06" />
            <stop offset="1" stopColor="#c7dcf5" stopOpacity=".26" />
          </linearGradient>
        </defs>
        <rect width="760" height="460" fill="url(#scGrid)" />
        <path className="df-bathy" d="M-40 92C100 44 166 172 294 128s174-10 246 60 158 48 260 6M-20 320c120-72 220 40 324-10s180-2 254 46 146 36 230-12" />
        <path className="df-cone df-cone--24" d="M129 344C184 300 275 216 376 124c77-70 190-72 254-1 61 67 23 159-56 197-113 54-279 69-445 24Z" />
        <path className="df-cone df-cone--12" d="M129 344c61-42 135-105 209-168 54-46 133-43 163 3 31 49-16 105-78 126-95 31-201 43-294 39Z" />
        <path className="df-trace" d="M129 344c82-51 138-117 226-172 72-45 142-51 224-18" />
        <g className="df-points">
          <circle cx="129" cy="344" r="7" />
          <circle cx="257" cy="247" r="5" />
          <circle cx="355" cy="172" r="5" />
          <circle cx="471" cy="139" r="5" />
          <circle cx="579" cy="154" r="7" />
        </g>
        <g className="df-labels">
          <text x="108" y="379">T+00</text>
          <text x="238" y="281">T+06</text>
          <text x="337" y="205">T+12</text>
          <text x="563" y="190">T+24</text>
        </g>
      </svg>
      <div className="drift-figure__legend">
        <span><i className="ln" /> Median trajectory</span>
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
