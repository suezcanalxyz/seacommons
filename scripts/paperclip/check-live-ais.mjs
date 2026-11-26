const base = 'https://live.seacommons.org';

async function get(path) {
  const response = await fetch(new URL(path, base), { signal: AbortSignal.timeout(15_000) });
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json();
}

try {
  const feed = await get('/api/v1/live/signals?mode=maritime&limit=100');
  const candidates = new Map();
  for (const { properties } of feed.features ?? []) {
    const mmsi = String(properties?.linked_mmsi ?? properties?.mmsi ?? '');
    if (/^\d{9}$/.test(mmsi)) candidates.set(mmsi, properties?.id ?? null);
    if (candidates.size === 3) break;
  }
  const vessels = [];
  for (const [mmsi, caseId] of candidates) {
    const dossier = await get(`/api/v1/live/vessels/${mmsi}/context?hours=24`);
    vessels.push({
      caseId, mmsi,
      latestFieldPublished: Object.hasOwn(dossier, 'latest_ais_fix'),
      latestAt: dossier.latest_ais_fix?.ts ?? dossier.track_points?.at(-1)?.ts ?? null,
    });
  }
  console.log(JSON.stringify({
    check: 'live-public-ais-api', checkedAt: new Date().toISOString(),
    result: vessels.length ? 'sampled' : 'no-eligible-cases', vessels,
  }));
} catch (error) {
  console.error(JSON.stringify({ check: 'live-public-ais-api', result: 'error', message: error.cause?.message ?? error.message }));
  process.exitCode = 1;
}
