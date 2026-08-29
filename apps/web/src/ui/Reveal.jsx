import React, { useEffect, useRef, useState } from 'react';
import { useInView, useReducedMotion } from './motion.js';

/**
 * Scroll-reveal wrapper. CSS-transition based (not JS-animated) so it can never
 * be starved by a busy main thread and degrades cleanly: the element and its
 * children are fully visible by default, and the reveal only adds a one-time
 * fade/rise the first time the block scrolls into view.
 *
 * `stagger` (ms) > 0 delays each direct child in turn — use for grids / lists.
 */
export default function Reveal({
  as: Tag = 'div',
  children,
  className = '',
  delay = 0,
  y = 22,
  duration = 720,
  stagger: staggerMs = 0,
  style,
  ...rest
}) {
  const ref = useRef(null);
  const reduced = useReducedMotion();
  const inView = useInView(ref);
  const [revealed, setRevealed] = useState(false);

  useEffect(() => {
    if (inView) setRevealed(true);
  }, [inView]);

  const active = reduced || revealed;

  useEffect(() => {
    const el = ref.current;
    if (!el || staggerMs <= 0) return;
    // Per-child transition delay for staggered grids.
    Array.from(el.children).forEach((child, i) => {
      child.style.transitionDelay = active ? `${delay + i * staggerMs}ms` : '0ms';
    });
  }, [active, delay, staggerMs]);

  return (
    <Tag
      ref={ref}
      className={`sc-reveal ${staggerMs > 0 ? 'sc-reveal--stagger' : ''} ${active ? 'is-in' : ''} ${className}`.trim()}
      style={{
        '--reveal-y': `${y}px`,
        '--reveal-duration': `${duration}ms`,
        '--reveal-delay': `${delay}ms`,
        ...style,
      }}
      {...rest}
    >
      {children}
    </Tag>
  );
}
