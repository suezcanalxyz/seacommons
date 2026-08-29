import React from 'react';
import { useReducedMotion } from './motion.js';

/**
 * Horizontal marquee. Content is duplicated so the loop is seamless; the copy
 * is aria-hidden. Reduced motion → a static, non-scrolling row (wraps).
 */
export default function Ticker({ items, className = '', duration = 38, separator = '/' }) {
  const reduced = useReducedMotion();
  const row = (hidden) => (
    <div className="sc-ticker__row" aria-hidden={hidden || undefined}>
      {items.map((item, i) => (
        <span className="sc-ticker__item" key={i}>
          {item}
          <i className="sc-ticker__sep" aria-hidden="true">{separator}</i>
        </span>
      ))}
    </div>
  );

  if (reduced) {
    return <div className={`sc-ticker is-static ${className}`.trim()}>{row(false)}</div>;
  }
  return (
    <div className={`sc-ticker ${className}`.trim()} style={{ '--ticker-duration': `${duration}s` }}>
      <div className="sc-ticker__track">
        {row(false)}
        {row(true)}
      </div>
    </div>
  );
}
