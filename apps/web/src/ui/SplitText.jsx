import React, { useEffect, useMemo, useRef } from 'react';
import { useInView, useReducedMotion } from './motion.js';

/**
 * Headline that reveals word by word using CSS transitions (main-thread-proof).
 * The full text stays selectable and is exposed to assistive tech as one string
 * via aria-label; the per-word spans are aria-hidden and visible by default, so
 * a failure or reduced-motion just shows the finished headline.
 */
export default function SplitText({ text, as: Tag = 'span', className = '', delay = 0, stepMs = 46 }) {
  const ref = useRef(null);
  const reduced = useReducedMotion();
  const inView = useInView(ref, { threshold: 0.25 });
  const words = useMemo(() => String(text).split(/(\s+)/), [text]);
  const active = reduced || inView;

  useEffect(() => {
    const el = ref.current;
    if (!el || reduced) return;
    const spans = el.querySelectorAll('[data-word]');
    spans.forEach((s, i) => {
      s.style.transitionDelay = active ? `${delay + i * stepMs}ms` : '0ms';
    });
  }, [active, delay, stepMs, reduced]);

  return (
    <Tag ref={ref} className={`sc-split ${active ? 'is-in' : ''} ${className}`.trim()} aria-label={text}>
      {words.map((w, i) =>
        /\s+/.test(w) ? (
          <React.Fragment key={i}> </React.Fragment>
        ) : (
          <span key={i} data-word aria-hidden="true">
            {w}
          </span>
        ),
      )}
    </Tag>
  );
}
