import React from 'react';
import { Reveal } from '../../ui/index.js';
import { SectionLabel, Display } from '../bits.jsx';

const TIERS = [
  { code: 'PUBLIC / P0', title: 'Methods and synthetic fixtures', body: 'Open source code, documentation, aggregated indicators and scenarios that do not represent real people.', tone: 'lime' },
  { code: 'RESEARCH / R1', title: 'Controlled analytical material', body: 'Purpose-bound datasets with documented minimisation, access, review and retention conditions.', tone: 'sea' },
  { code: 'OPERATIONAL / O2', title: 'Live and identifying information', body: 'Positions, contact details and case material available only to authorised teams and audited services.', tone: 'amber' },
];

const PRINCIPLES = ['Data minimisation', 'Purpose limitation', 'Human review', 'Correction by design', 'Dual-use assessment', 'Documented deletion'];

export default function Governance() {
  return (
    <section id="governance" className="section governance">
      <SectionLabel index="Governance / 008" title="Access follows sensitivity" />
      <div className="governance__grid">
        <Display id="governance-title">Open where safe.<br />Restricted where necessary.</Display>
        <Reveal className="tiers" stagger={90}>
          {TIERS.map((t) => (
            <article className={`tier tier--${t.tone}`} key={t.code}>
              <span>{t.code}</span>
              <h3>{t.title}</h3>
              <p>{t.body}</p>
            </article>
          ))}
        </Reveal>
      </div>
      <Reveal className="principles" stagger={60}>
        {PRINCIPLES.map((p) => <p key={p}>{p}</p>)}
      </Reveal>

      <div className="limits">
        <Reveal className="limits__heading" y={12}>
          <span>Operational boundary</span>
          <h2>This is research infrastructure.<br />It is not an emergency service.</h2>
        </Reveal>
        <Reveal className="limits__copy" delay={120}>
          <p>
            SeaCommons outputs are experimental and may be incomplete, delayed or wrong. They must not
            replace official search-and-rescue coordination, emergency communications or qualified
            operational judgment.
          </p>
          <p>
            If a life may be at risk, contact the appropriate emergency and maritime rescue authorities
            through established channels.
          </p>
        </Reveal>
      </div>
    </section>
  );
}
