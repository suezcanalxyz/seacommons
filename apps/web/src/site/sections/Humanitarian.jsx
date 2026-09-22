import React from 'react';
import { Reveal } from '../../ui/index.js';
import { SectionLabel, Display } from '../bits.jsx';

const FLOW = [
  ['01', 'Origin', 'An operational or public report enters with source identity, time, transport and coordinate provenance preserved.'],
  ['02', 'Claims', 'Deterministic claims such as rescue completed, people rescued, disembarkation or fatalities remain separate from lifecycle state.'],
  ['03', 'Association', 'Additional NGO, AIS or public evidence is linked only when identity, time, place and source-lineage constraints are compatible.'],
  ['04', 'Resolution', 'Resolution evidence can support the case record, but one technical signal does not automatically close a Humanitarian incident.'],
];

const SOURCES = [
  'Alarm Phone and operational-origin reporting',
  'Civil SAR NGOs and verification organisations',
  'AIS vessel activity and SAR-response context',
  'Public news, RSS and institutional reporting',
  'Environmental context when relevant to reconstruction',
];

export default function Humanitarian() {
  return (
    <section id="humanitarian-detail" className="section humanitarian">
      <SectionLabel index="Humanitarian / 003" title="Humanitarian evidence" tone="light" />
      <div className="humanitarian__head">
        <Display id="humanitarian-title">
          A distress report is not a complete case.<br />SeaCommons builds the chain around it.
        </Display>
        <Reveal delay={120}>
          <p>
            Humanitarian evidence can arrive late, through different channels and with uncertain
            coordinates. SeaCommons keeps those differences explicit, protects sensitive material
            and only publishes a reduced public projection.
          </p>
        </Reveal>
      </div>

      <Reveal as="ol" className="humanitarian__flow" stagger={80}>
        {FLOW.map(([n, title, body]) => (
          <li key={n}>
            <span>{n}</span>
            <h3>{title}</h3>
            <p>{body}</p>
          </li>
        ))}
      </Reveal>

      <div className="humanitarian__sources">
        <Reveal>
          <div>
            <span>Typical evidence</span>
            <h3>Several sources can describe the same event without being independent.</h3>
          </div>
        </Reveal>
        <Reveal as="ul" stagger={70}>
          {SOURCES.map((source) => <li key={source}>{source}</li>)}
        </Reveal>
      </div>

      <Reveal className="humanitarian__rule">
        <strong>Key rule</strong>
        <p>
          Transport is not source independence. The same organisation publishing through X, RSS
          and email remains one lineage. AIS can support response assessment, but AIS alone does
          not prove that a rescue was completed.
        </p>
      </Reveal>
    </section>
  );
}
