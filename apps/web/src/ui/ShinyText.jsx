import React from 'react';
import { useReducedMotion } from './motion.js';

/**
 * Text with a slow specular sweep passing across it. CSS-only animation
 * (background-position); disabled under reduced motion, where it renders as a
 * flat accent-coloured string.
 */
export default function ShinyText({ children, className = '', speed = 5 }) {
  const reduced = useReducedMotion();
  return (
    <span
      className={`sc-shiny ${reduced ? 'is-static' : ''} ${className}`.trim()}
      style={{ '--shiny-duration': `${speed}s` }}
    >
      {children}
    </span>
  );
}
