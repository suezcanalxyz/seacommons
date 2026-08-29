/** Same production hostname mapping as the console's guessApiBase() in ../main.jsx,
 * kept as a small standalone copy here because the marketing site is a separate
 * static bundle that must not pull in the console's auth/state machinery. */
export function resolveSiteApiBase() {
  const envBase = import.meta.env.VITE_API_BASE;
  if (envBase) return envBase.replace(/\/$/, '');
  const { protocol, hostname } = window.location;
  const isLocal = hostname === 'localhost' || hostname === '127.0.0.1';
  if (isLocal) return `${protocol}//${hostname}:8000`;
  return 'https://api.seacommons.org';
}

export const LIVE_HOST_URL = 'https://live.seacommons.org';
