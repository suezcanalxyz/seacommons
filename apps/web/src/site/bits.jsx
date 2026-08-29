import React from 'react';
import { Reveal } from '../ui/index.js';

export function SectionLabel({ index, title, tone }) {
  return (
    <Reveal className={`section-label ${tone ? `section-label--${tone}` : ''}`.trim()} y={10} duration={520}>
      <span>{index}</span>
      <span>{title}</span>
    </Reveal>
  );
}

export function Display({ children, id, tone }) {
  return (
    <Reveal as="h2" id={id} className={`display ${tone ? `display--${tone}` : ''}`.trim()}>
      {children}
    </Reveal>
  );
}
