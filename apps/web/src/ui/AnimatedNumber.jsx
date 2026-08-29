import React, { useEffect, useRef, useState } from 'react';
import { animate } from 'animejs';
import { useInView, useReducedMotion } from './motion.js';

/**
 * Counts up to `value` when scrolled into view. Renders with tabular figures so
 * the width never jumps mid-count (no layout shift). Reduced motion → shows the
 * final value immediately.
 */
export default function AnimatedNumber({
  value,
  duration = 1400,
  decimals = 0,
  prefix = '',
  suffix = '',
  className,
}) {
  const ref = useRef(null);
  const reduced = useReducedMotion();
  const inView = useInView(ref, { threshold: 0.6 });
  const [display, setDisplay] = useState(() => (reduced ? value : 0));
  const played = useRef(false);

  useEffect(() => {
    if (played.current) return;
    if (reduced) {
      setDisplay(value);
      return;
    }
    if (!inView) return;
    played.current = true;
    const obj = { n: 0 };
    animate(obj, {
      n: value,
      duration,
      ease: 'out(4)',
      onUpdate: () => setDisplay(obj.n),
    });
  }, [inView, reduced, value, duration]);

  const shown = decimals > 0 ? display.toFixed(decimals) : String(Math.round(display));
  return (
    <span ref={ref} className={className} style={{ fontVariantNumeric: 'tabular-nums' }}>
      {prefix}
      {shown}
      {suffix}
    </span>
  );
}
