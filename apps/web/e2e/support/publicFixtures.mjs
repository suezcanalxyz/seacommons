export const PUBLIC_LIVE_URL = 'http://live.seacommons.org:4173/';
export const PUBLIC_PLAY_URL = 'http://play.seacommons.org:4173/play.html';

const ONE_PIXEL_PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZQmcAAAAASUVORK5CYII=',
  'base64',
);

const humanitarianFeature = {
  type: 'Feature',
  geometry: { type: 'Point', coordinates: [14.2, 35.4] },
  properties: {
    id: 'humanitarian-1',
    type: 'distress',
    kind: 'distress',
    source: 'Alarm Phone',
    title: 'Distress report',
    humanitarian_case_type: 'distress',
    origin_category: 'humanitarian_alarm_phone',
    incident_lifecycle: 'active',
    observed_at: '2026-09-08T12:00:00Z',
  },
};

const maritimeFeature = {
  type: 'Feature',
  geometry: { type: 'Point', coordinates: [15.4, 36.0] },
  properties: {
    id: 'maritime-1',
    type: 'vessel_incident',
    kind: 'vessel_incident',
    source: 'AIS safety',
    title: 'Not under command report',
    maritime_domain: 'safety',
    navigation_status: 'not_under_command',
    observed_at: '2026-09-08T12:05:00Z',
  },
};

export const livePipelineFixture = {
  sources: [
    { family: 'ais', label: 'AIS', state: 'live', mode: 'legacy' },
    { family: 'first_party', label: 'First-party', state: 'live' },
    { family: 'partner', label: 'Partner', state: 'degraded' },
    { family: 'public_feed', label: 'Public feed', state: 'live' },
    {
      family: 'radio', label: 'Radio', state: 'live', receivers: [{
        receiver_id: 'rx-eligible', station_label: 'Mediterranean DSC', provider: 'kiwisdr',
        state: 'connected', channel_kind: 'dsc', frequency_hz: 2187500, mode: 'usb',
        last_observation_at: '2026-09-08T12:06:00Z', observations_received: 12,
      }],
    },
  ],
};

export const receiverMeshFixture = {
  catalogued: 2,
  reachable: 2,
  eligible: 2,
  active: 1,
  receivers: [
    {
      receiver_id: 'rx-eligible', station_label: 'Mediterranean DSC', provider: 'kiwisdr',
      network_family: 'public', country: 'IT', state: 'connected', active: true,
      listen_available: true, frequency_hz: 2187500, mode: 'usb',
      latitude: 36.1, longitude: 15.2, score: 91,
      capabilities: [{ min_hz: 2100000, max_hz: 2200000 }],
    },
    {
      receiver_id: 'rx-unavailable', station_label: 'Standby NAVTEX', provider: 'openwebrx',
      network_family: 'public', country: 'MT', state: 'catalogued', active: false,
      listen_available: false, frequency_hz: 518000, mode: 'usb',
      latitude: 35.9, longitude: 14.5, score: 76,
      capabilities: [{ min_hz: 500000, max_hz: 530000 }],
    },
  ],
};

const playIncidents = [
  {
    incident_id: 'play-humanitarian-1', title: 'Historical distress', domain: 'humanitarian',
    source: 'Alarm Phone', case_type: 'distress', incident_status: 'resolved',
    reported_at: '2026-09-05T10:00:00Z', geometry: { type: 'Point', coordinates: [14.1, 35.2] },
  },
  {
    incident_id: 'play-maritime-1', title: 'Historical safety report', domain: 'maritime',
    source: 'AIS', case_type: 'vessel_incident', incident_status: 'outcome_unknown',
    reported_at: '2026-09-06T11:00:00Z', geometry: { type: 'Point', coordinates: [15.1, 36.0] },
  },
  {
    incident_id: 'play-correlated-1', title: 'Reviewed correlated case', domain: 'maritime',
    source: 'SeaCommons', case_type: 'correlated_alert', incident_status: 'needs_review',
    reported_at: '2026-09-07T12:00:00Z', geometry: { type: 'Point', coordinates: [16.0, 35.8] },
  },
];

function signalPayload(mode) {
  const features = mode === 'humanitarian'
    ? [humanitarianFeature]
    : mode === 'maritime'
      ? [maritimeFeature]
      : [humanitarianFeature, maritimeFeature];
  return {
    type: 'FeatureCollection',
    features,
    meta: { mode_counts: { humanitarian: 1, maritime: 1 } },
  };
}

function timelinePayload(incidentId) {
  const incident = playIncidents.find((item) => item.incident_id === incidentId) || playIncidents[0];
  return {
    incident,
    timeline: [{
      id: `${incident.incident_id}:report`, type: 'report', at: incident.reported_at,
      title: incident.title, source: incident.source, geometry: incident.geometry,
      properties: {},
    }],
  };
}
async function fulfillJson(route, payload, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(payload),
  });
}

function apiPayload(url) {
  const { pathname, searchParams } = url;
  if (pathname === '/api/v1/live/signals') return signalPayload(searchParams.get('mode') || 'all');
  if (pathname === '/api/v1/live/pipeline') return livePipelineFixture;
  if (pathname === '/api/v1/live/receivers/mesh') return receiverMeshFixture;
  if (pathname === '/api/v1/live/radio/events') return { events: [] };
  if (pathname === '/api/v1/live/radio/messages') return { messages: [] };
  if (pathname === '/api/v1/live/drifts') return { type: 'FeatureCollection', features: [] };
  if (pathname === '/api/v1/live/platforms') return { type: 'FeatureCollection', features: [] };
  if (pathname === '/api/v1/live/ngo-vessels') return { type: 'FeatureCollection', features: [] };
  if (pathname === '/api/v1/play/counts') return { total_count: playIncidents.length };
  if (pathname === '/api/v1/play/incidents') return { incidents: playIncidents, next_offset: null };
  if (pathname.startsWith('/api/v1/play/incidents/') && pathname.endsWith('/timeline')) {
    const incidentId = decodeURIComponent(pathname.slice('/api/v1/play/incidents/'.length, -'/timeline'.length));
    return timelinePayload(incidentId);
  }
  return {};
}

export async function installDeterministicRoutes(page) {
  await page.route('**/api/v1/**', async (route) => {
    await fulfillJson(route, apiPayload(new URL(route.request().url())));
  });

  for (const pattern of [
    'https://a.tile.openstreetmap.org/**',
    'https://server.arcgisonline.com/**',
    'https://gibs.earthdata.nasa.gov/**',
    'https://api.maptiler.com/**',
  ]) {
    await page.route(pattern, async (route) => {
      await route.fulfill({ status: 200, contentType: 'image/png', body: ONE_PIXEL_PNG });
    });
  }
}
