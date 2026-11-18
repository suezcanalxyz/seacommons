// Read-only NAVAREA III notices, published by Navtex Online.
// CDN cache protects the upstream request budget; no first-party RF/DSC evidence is created.
const UPSTREAM = 'https://navtex.online/api/v1/messages?navarea=III&limit=50';
const CACHE_MS = 180_000;
let lastAttempt = 0;
let lastGood = null;
let pending = null;

function normalize(raw) {
  if (!raw || (typeof raw.id !== 'string' && typeof raw.id !== 'number')) return null;
  const id = String(raw.id);
  if (!/^[A-Za-z0-9_-]{1,80}$/.test(id)) return null;
  const station = raw.station && typeof raw.station === 'object' ? raw.station : {};
  const plain = raw.plain && typeof raw.plain === 'object' ? raw.plain : {};
  return {
    external_id: id,
    source: 'navtex_online',
    source_class: 'secondary_maritime_safety_information',
    independent_rf_reception: false,
    is_dsc_decode: false,
    station_id: typeof station.id === 'string' ? station.id.slice(0, 100) : null,
    navarea: typeof station.navarea === 'string' ? station.navarea : null,
    first_seen: raw.firstSeen || null,
    last_seen: raw.lastSeen || null,
    status: typeof raw.status === 'string' ? raw.status : 'unknown',
    original_text: typeof raw.text === 'string' ? raw.text.slice(0, 20000)
      : typeof plain.text === 'string' ? plain.text.slice(0, 20000) : null,
    original_url: 'https://navtex.online/messages/' + encodeURIComponent(id),
  };
}

export function projectNavtexPayload(payload) {
  if (!payload || !Array.isArray(payload.messages)) throw new Error('Invalid NAVTEX payload');
  const byId = new Map();
  for (const sourceRow of payload.messages.slice(0, 50)) {
    const row = normalize(sourceRow);
    if (row && row.navarea === 'III') byId.set(row.external_id, row);
  }
  return {
    source: 'navtex_online',
    source_class: 'secondary_maritime_safety_information',
    independent_rf_reception: false,
    scope: 'NAVAREA_III',
    upstream: 'https://navtex.online/feeds',
    warning: 'Published secondary NAVTEX copies, not first-party RF reception or navigational advice.',
    messages: [...byId.values()],
  };
}

async function getSnapshot() {
  const now = Date.now();
  if (lastGood && now - lastAttempt < CACHE_MS) return lastGood;
  if (pending) return pending;
  if (now - lastAttempt < CACHE_MS && !lastGood) return null;
  lastAttempt = now;
  pending = (async () => {
    const response = await fetch(UPSTREAM, {
      headers: { accept: 'application/json', 'user-agent': 'SeaCommons/1.0 external-NAVTEX-context' },
      signal: AbortSignal.timeout(8500),
    });
    if (!response.ok) throw new Error('NAVTEX provider unavailable');
    const parsed = projectNavtexPayload(await response.json());
    lastGood = { ...parsed, fetched_at: new Date().toISOString(), state: 'live' };
    return lastGood;
  })();
  try {
    return await pending;
  } catch {
    return lastGood ? { ...lastGood, state: 'degraded' } : null;
  } finally {
    pending = null;
  }
}

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    res.setHeader('allow', 'GET');
    return res.status(405).json({ detail: 'Method not allowed' });
  }
  const snapshot = await getSnapshot();
  if (!snapshot) {
    res.setHeader('cache-control', 'no-store');
    return res.status(503).json({
      source: 'navtex_online', state: 'unavailable', messages: [], independent_rf_reception: false,
    });
  }
  res.setHeader('cache-control', 'public, max-age=0, must-revalidate');
  res.setHeader('cdn-cache-control', 'public, s-maxage=180, stale-while-revalidate=60');
  res.setHeader('x-seacommons-source-class', 'secondary-maritime-safety');
  return res.status(200).json(snapshot);
}
