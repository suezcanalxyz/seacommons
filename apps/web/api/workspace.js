import https from 'node:https';

export function workspaceTarget(query, origin) {
  const base = new URL(origin);
  if (base.protocol !== 'https:' || base.username || base.password || base.pathname !== '/' || base.search || base.hash) throw new Error('Invalid origin');
  const path = Array.isArray(query.path) ? query.path[0] : query.path;
  if (!/^(me|records(?:\/[0-9a-f-]{36}(?:\/history)?)?)$/.test(String(path || ''))) throw new Error('Invalid resource');
  const target = new URL(`/api/v1/workspace/${path}`, base);
  for (const key of ['offset', 'limit']) {
    const value = Array.isArray(query[key]) ? query[key][0] : query[key];
    if (value !== undefined && /^\d{1,6}$/.test(String(value))) target.searchParams.set(key, String(value));
  }
  return target;
}

export default function handler(req, res) {
  res.setHeader('cache-control', 'private, no-store');
  res.setHeader('vary', 'Authorization');
  if (!/^Bearer \S+$/i.test(req.headers.authorization || '')) return res.status(401).json({ detail: 'Sign in to continue' });
  if (!process.env.SEACOMMONS_PARTNER_API_ORIGIN) return res.status(503).json({ detail: 'Partner access is not configured' });
  let target;
  try { target = workspaceTarget(req.query || {}, process.env.SEACOMMONS_PARTNER_API_ORIGIN); }
  catch { return res.status(400).json({ detail: 'Invalid workspace request' }); }
  if (!['GET', 'POST', 'PUT'].includes(req.method)) return res.status(405).json({ detail: 'Method not allowed' });
  const upstream = https.request(target, {
    method: req.method,
    headers: { authorization: req.headers.authorization, 'content-type': 'application/json', accept: 'application/json' },
  }, (response) => {
    res.statusCode = response.statusCode || 502;
    res.setHeader('content-type', 'application/json');
    response.pipe(res);
  });
  upstream.setTimeout(15_000, () => upstream.destroy(new Error('Workspace timeout')));
  upstream.on('error', () => {
    if (res.headersSent) res.destroy();
    else res.status(502).json({ detail: 'Partner workspace unavailable' });
  });
  req.pipe(upstream);
}

export const config = { api: { bodyParser: false }, maxDuration: 20 };
