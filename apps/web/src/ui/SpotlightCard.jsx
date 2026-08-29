import React, { useRef } from 'react';

/**
 * Card with a soft radial highlight that tracks the cursor. Pure CSS custom
 * properties — no animation loop, no JS on non-hover devices. The highlight is
 * decorative; it fades out when the pointer leaves.
 */
export default function SpotlightCard({ as: Tag = 'div', children, className = '', ...rest }) {
  const ref = useRef(null);

  const onMove = (e) => {
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    el.style.setProperty('--spot-x', `${e.clientX - r.left}px`);
    el.style.setProperty('--spot-y', `${e.clientY - r.top}px`);
    el.style.setProperty('--spot-opacity', '1');
  };
  const onLeave = () => {
    ref.current?.style.setProperty('--spot-opacity', '0');
  };

  return (
    <Tag
      ref={ref}
      className={`sc-spotlight ${className}`.trim()}
      onPointerMove={onMove}
      onPointerLeave={onLeave}
      {...rest}
    >
      {children}
    </Tag>
  );
}
