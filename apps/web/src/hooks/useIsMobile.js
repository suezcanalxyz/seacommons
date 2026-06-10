import { useEffect, useState } from 'react';

const MOBILE_QUERY = '(max-width: 680px)';

/**
 * Reactive mobile breakpoint hook.
 * Mirrors the `@media (max-width: 680px)` breakpoint in styles.css so JS layout
 * decisions (bottom nav vs sidebar toggle) stay in sync with the CSS.
 */
export default function useIsMobile() {
  const [isMobile, setIsMobile] = useState(
    () => window.matchMedia(MOBILE_QUERY).matches,
  );

  useEffect(() => {
    const mql = window.matchMedia(MOBILE_QUERY);
    const onChange = (e) => setIsMobile(e.matches);
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, []);

  return isMobile;
}
