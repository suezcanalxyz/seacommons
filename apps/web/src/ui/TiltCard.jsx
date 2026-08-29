import React, { useRef } from 'react';
import { hasFinePointer, prefersReducedMotion } from './motion.js';

/**
 * Subtle 3D tilt toward the cursor. Transform-only, no animation loop (the
 * browser interpolates via CSS transition). Disabled for touch + reduced
 * motion, where it is an ordinary div.
 */
export default function TiltCard({ children, className = '', max = 6, ...rest }) {
  const ref = useRef(null);
  const enabled = useRef(hasFinePointer() && !prefersReducedMotion());

  const onMove = (e) => {
    const el = ref.current;
    if (!el || !enabled.current) return;
    const r = el.getBoundingClientRect();
    const px = (e.clientX - r.left) / r.width - 0.5;
    const py = (e.clientY - r.top) / r.height - 0.5;
    el.style.transform = `perspective(900px) rotateX(${(-py * max).toFixed(2)}deg) rotateY(${(px * max).toFixed(2)}deg)`;
  };
  const onLeave = () => {
    if (ref.current) ref.current.style.transform = '';
  };

  return (
    <div
      ref={ref}
      className={`sc-tilt ${className}`.trim()}
      onPointerMove={onMove}
      onPointerLeave={onLeave}
      {...rest}
    >
      {children}
    </div>
  );
}
