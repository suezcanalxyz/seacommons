/** The marketing site is always served at the main domain (vercel.json routes
 * console/live/play/engine subdomains to console.html instead), so in
 * production it must hit its OWN origin — vercel.json rewrites
 * /api/v1/live/* to the serverless proxy there. api.seacommons.org is a
 * separate host used only by the console and is not guaranteed to be up;
 * pointing the site at it was a bug (verified: TCP connect times out there,
 * while seacommons.org/api/v1/live/signals returns 200 through the rewrite). */
export function resolveSiteApiBase() {
  const envBase = import.meta.env.VITE_API_BASE;
  if (envBase) return envBase.replace(/\/$/, '');
  const { protocol, hostname, origin } = window.location;
  const isLocal = hostname === 'localhost' || hostname === '127.0.0.1';
  if (isLocal) return `${protocol}//${hostname}:8000`;
  return origin;
}

export const LIVE_HOST_URL = 'https://live.seacommons.org';
