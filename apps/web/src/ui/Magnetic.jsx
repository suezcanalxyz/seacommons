import React, { useEffect, useRef } from 'react';
import { animate } from 'animejs';
import { hasFinePointer, prefersReducedMotion } from './motion.js';

/**
 * Wraps an interactive element so it drifts a few pixels toward the cursor on
 * hover, then springs back on leave. Mouse-only and disabled under reduced
 * motion — touch users get the element unchanged.
 */
export default function Magnetic({ children, strength = 0.28, className }) {
  const ref = useRef(null);

  useEffect(() => {
    const el = ref.current;
    if (!el || !hasFinePointer() || prefersReducedMotion()) return undefined;

    const onMove = (e) => {
      const r = el.getBoundingClientRect();
      const x = (e.clientX - (r.left + r.width / 2)) * strength;
      const y = (e.clientY - (r.top + r.height / 2)) * strength;
      animate(el, { translateX: x, translateY: y, duration: 320, ease: 'out(3)' });
    };
    const onLeave = () => {
      animate(el, { translateX: 0, translateY: 0, duration: 520, ease: 'outElastic(1, .6)' });
    };
    el.addEventListener('pointermove', onMove);
    el.addEventListener('pointerleave', onLeave);
    return () => {
      el.removeEventListener('pointermove', onMove);
      el.removeEventListener('pointerleave', onLeave);
    };
  }, [strength]);

  return (
    <span ref={ref} className={className} style={{ display: 'inline-flex', willChange: 'transform' }}>
      {children}
    </span>
  );
}
