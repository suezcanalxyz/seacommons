// Shared motion utilities for the SeaCommons UI.
//
// Every animated primitive in src/ui routes through here so that a single
// switch — the OS "reduce motion" setting — disables transforms, WebGL and
// timed reveals across both the institutional site and the operator console.
// Animations must never be load-bearing: content is always present in the DOM
// at full opacity by default, and the reveal only *delays* it.

import { useEffect, useRef, useState } from 'react';

const REDUCE_QUERY = '(prefers-reduced-motion: reduce)';

export function prefersReducedMotion() {
  if (typeof window === 'undefined' || !window.matchMedia) return false;
  return window.matchMedia(REDUCE_QUERY).matches;
}

/** Live-updating reduced-motion flag. */
export function useReducedMotion() {
  const [reduced, setReduced] = useState(prefersReducedMotion);
  useEffect(() => {
    if (!window.matchMedia) return undefined;
    const mq = window.matchMedia(REDUCE_QUERY);
    const onChange = () => setReduced(mq.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);
  return reduced;
}

/**
 * Fires once when `ref` first enters the viewport. Returns a boolean.
 * `rootMargin` lets a reveal start slightly before the element is on screen.
 */
export function useInView(ref, { rootMargin = '0px 0px -10% 0px', threshold = 0.12, once = true } = {}) {
  const [inView, setInView] = useState(false);
  const done = useRef(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || (once && done.current)) return undefined;
    if (typeof IntersectionObserver === 'undefined') {
      setInView(true);
      return undefined;
    }
    // If the element is already at or above the fold when we mount — deep link,
    // fast scroll before hydration, or simply content above the first screen —
    // reveal it now. IntersectionObserver only fires on *crossings*, so an
    // element scrolled past before the observer attached would stay hidden.
    const rect = el.getBoundingClientRect();
    if (rect.top < (window.innerHeight || 0) * 0.92) {
      setInView(true);
      done.current = true;
      if (once) return undefined;
    }
    const io = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setInView(true);
            if (once) {
              done.current = true;
              io.disconnect();
            }
          } else if (!once) {
            setInView(false);
          }
        }
      },
      { rootMargin, threshold },
    );
    io.observe(el);

    // A tab opened in the background throttles IntersectionObserver; when it
    // finally becomes visible, re-check so nothing stays stuck hidden.
    const onVisible = () => {
      if (document.visibilityState !== 'visible' || done.current) return;
      const r = el.getBoundingClientRect();
      if (r.top < (window.innerHeight || 0) && r.bottom > 0) {
        setInView(true);
        done.current = true;
        io.disconnect();
      }
    };
    document.addEventListener('visibilitychange', onVisible);

    return () => {
      io.disconnect();
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [ref, rootMargin, threshold, once]);
  return inView;
}

/** True when the pointer is a real mouse — gate magnetic / tilt effects. */
export function hasFinePointer() {
  if (typeof window === 'undefined' || !window.matchMedia) return false;
  return window.matchMedia('(pointer: fine)').matches;
}
