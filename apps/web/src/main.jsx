import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';
import MapFloatingPanel from './components/ConePanel.jsx';
import ScenarioModal from './components/ScenarioModal.jsx';
import SimHistory from './components/SimHistory.jsx';
import IntelDashboard from './components/IntelDashboard.jsx';

function enrichCaseGeo(geojson, lat, lon) {
  return {
    ...geojson,
    features: [
      ...geojson.features,
      {
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [Number(lon), Number(lat)] },
        properties: { type: 'origin_point' },
      },
    ],
  };
}

function guessApiBase() {
  const envBase = import.meta.env.VITE_API_BASE;
  if (envBase) return envBase.replace(/\/$/, '');
  const { protocol, hostname, port, origin } = window.location;
  const isLocal = hostname === 'localhost' || hostname === '127.0.0.1'
    || port === '3000' || port === '5173' || port === '4173';
  if (isLocal) {
    const saved = window.localStorage.getItem('seacommons_api_base');
    if (saved) return saved.replace(/\/$/, '');
    return `${protocol}//${hostname}:8000`;
  }
  // In production always use origin — API is proxied via Vercel rewrites.
  // Ignore any stale localStorage entry that may point to a dead backend.
  return origin;
}

function loadLocalSettings() {
  return {
    timezeroHost: window.localStorage.getItem('seacommons_tz_host') || 'localhost',
    timezeroPort: window.localStorage.getItem('seacommons_tz_port') || '4371',
    timezeroEnabled: window.localStorage.getItem('seacommons_tz_enabled') || 'false',
  };
}

function apiUrl(base, path) {
  return `${base.replace(/\/$/, '')}${path}`;
}

async function fetchJson(base, path, options, timeoutMs = 12000) {
  const controller = new AbortController();
  const timer = window.setTimeout(
    () => controller.abort(new DOMException(`Request timeout: ${path}`, 'TimeoutError')),
    timeoutMs,
  );
  try {
    const response = await fetch(apiUrl(base, path), { signal: controller.signal, ...options });
    if (!response.ok) {
      const text = await response.text().catch(() => '');
      throw new Error(text || `HTTP ${response.status}`);
    }
    return response.json();
  } finally {
    window.clearTimeout(timer);
  }
}

function Pill({ label, tone = 'default' }) {
  return <span className={`pill tone-${tone}`}>{label}</span>;
}

const VESSEL_TYPES = [
  { value: 'rubber_boat',     label: 'Rubber boat' },
  { value: 'life_raft',       label: 'Life raft' },
  { value: 'fishing_vessel',  label: 'Fishing vessel' },
  { value: 'wooden_boat',     label: 'Wooden boat' },
  { value: 'sailboat',        label: 'Sailboat' },
  { value: 'motorboat',       label: 'Motorboat' },
  { value: 'container_ship',  label: 'Cargo / container' },
  { value: 'unknown',         label: 'Unknown' },
];

const RISK_LEVELS = [
  { value: 'high',   label: 'High' },
  { value: 'medium', label: 'Medium' },
  { value: 'low',    label: 'Low' },
];

const MAPTILER_KEY = import.meta.env.VITE_MAPTILER_KEY;
const OWM_KEY = import.meta.env.VITE_OWM_KEY;

function mapStyle() {
  if (MAPTILER_KEY) {
    return `https://api.maptiler.com/maps/hybrid/style.json?key=${MAPTILER_KEY}`;
  }
  return {
    version: 8,
    sources: {
      osm: {
        type: 'raster',
        tiles: ['https://a.tile.openstreetmap.org/{z}/{x}/{y}.png'],
        tileSize: 256,
        attribution: '&copy; OpenStreetMap contributors',
      },
    },
    layers: [{ id: 'osm', type: 'raster', source: 'osm' }],
  };
}

function weatherGridToVectors(featureCollection) {
  const features = (featureCollection?.features || []).map((feature) => {
    const [lon, lat] = feature.geometry.coordinates;
    const speed = Number(feature.properties.wind_speed_ms || 0);
    const dirDeg = Number(feature.properties.wind_dir_deg || 0);
    const theta = (dirDeg * Math.PI) / 180;
    const vectorScale = Math.max(0.12, Math.min(0.36, 0.08 + speed * 0.018));
    const endLon = lon + vectorScale * Math.sin(theta);
    const endLat = lat + vectorScale * Math.cos(theta);
    return {
      type: 'Feature',
      geometry: { type: 'LineString', coordinates: [[lon, lat], [endLon, endLat]] },
      properties: { ...feature.properties },
    };
  });
  return { type: 'FeatureCollection', features };
}

function formatDistance(vessel) {
  if (!vessel) return '—';
  return `${vessel.distance_nm.toFixed(1)} nm`;
}

function vesselTone(vessel) {
  if (!vessel) return 'default';
  if ((vessel.type || '').toString().toUpperCase() === 'SAR') return 'ok';
  return 'info';
}

/** Build GeoJSON for proximity rendering: circles at vessel positions + lines from distress. */
function buildProximityGeojson(vessels, distressLat, distressLon) {
  if (!vessels.length || !Number.isFinite(distressLat) || !Number.isFinite(distressLon)) {
    return {
      vessels: { type: 'FeatureCollection', features: [] },
      lines:   { type: 'FeatureCollection', features: [] },
    };
  }
  const vesselFeatures = vessels.map((v, idx) => ({
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [v.lon, v.lat] },
    properties: {
      mmsi: v.mmsi,
      ship_name: v.ship_name,
      type: v.type,
      distance_nm: v.distance_nm,
      rank: idx + 1,
    },
  }));
  const lineFeatures = vessels.map((v) => ({
    type: 'Feature',
    geometry: {
      type: 'LineString',
      coordinates: [[distressLon, distressLat], [v.lon, v.lat]],
    },
    properties: { ship_name: v.ship_name, distance_nm: v.distance_nm },
  }));
  return {
    vessels: { type: 'FeatureCollection', features: vesselFeatures },
    lines:   { type: 'FeatureCollection', features: lineFeatures },
  };
}

function createVesselArrowImage(size = 48) {
  const canvas = document.createElement('canvas');
  canvas.width = size; canvas.height = size;
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, size, size);
  ctx.fillStyle = '#ffffff';
  const cx = size / 2;
  ctx.beginPath();
  ctx.moveTo(cx, 3);
  ctx.lineTo(size - 6, size - 4);
  ctx.lineTo(cx, size - 11);
  ctx.lineTo(6, size - 4);
  ctx.closePath();
  ctx.fill();
  const idata = ctx.getImageData(0, 0, size, size);
  return { width: size, height: size, data: new Uint8Array(idata.data.buffer) };
}

function App() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [activePanel, setActivePanel] = useState('sim');
  const [apiBase, setApiBase] = useState(guessApiBase);
  const [localSettings, setLocalSettings] = useState(loadLocalSettings);
  const [summary, setSummary] = useState(null);
  const [stats, setStats] = useState(null);
  const [vessels, setVessels] = useState({ type: 'FeatureCollection', features: [] });
  const [ngoVessels, setNgoVessels] = useState({ type: 'FeatureCollection', features: [] });
  const [platforms, setPlatforms] = useState({ type: 'FeatureCollection', features: [] });
  const [alerts, setAlerts] = useState({ type: 'FeatureCollection', features: [] });
  const [caseGeojson, setCaseGeojson] = useState({ type: 'FeatureCollection', features: [] });
  const [weather, setWeather] = useState(null);
  const [weatherGrid, setWeatherGrid] = useState({ type: 'FeatureCollection', features: [] });
  const [weatherVectors, setWeatherVectors] = useState({ type: 'FeatureCollection', features: [] });
  const [timezero, setTimezero] = useState(null);
  const [selectedVessel, setSelectedVessel] = useState(null);
  const [nearestVessels, setNearestVessels] = useState([]);
  const [mapReady, setMapReady] = useState(false);
  const [selectionMode, setSelectionMode] = useState(false);
  const [cursorHint, setCursorHint] = useState({ visible: false, x: 0, y: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [caseStatus, setCaseStatus] = useState('idle');
  const [caseLog, setCaseLog] = useState([]);
  const [mapPanel, setMapPanel] = useState(null);
  const [showScenario, setShowScenario] = useState(false);
  const [scenarioType, setScenarioType] = useState('distress');
  const [caseEventId, setCaseEventId] = useState(null);
  const [simHistory, setSimHistory] = useState([]);   // session-only: cleared on page refresh
  const [activeSimId, setActiveSimId] = useState(null);
  const [intelEvents, setIntelEvents] = useState(() => {
    try {
      const cached = window.localStorage.getItem('seacommons_intel_cache');
      if (cached) {
        const cutoff = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString();
        const parsed = JSON.parse(cached);
        return parsed.filter(e => (e.properties?.timestamp_utc || '') >= cutoff);
      }
    } catch { /* ignore */ }
    return [];
  });
  const [intelDrifts, setIntelDrifts] = useState({ type: 'FeatureCollection', features: [] });
  const [intelConnected, setIntelConnected] = useState(false);
  const [intelMode, setIntelMode] = useState('offline'); // 'ws' | 'poll' | 'offline'
  const [intelFilter, setIntelFilter] = useState('all');
  const [showAisAlerts, setShowAisAlerts] = useState(false);
  const [showVesselLinks, setShowVesselLinks] = useState(false);
  const [triggeringDrift, setTriggeringDrift] = useState(() => new Set());
  const caseEventIdRef = useRef(null);
  const caseStatusRef = useRef('idle');
  const simParamsRef = useRef({});
  const intelWsRef = useRef(null);
  const [form, setForm] = useState({
    lat: '',
    lon: '',
    persons: '1',
    vessel_type: 'rubber_boat',
    risk_level: 'high',
  });

  const mapNodeRef = useRef(null);
  const mapRef = useRef(null);
  const selectionModeRef = useRef(false);
  const activePanelRef = useRef('sim');

  const selectedLat = parseFloat(form.lat);
  const selectedLon = parseFloat(form.lon);

  function pushCaseLog(message) {
    setCaseLog((cur) => [
      { id: `${Date.now()}-${Math.random()}`, message, at: new Date().toISOString() },
      ...cur,
    ].slice(0, 20));
  }

  async function loadWeatherFor(lat, lon) {
    const payload = await fetchJson(
      apiBase,
      `/api/v1/weather?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}`,
    );
    setWeather(payload);
    pushCaseLog(`Weather ${payload.source} @ ${Number(lat).toFixed(3)}, ${Number(lon).toFixed(3)}`);
    return payload;
  }

  async function loadWeatherGridForMap(map) {
    const bounds = map.getBounds();
    const payload = await fetchJson(
      apiBase,
      `/api/v1/weather/grid?lat_min=${bounds.getSouth().toFixed(3)}&lat_max=${bounds.getNorth().toFixed(3)}&lon_min=${bounds.getWest().toFixed(3)}&lon_max=${bounds.getEast().toFixed(3)}&n=6`,
    );
    setWeatherGrid(payload);
    setWeatherVectors(weatherGridToVectors(payload));
  }

  async function triggerIntelDrift(eventId, lat, lon) {
    setTriggeringDrift((prev) => new Set([...prev, eventId]));
    try {
      await fetchJson(apiBase, '/api/v1/intel/auto-drift', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ intel_event_id: eventId, lat, lon, vessel_type: 'rubber_boat' }),
      }, 8000);
      setIntelEvents((prev) => prev.map((f) =>
        f.properties?.id === eventId
          ? { ...f, properties: { ...f.properties, drift_status: 'computing' } }
          : f
      ));
    } catch (err) {
      setTriggeringDrift((prev) => { const n = new Set(prev); n.delete(eventId); return n; });
    }
  }

  async function loadNearestVessels(lat, lon) {
    if (!Number.isFinite(Number(lat)) || !Number.isFinite(Number(lon))) return [];
    const payload = await fetchJson(
      apiBase,
      `/api/v1/vessels/nearest?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}&limit=5`,
    );
    setNearestVessels(payload.vessels || []);
    return payload.vessels || [];
  }

  useEffect(() => {
    window.localStorage.setItem('seacommons_api_base', apiBase);
  }, [apiBase]);

  useEffect(() => {
    selectionModeRef.current = selectionMode;
  }, [selectionMode]);

  useEffect(() => {
    activePanelRef.current = activePanel;
  }, [activePanel]);

  useEffect(() => {
    caseEventIdRef.current = caseEventId;
  }, [caseEventId]);

  useEffect(() => {
    caseStatusRef.current = caseStatus;
  }, [caseStatus]);

  // ── Intel feed: REST polling always-on + WS upgrade when available ───────────
  // Vercel does NOT proxy WebSocket connections, so wss://seacommons.suezcanal.xyz
  // always fails in production. We start REST polling immediately so data flows
  // on first load, and attempt WS in parallel — if it connects (direct backend /
  // dev) it takes over; if it fails we just keep polling.
  useEffect(() => {
    const wsBase = apiBase.replace(/^http/, 'ws');
    let ws = null;
    let reconnectTimer = null;
    let pollTimer = null;
    let wsAlive = true;   // false once we give up on WS
    let polling = false;
    let alive = true;

    function handleWsMessage(e) {
      try {
        const msg = JSON.parse(e.data);
        if (msg.type === 'ping') return;
        if (msg.type === 'snapshot') {
          setIntelEvents(msg.features || []);
        } else if (msg.type === 'Feature') {
          setIntelEvents((prev) => [msg, ...prev].slice(0, 300));
          const mp = msg.properties || {};
          if (mp.type === 'distress' && ['critical', 'high'].includes(mp.severity)) {
            setActivePanel('osint');
            setSidebarOpen(true);
          }
        } else if (msg.type === 'event_update' && msg.drift?.trajectory) {
          setIntelDrifts((prev) => {
            const keep = prev.features.filter(f => f.properties?.intel_event_id !== msg.id);
            const d = msg.drift;
            const newFeats = [d.trajectory, d.cone_24h].filter(Boolean).map(f => ({
              ...f,
              properties: { ...f.properties, intel_event_id: msg.id,
                intel_title: d.title, intel_severity: d.severity, intel_source: d.source, auto_drift: true },
            }));
            if (d.impact_point?.features) {
              d.impact_point.features.forEach(f => newFeats.push({
                ...f, properties: { ...f.properties, intel_event_id: msg.id, auto_drift: true },
              }));
            }
            return { type: 'FeatureCollection', features: [...keep, ...newFeats] };
          });
        }
      } catch { /* ignore malformed */ }
    }

    async function pollOnce() {
      try {
        const data = await fetchJson(apiBase, '/api/v1/intel?limit=200&days=30');
        if (!alive) return;
        if (data.features) {
          setIntelEvents(data.features);
          try { window.localStorage.setItem('seacommons_intel_cache', JSON.stringify(data.features)); } catch { /* quota */ }
          setIntelConnected(true);
          // only set 'poll' if WS hasn't taken over
          setIntelMode((prev) => prev === 'ws' ? 'ws' : 'poll');
        }
      } catch {
        if (!alive) return;
        setIntelConnected(false);
        setIntelMode((prev) => prev === 'ws' ? 'ws' : 'offline');
      }
    }

    async function pollLoop() {
      if (!alive || polling) return;
      polling = true;
      while (alive) {
        await pollOnce();
        if (!alive) break;
        await new Promise((res) => { pollTimer = window.setTimeout(res, 30000); });
      }
      polling = false;
    }

    function tryWs() {
      if (!alive || !wsAlive) return;
      ws = new WebSocket(`${wsBase}/ws/intel`);
      intelWsRef.current = ws;

      const openTimer = window.setTimeout(() => {
        if (ws && ws.readyState !== WebSocket.OPEN) ws.close();
      }, 4000);

      ws.onopen = () => {
        window.clearTimeout(openTimer);
        setIntelConnected(true);
        setIntelMode('ws');
      };
      ws.onclose = () => {
        window.clearTimeout(openTimer);
        if (!alive) return;
        // WS failed — stop trying; polling already covers the feed
        wsAlive = false;
      };
      ws.onerror = () => { window.clearTimeout(openTimer); ws?.close(); };
      ws.onmessage = handleWsMessage;
    }

    // Start REST polling immediately — data on first load regardless of WS
    pollLoop();
    // Only try WebSocket for a direct backend (localhost, LAN IP, raw public IP).
    // When apiBase === window.location.origin the frontend is served via a CDN
    // rewrite (e.g. Vercel) which cannot proxy WebSocket upgrades — skip to avoid
    // the WS failed console error on every page load.
    const apiHost = apiBase.replace(/^https?:\/\//, '').split('/')[0];
    const isDirectBackend = /^(localhost|127\.|192\.168\.|10\.|172\.(1[6-9]|2\d|3[01])\.)/.test(apiHost)
      || /^\d+\.\d+\.\d+\.\d+(:\d+)?$/.test(apiHost);
    if (isDirectBackend) tryWs();

    return () => {
      alive = false;
      wsAlive = false;
      window.clearTimeout(reconnectTimer);
      window.clearTimeout(pollTimer);
      ws?.close();
    };
  }, [apiBase]);

  // ── Intel drift traces polling ───────────────────────────────────────────────
  useEffect(() => {
    let alive = true;
    async function loadDrifts() {
      try {
        const data = await fetchJson(apiBase, '/api/v1/intel/drifts');
        if (alive && data.features) setIntelDrifts(data);
      } catch { /* ignore */ }
      if (alive) window.setTimeout(loadDrifts, 120_000);
    }
    loadDrifts();
    return () => { alive = false; };
  }, [apiBase]);

  useEffect(() => {
    fetchJson(apiBase, '/api/v1/zones/platforms')
      .then(d => { if (d.features) setPlatforms(d); })
      .catch(() => {});
  }, [apiBase]);

  useEffect(() => {
    let alive = true;
    async function loadNgoVessels() {
      try {
        const data = await fetchJson(apiBase, '/api/v1/intel/ngo');
        if (alive && data.features) {
          // Only keep positioned vessels (geometry != null)
          const positioned = { ...data, features: data.features.filter((f) => f.geometry?.coordinates) };
          setNgoVessels(positioned);
        }
      } catch { /* ignore */ }
      if (alive) window.setTimeout(loadNgoVessels, 120_000);
    }
    loadNgoVessels();
    return () => { alive = false; };
  }, [apiBase]);

  useEffect(() => {
    window.localStorage.setItem('seacommons_tz_host', localSettings.timezeroHost);
    window.localStorage.setItem('seacommons_tz_port', localSettings.timezeroPort);
    window.localStorage.setItem('seacommons_tz_enabled', localSettings.timezeroEnabled);
  }, [localSettings]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    map.getCanvas().style.cursor = (activePanel === 'sim' || selectionMode) ? 'crosshair' : '';
  }, [activePanel, selectionMode, mapReady]);

  // ── Map init ────────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!mapNodeRef.current || mapRef.current) return;
    let disposed = false;
    let liveMap = null;

    async function initMap() {
      await import('maplibre-gl/dist/maplibre-gl.css');
      const { default: maplibregl } = await import('maplibre-gl');
      if (disposed || mapRef.current) return;

      const map = new maplibregl.Map({
        container: mapNodeRef.current,
        style: mapStyle(),
        center: [14.3, 35.8],
        zoom: 6.5,
        attributionControl: true,
      });

      liveMap = map;

      let weatherTimer = null;
      map.on('moveend', () => {
        window.clearTimeout(weatherTimer);
        weatherTimer = window.setTimeout(() => {
          loadWeatherGridForMap(map).catch((err) => setError(err.message || 'Weather grid unavailable'));
        }, 220);
      });

      map.on('load', () => {
        // Register vessel arrow SDF icon
        map.addImage('vessel-arrow', createVesselArrowImage(48), { sdf: true });

        // sources
        map.addSource('weather-points',    { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        map.addSource('weather-vectors',   { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        map.addSource('vessels',           { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        map.addSource('vessels-ngo',       { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        map.addSource('platforms',         { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        map.addSource('alerts',            { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        map.addSource('sar-case',          { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        map.addSource('proximity-lines',   { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        map.addSource('proximity-vessels', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        map.addSource('intel-events',      { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        map.addSource('intel-drifts',      { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        map.addSource('intel-vessel-links', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });

        // weather vectors
        map.addLayer({
          id: 'weather-vectors', type: 'line', source: 'weather-vectors',
          paint: {
            'line-color': ['interpolate', ['linear'], ['get', 'beaufort'],
              0, '#7dd3fc', 4, '#22c55e', 7, '#f59e0b', 10, '#ef4444'],
            'line-width': 2, 'line-opacity': 0.68,
          },
        });
        map.addLayer({
          id: 'weather-points', type: 'circle', source: 'weather-points',
          paint: {
            'circle-radius': 3.5, 'circle-opacity': 0.9,
            'circle-color': ['interpolate', ['linear'], ['get', 'beaufort'],
              0, '#7dd3fc', 4, '#22c55e', 7, '#f59e0b', 10, '#ef4444'],
            'circle-stroke-width': 0.8, 'circle-stroke-color': '#04131a',
          },
        });

        // ── Layer z-order (bottom → top) ─────────────────────────────────────
        // weather → platforms → intel-drift (bg) → alerts → sar-case
        // → proximity → vessels → NGO → intel-drift-points → intel-events → sar-impact

        // Oil/gas platforms — static infrastructure, rendered just above weather
        map.addLayer({
          id: 'platforms-halo', type: 'circle', source: 'platforms',
          paint: {
            'circle-radius': 7,
            'circle-color': ['match', ['get', 'platform_type'],
              'oil', 'rgba(251,146,60,0.20)',
                     'rgba(250,204,21,0.18)'],
            'circle-blur': 0.5,
          },
        });
        map.addLayer({
          id: 'platforms-layer', type: 'circle', source: 'platforms',
          paint: {
            'circle-radius': 4,
            'circle-color': ['match', ['get', 'platform_type'],
              'oil', '#fb923c',
                     '#fbbf24'],
            'circle-opacity': 0.88,
            'circle-stroke-width': 1.5,
            'circle-stroke-color': '#0d1f26',
          },
        });

        // Intel auto-drift background cones & lines (faintest, furthest back)
        map.addLayer({
          id: 'intel-drift-cone', type: 'fill', source: 'intel-drifts',
          filter: ['==', '$type', 'Polygon'],
          paint: {
            'fill-color': ['match', ['get', 'intel_severity'],
              'critical', 'rgba(255,59,59,0.08)',
              'high',     'rgba(255,123,84,0.07)',
                          'rgba(139,240,197,0.05)'],
            'fill-outline-color': ['match', ['get', 'intel_severity'],
              'critical', 'rgba(255,59,59,0.28)',
              'high',     'rgba(255,123,84,0.22)',
                          'rgba(139,240,197,0.18)'],
          },
        });
        map.addLayer({
          id: 'intel-drift-line', type: 'line', source: 'intel-drifts',
          filter: ['==', '$type', 'LineString'],
          paint: {
            'line-color': ['match', ['get', 'intel_severity'],
              'critical', 'rgba(255,59,59,0.55)',
              'high',     'rgba(255,123,84,0.50)',
                          'rgba(139,240,197,0.40)'],
            'line-width': 1.5,
            'line-dasharray': [3, 3],
          },
        });

        // Historical SAR drift cones & trajectories
        map.addLayer({
          id: 'alerts-cone', type: 'fill', source: 'alerts',
          filter: ['==', '$type', 'Polygon'],
          paint: {
            'fill-color': ['match', ['get', 'type'],
              'cone_6h',  'rgba(255,180,60,0.22)',
              'cone_12h', 'rgba(255,120,40,0.17)',
                          'rgba(255,60,30,0.13)'],
            'fill-outline-color': ['match', ['get', 'type'],
              'cone_6h',  'rgba(255,180,60,0.55)',
              'cone_12h', 'rgba(255,120,40,0.45)',
                          'rgba(255,60,30,0.38)'],
          },
        });
        map.addLayer({
          id: 'alerts-layer', type: 'line', source: 'alerts',
          filter: ['==', '$type', 'LineString'],
          paint: { 'line-color': '#ff7b54', 'line-width': 2.5, 'line-opacity': 0.9 },
        });

        // Active SAR case cone & trajectory
        map.addLayer({
          id: 'sar-case-cone', type: 'fill', source: 'sar-case',
          filter: ['==', '$type', 'Polygon'],
          paint: {
            'fill-color': ['match', ['get', 'type'],
              'cone_6h',  'rgba(255,224,109,0.18)',
              'cone_12h', 'rgba(255,180,80,0.14)',
                          'rgba(255,120,60,0.10)'],
            'fill-outline-color': ['match', ['get', 'type'],
              'cone_6h',  'rgba(255,224,109,0.55)',
              'cone_12h', 'rgba(255,180,80,0.45)',
                          'rgba(255,120,60,0.35)'],
          },
        });
        map.addLayer({
          id: 'sar-case-line', type: 'line', source: 'sar-case',
          filter: ['==', '$type', 'LineString'],
          paint: {
            'line-color': '#ff3b3b',
            'line-width': 3,
            'line-opacity': 0.95,
          },
        });
        map.addLayer({
          id: 'sar-case-traj-arrows', type: 'symbol', source: 'sar-case',
          filter: ['all', ['==', '$type', 'LineString'], ['==', ['get', 'type'], 'trajectory']],
          layout: {
            'symbol-placement': 'line',
            'symbol-spacing': 100,
            'icon-image': 'vessel-arrow',
            'icon-size': 0.55,
            'icon-rotation-alignment': 'map',
            'icon-allow-overlap': true,
            'icon-ignore-placement': true,
          },
          paint: { 'icon-color': '#ff3b3b', 'icon-opacity': 1.0 },
        });

        // Proximity: dashed lines from distress to nearest vessels
        map.addLayer({
          id: 'proximity-lines', type: 'line', source: 'proximity-lines',
          paint: {
            'line-color': '#f97316',
            'line-width': 1.5,
            'line-opacity': 0.65,
            'line-dasharray': [4, 5],
          },
        });

        // Proximity: highlighted vessel triangles (orange glow + arrow)
        map.addLayer({
          id: 'proximity-vessels-halo', type: 'circle', source: 'proximity-vessels',
          paint: { 'circle-radius': 14, 'circle-color': 'rgba(249,115,22,0.20)', 'circle-blur': 0.8 },
        });
        map.addLayer({
          id: 'proximity-vessels-layer', type: 'symbol', source: 'proximity-vessels',
          layout: {
            'icon-image': 'vessel-arrow',
            'icon-size': 0.56,
            'icon-rotate': ['coalesce', ['get', 'course'], 0],
            'icon-rotation-alignment': 'map',
            'icon-allow-overlap': true,
            'icon-ignore-placement': true,
          },
          paint: {
            'icon-color': '#f97316',
            'icon-opacity': 1.0,
            'icon-halo-color': '#431407',
            'icon-halo-width': 2.0,
          },
        });

        // AIS vessels — moving: triangle arrow; stationary: dot
        const _movingFilter  = ['>', ['coalesce', ['get', 'speed'], 0], 0.3];
        const _stationFilter = ['<=', ['coalesce', ['get', 'speed'], 0], 0.3];
        map.addLayer({
          id: 'vessels-stationary', type: 'circle', source: 'vessels',
          filter: _stationFilter,
          paint: {
            'circle-radius': ['interpolate', ['linear'], ['zoom'], 5, 3, 10, 5, 14, 7],
            'circle-color': ['match', ['get', 'ais_class'], 'A', '#4a9ebb', '#75f5e2'],
            'circle-opacity': 0.75,
            'circle-stroke-width': 0.8,
            'circle-stroke-color': '#021318',
          },
        });
        map.addLayer({
          id: 'vessels-layer', type: 'symbol', source: 'vessels',
          filter: _movingFilter,
          layout: {
            'icon-image': 'vessel-arrow',
            'icon-size': ['interpolate', ['linear'], ['zoom'], 5, 0.30, 10, 0.50, 14, 0.65],
            'icon-rotate': ['coalesce', ['get', 'course'], 0],
            'icon-rotation-alignment': 'map',
            'icon-allow-overlap': true,
            'icon-ignore-placement': true,
          },
          paint: {
            'icon-color': ['match', ['get', 'ais_class'], 'A', '#4a9ebb', '#75f5e2'],
            'icon-opacity': 0.96,
            'icon-halo-color': '#021318',
            'icon-halo-width': 1.2,
          },
        });

        // NGO / coastguard vessels — bright teal, on top of commercial
        map.addLayer({
          id: 'vessels-ngo-stationary', type: 'circle', source: 'vessels-ngo',
          filter: _stationFilter,
          paint: {
            'circle-radius': ['interpolate', ['linear'], ['zoom'], 5, 4, 10, 6, 14, 8],
            'circle-color': '#00e8c8',
            'circle-opacity': 0.85,
            'circle-stroke-width': 1.2,
            'circle-stroke-color': '#021318',
          },
        });
        map.addLayer({
          id: 'vessels-ngo', type: 'symbol', source: 'vessels-ngo',
          filter: _movingFilter,
          layout: {
            'icon-image': 'vessel-arrow',
            'icon-size': ['interpolate', ['linear'], ['zoom'], 5, 0.36, 10, 0.58, 14, 0.72],
            'icon-rotate': ['coalesce', ['get', 'course'], 0],
            'icon-rotation-alignment': 'map',
            'icon-allow-overlap': true,
            'icon-ignore-placement': true,
          },
          paint: {
            'icon-color': '#00e8c8',
            'icon-opacity': 1.0,
            'icon-halo-color': '#021318',
            'icon-halo-width': 1.8,
          },
        });

        // Intel auto-drift impact points (above vessels)
        map.addLayer({
          id: 'intel-drift-point', type: 'circle', source: 'intel-drifts',
          filter: ['==', '$type', 'Point'],
          paint: {
            'circle-radius': 4,
            'circle-color': ['match', ['get', 'intel_severity'],
              'critical', '#ff3b3b', 'high', '#ff7b54', '#8bf0c5'],
            'circle-opacity': 0.78,
            'circle-stroke-width': 1,
            'circle-stroke-color': '#04131a',
          },
        });

        // Intel → vessel correlation lines (toggled manually via showVesselLinks)
        map.addLayer({
          id: 'intel-vessel-links-layer', type: 'line', source: 'intel-vessel-links',
          layout: { visibility: 'none' },
          paint: {
            'line-color': ['match', ['get', 'severity'],
              'critical', '#ff3b3b', 'high', '#ff7b54', 'medium', '#ffe06d', '#8bf0c5'],
            'line-width': 1.5,
            'line-opacity': 0.7,
            'line-dasharray': [3, 3],
          },
        });

        // Intel event circles — exclude routine AIS loiter alerts from map
        const _noAisFilter = ['!=', ['get', 'type'], 'ais_spike'];
        map.addLayer({
          id: 'intel-events-halo', type: 'circle', source: 'intel-events',
          filter: _noAisFilter,
          paint: {
            'circle-radius': 14,
            'circle-color': ['match', ['get', 'severity'],
              'critical', 'rgba(255,59,59,0.18)',
              'high',     'rgba(255,123,84,0.15)',
              'medium',   'rgba(255,224,109,0.12)',
                          'rgba(139,240,197,0.1)'],
            'circle-blur': 0.8,
          },
        });
        map.addLayer({
          id: 'intel-events-layer', type: 'circle', source: 'intel-events',
          filter: _noAisFilter,
          paint: {
            'circle-radius': 5,
            'circle-color': ['match', ['get', 'severity'],
              'critical', '#ff3b3b',
              'high',     '#ff7b54',
              'medium',   '#ffe07d',
                          '#8bf0c5'],
            'circle-opacity': 0.9,
            'circle-stroke-width': 1.2,
            'circle-stroke-color': '#04131a',
          },
        });

        // Active SAR impact point — topmost layer
        map.addLayer({
          id: 'sar-case-points', type: 'circle', source: 'sar-case',
          filter: ['==', '$type', 'Point'],
          paint: {
            'circle-radius': ['match', ['get', 'type'], 'origin_point', 8, 6],
            'circle-color': ['match', ['get', 'type'], 'origin_point', '#ff3b3b', '#fff4bf'],
            'circle-stroke-width': 2,
            'circle-stroke-color': ['match', ['get', 'type'], 'origin_point', '#ffffff', '#ff7b54'],
          },
        });

        map.on('mouseenter', 'intel-events-layer', () => { map.getCanvas().style.cursor = 'pointer'; });
        map.on('mouseleave', 'intel-events-layer', () => {
          map.getCanvas().style.cursor = (activePanelRef.current === 'sim' || selectionModeRef.current) ? 'crosshair' : '';
        });
        map.on('click', 'intel-events-layer', (event) => {
          const feature = event.features?.[0];
          if (!feature) return;
          const [lon, lat] = feature.geometry.coordinates;
          map.flyTo({ center: [lon, lat], zoom: 9, duration: 800 });
          setActivePanel('osint');
          setSidebarOpen(true);
          event.originalEvent?.stopPropagation?.();
        });
        map.on('mouseenter', 'intel-drift-line', () => { map.getCanvas().style.cursor = 'pointer'; });
        map.on('mouseleave', 'intel-drift-line', () => {
          map.getCanvas().style.cursor = (activePanelRef.current === 'sim' || selectionModeRef.current) ? 'crosshair' : '';
        });

        // vessel click (commercial + NGO share same handler)
        for (const lyr of ['vessels-layer', 'vessels-stationary', 'vessels-ngo', 'vessels-ngo-stationary', 'proximity-vessels-layer']) {
          map.on('mouseenter', lyr, () => { map.getCanvas().style.cursor = 'pointer'; });
          map.on('mouseleave', lyr, () => {
            map.getCanvas().style.cursor = (activePanelRef.current === 'sim' || selectionModeRef.current) ? 'crosshair' : '';
          });
          map.on('click', lyr, (event) => {
            const feature = event.features?.[0];
            if (!feature) return;
            const [lon, lat] = feature.geometry.coordinates;
            setSelectedVessel({ ...feature.properties, lon, lat });
            setSidebarOpen(true);
            event.originalEvent?.stopPropagation?.();
          });
        }

        // Drift cone click
        map.on('mouseenter', 'sar-case-cone', () => { map.getCanvas().style.cursor = 'pointer'; });
        map.on('mouseleave', 'sar-case-cone', () => {
          map.getCanvas().style.cursor = (activePanelRef.current === 'sim' || selectionModeRef.current) ? 'crosshair' : '';
        });
        map.on('click', 'sar-case-cone', (event) => {
          const feature = event.features?.[0];
          if (feature) {
            setMapPanel({ type: 'cone', feature, eventId: caseEventIdRef.current, caseStatus: caseStatusRef.current, simParams: simParamsRef.current });
            event.originalEvent?.stopPropagation?.();
          }
        });
        map.on('mouseenter', 'sar-case-points', () => { map.getCanvas().style.cursor = 'pointer'; });
        map.on('mouseleave', 'sar-case-points', () => {
          map.getCanvas().style.cursor = (activePanelRef.current === 'sim' || selectionModeRef.current) ? 'crosshair' : '';
        });
        map.on('click', 'sar-case-points', (event) => {
          const feature = event.features?.[0];
          if (feature) {
            setMapPanel({ type: 'cone', feature, eventId: caseEventIdRef.current, caseStatus: caseStatusRef.current, simParams: simParamsRef.current });
            event.originalEvent?.stopPropagation?.();
          }
        });

        map.on('mousemove', (event) => {
          if (activePanelRef.current !== 'sim' && !selectionModeRef.current) return;
          setCursorHint({ visible: true, x: event.point.x, y: event.point.y });
        });
        map.on('mouseleave', () => {
          setCursorHint((cur) => ({ ...cur, visible: false }));
        });

        map.on('click', (event) => {
          const hit = map.queryRenderedFeatures(event.point, {
            layers: ['sar-case-cone', 'sar-case-points', 'vessels-layer', 'vessels-stationary', 'vessels-ngo', 'vessels-ngo-stationary', 'proximity-vessels-layer', 'intel-events-layer'],
          });
          if (hit.length > 0) return;

          const nextLat = event.lngLat.lat.toFixed(5);
          const nextLon = event.lngLat.lng.toFixed(5);
          setForm((cur) => ({ ...cur, lat: nextLat, lon: nextLon }));
          setSelectionMode(false);
          setCursorHint({ visible: false, x: 0, y: 0 });
          if (activePanelRef.current === 'sim' || selectionModeRef.current) {
            setShowScenario(true);
            loadNearestVessels(nextLat, nextLon).catch(() => {});
            return;
          }
          loadWeatherFor(nextLat, nextLon).catch((err) => setError(err.message || 'Weather unavailable'));
        });

        map.getSource('weather-points')?.setData(weatherGrid);
        map.getSource('weather-vectors')?.setData(weatherVectors);
        map.getSource('vessels')?.setData(vessels);
        map.getSource('vessels-ngo')?.setData(ngoVessels);
        map.getSource('platforms')?.setData(platforms);
        map.getSource('alerts')?.setData(alerts);

        // Platform hover tooltip
        map.on('mouseenter', 'platforms-layer', (e) => {
          map.getCanvas().style.cursor = 'pointer';
          const p = e.features?.[0]?.properties || {};
          map.getCanvas().title = `${p.name} — ${p.operator} (${p.platform_type})`;
        });
        map.on('mouseleave', 'platforms-layer', () => {
          map.getCanvas().style.cursor = '';
          map.getCanvas().title = '';
        });
        map.getSource('sar-case')?.setData(caseGeojson);
        setMapReady(true);
        loadWeatherGridForMap(map).catch(() => {});
      });

      mapRef.current = map;
    }

    initMap();
    return () => {
      disposed = true;
      if (liveMap) liveMap.remove();
    };
  }, []);

  // ── Map source updates ───────────────────────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !map.isStyleLoaded()) return;
    map.getSource('weather-points')?.setData(weatherGrid);
    map.getSource('weather-vectors')?.setData(weatherVectors);
  }, [weatherGrid, weatherVectors, mapReady]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !map.isStyleLoaded()) return;
    map.getSource('vessels')?.setData(vessels);
  }, [vessels, mapReady]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !map.isStyleLoaded()) return;
    map.getSource('vessels-ngo')?.setData(ngoVessels);
  }, [ngoVessels, mapReady]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !map.isStyleLoaded()) return;
    map.getSource('platforms')?.setData(platforms);
  }, [platforms, mapReady]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !map.isStyleLoaded()) return;
    map.getSource('alerts')?.setData(alerts);
  }, [alerts, mapReady]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const src = map.getSource('sar-case');
    if (src) src.setData(caseGeojson);
  }, [caseGeojson, mapReady]);

  // Proximity overlay: update whenever nearest vessels or distress point changes
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !map.isStyleLoaded()) return;
    const { vessels: vfc, lines: lfc } = buildProximityGeojson(nearestVessels, selectedLat, selectedLon);
    map.getSource('proximity-vessels')?.setData(vfc);
    map.getSource('proximity-lines')?.setData(lfc);
  }, [nearestVessels, selectedLat, selectedLon, mapReady]);

  // Intel events map layer
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !map.isStyleLoaded()) return;
    const features = intelEvents.filter((f) => f.geometry?.coordinates);
    map.getSource('intel-events')?.setData({ type: 'FeatureCollection', features });
  }, [intelEvents, mapReady]);

  // Intel drift traces map layer
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !map.isStyleLoaded()) return;
    map.getSource('intel-drifts')?.setData(intelDrifts);
  }, [intelDrifts, mapReady]);

  // Intel → vessel correlation lines (manual toggle only)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !map.isStyleLoaded()) return;
    const layer = map.getLayer('intel-vessel-links-layer');
    if (!layer) return;
    if (!showVesselLinks) {
      map.setLayoutProperty('intel-vessel-links-layer', 'visibility', 'none');
      map.getSource('intel-vessel-links')?.setData({ type: 'FeatureCollection', features: [] });
      return;
    }
    // Build a lookup of MMSI → vessel coordinates from the current registry
    const vesselByMmsi = {};
    for (const f of (vessels.features || [])) {
      const mmsi = f.properties?.mmsi;
      if (mmsi && f.geometry?.coordinates) vesselByMmsi[String(mmsi)] = f.geometry.coordinates;
    }
    const features = [];
    for (const ev of intelEvents) {
      const p = ev.properties || {};
      const evCoords = ev.geometry?.coordinates;
      if (!evCoords || !p.linked_mmsi) continue;
      const vesselCoords = vesselByMmsi[String(p.linked_mmsi)];
      if (!vesselCoords) continue;
      features.push({
        type: 'Feature',
        geometry: { type: 'LineString', coordinates: [evCoords, vesselCoords] },
        properties: { severity: p.severity, mmsi: p.linked_mmsi, title: p.title },
      });
    }
    map.getSource('intel-vessel-links')?.setData({ type: 'FeatureCollection', features });
    map.setLayoutProperty('intel-vessel-links-layer', 'visibility', 'visible');
  }, [showVesselLinks, intelEvents, vessels, mapReady]);

  // ── Initial data load + polling ──────────────────────────────────────────────
  useEffect(() => {
    let alive = true;
    let lastVesselTs = null; // ISO timestamp of last full vessel fetch
    let vesselSnapshot = null; // latest full GeoJSON snapshot

    async function fetchVessels() {
      // First call: full load (active vessels last 2h, gzipped ~80KB).
      // Subsequent: incremental diff only (vessels updated since last poll).
      const isFirst = !lastVesselTs;
      const url = lastVesselTs ? `/api/v1/vessels?since=${encodeURIComponent(lastVesselTs)}` : '/api/v1/vessels';
      const timeoutMs = isFirst ? 20000 : 12000;
      const data = await fetchJson(apiBase, url, undefined, timeoutMs);
      if (!data?.features) return;
      lastVesselTs = new Date().toISOString();
      if (!vesselSnapshot) {
        vesselSnapshot = data;
      } else {
        // Merge incremental updates into snapshot
        const updated = new Map(data.features.map((f) => [f.properties?.mmsi, f]));
        const merged = vesselSnapshot.features.map((f) => updated.get(f.properties?.mmsi) || f);
        data.features.forEach((f) => { if (!vesselSnapshot.features.some((e) => e.properties?.mmsi === f.properties?.mmsi)) merged.push(f); });
        vesselSnapshot = { type: 'FeatureCollection', features: merged };
      }
      return vesselSnapshot;
    }

    async function loadSummary() {
      try {
        const summaryPayload = await fetchJson(apiBase, '/api/v1/ops/summary', undefined, 8000);
        if (!alive) return;
        setSummary(summaryPayload);
        setTimezero(summaryPayload?.backend?.timezero || null);
      } catch { /* non-critical */ }
      try {
        const statsPayload = await fetchJson(apiBase, '/api/v1/ops/stats', undefined, 10000);
        if (!alive) return;
        setStats(statsPayload);
      } catch { /* non-critical */ }
    }

    async function loadAll() {
      // ops/summary is NOT in this Promise.all — it's non-critical and
      // must never delay the map render or the loading banner clearing.
      try {
        const [vesselsPayload, alertsPayload] = await Promise.all([
          fetchVessels(),
          fetchJson(apiBase, '/api/v1/alerts/geojson'),
        ]);
        if (!alive) return;
        if (vesselsPayload) setVessels(vesselsPayload);
        setAlerts(alertsPayload);
        setError('');
      } catch (err) {
        if (!alive) return;
        setError(err.message || 'Backend unreachable');
      } finally {
        if (alive) setLoading(false);
      }
      // Fire summary fetch after banner clears — failure is silent
      loadSummary();
    }
    loadAll();
    const id = window.setInterval(loadAll, 15000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, [apiBase]);

  useEffect(() => {
    if (!Number.isFinite(selectedLat) || !Number.isFinite(selectedLon)) return;
    let cancelled = false;
    loadNearestVessels(selectedLat, selectedLon).catch(() => {
      if (!cancelled) setNearestVessels([]);
    });
    return () => { cancelled = true; };
  }, [apiBase, selectedLat, selectedLon]);

  // ── Derived data ─────────────────────────────────────────────────────────────
  const topStats = useMemo(() => {
    if (!summary) return [];
    const openAlerts = stats?.sar?.open_alerts ?? 0;
    return [
      { label: 'AIS',      value: summary.traffic?.registry?.active_30m ?? '—', tone: 'ok' },
      { label: 'Signals',  value: stats?.signals?.recent_event_count ?? '—',    tone: 'info' },
      { label: 'Alerts',   value: openAlerts,                                    tone: openAlerts > 0 ? 'warn' : 'default' },
      { label: 'Forensics',value: stats?.sar?.forensic_packets ?? '—',           tone: 'default' },
    ];
  }, [summary, stats]);

  const serviceRows = useMemo(() => {
    if (!summary) return [];
    return [
      { name: 'AISStream', state: summary.backend?.aisstream_connected ? 'live' : 'degraded', detail: summary.backend?.aisstream_connected ? `live feed (${summary.backend?.aisstream_messages} msgs)` : 'feed unavailable' },
      { name: 'CMEMS',     state: summary.backend?.cmems_configured ? 'ready' : 'degraded', detail: summary.backend?.cmems_configured ? 'live currents configured' : 'credentials missing' },
      { name: 'Redis',     state: summary.backend?.redis_configured ? 'ok' : 'off',      detail: summary.backend?.redis_configured ? 'cache active' : 'not configured' },
      { name: 'Database',  state: summary.backend?.database ?? '—',                      detail: summary.backend?.database === 'postgres' ? 'persistent' : 'local' },
      { name: 'Scheduler', state: summary.scheduler?.running ? 'live' : 'off',           detail: summary.scheduler?.running ? `${summary.scheduler?.jobs?.length || 0} jobs active` : 'not running' },
      { name: 'TimeZero',  state: timezero ? (timezero.enabled ? (timezero.reachable ? 'reachable' : 'off') : 'disabled') : 'pending', detail: timezero ? `${timezero.host}:${timezero.port}` : 'pending' },
    ];
  }, [summary, timezero]);

  // ── Actions ──────────────────────────────────────────────────────────────────
  async function loadWeather() {
    setWeather(null);
    try {
      await loadWeatherFor(form.lat, form.lon);
    } catch (err) {
      setError(err.message || 'Weather unavailable');
    }
  }

  async function runSarCaseAt(lat, lon, overrides = {}) {
    const persons = form.persons;
    const vesselType = form.vessel_type;
    const riskLevel = form.risk_level;
    const activeSType = overrides.scenarioType || scenarioType;
    simParamsRef.current = { scenarioType: activeSType, vesselType, persons, riskLevel, lat, lon };
    setCaseStatus('starting…');
    const emptyGeo = { type: 'FeatureCollection', features: [] };
    setCaseGeojson(emptyGeo);
    mapRef.current?.getSource('sar-case')?.setData(emptyGeo);
    setMapPanel(null);
    setError('');

    let nearby = nearestVessels;
    if (!nearby.length) {
      try { nearby = await loadNearestVessels(lat, lon); } catch { nearby = []; }
    }

    pushCaseLog(`${activeSType.replace('_', ' ')} @ ${Number(lat).toFixed(4)}, ${Number(lon).toFixed(4)}`);
    if (nearby.length) {
      pushCaseLog(`Nearest: ${nearby.map((v) => `${v.ship_name} (${v.distance_nm.toFixed(1)} nm)`).join(', ')}`);
    }

    try {
      const created = await fetchJson(apiBase, '/api/v1/alert', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          lat: Number(lat),
          lon: Number(lon),
          timestamp: new Date().toISOString(),
          persons: Number(persons || 0),
          vessel_type: vesselType,
          risk_level: riskLevel,
          scenario_type: activeSType,
          domain: 'ocean_sar',
        }),
      });

      setCaseStatus(`queued ${created.event_id.slice(0, 8)}`);
      setCaseEventId(created.event_id);
      pushCaseLog(`Alert queued ${created.event_id.slice(0, 8)}`);

      let consecutiveErrors = 0;
      for (let i = 0; i < 180; i += 1) {
        // ── Poll status — only retry on transient network errors ──────────────
        let statusResp;
        try {
          statusResp = await fetchJson(apiBase, `/api/v1/alert/${created.event_id}`);
          consecutiveErrors = 0;
        } catch (netErr) {
          consecutiveErrors += 1;
          if (consecutiveErrors >= 5) throw netErr;
          pushCaseLog(`Poll retry ${consecutiveErrors}/5…`);
          const delay = i < 20 ? 2000 : i < 60 ? 3000 : 5000;
          await new Promise((resolve) => window.setTimeout(resolve, delay));
          continue;
        }

        // ── Logical terminal states — fail/complete immediately, no retry ────
        if (statusResp.status === 'failed') {
          throw new Error(statusResp.drift_result?.metadata?.error || 'Simulation failed');
        }
        if (statusResp.status === 'completed') {
          const geojson = await fetchJson(apiBase, `/api/v1/alert/${created.event_id}/geojson`);
          const enriched = enrichCaseGeo(geojson, lat, lon);
          setCaseGeojson(enriched);
          mapRef.current?.getSource('sar-case')?.setData(enriched);
          setCaseStatus('completed');
          pushCaseLog(`Drift ready ${created.event_id.slice(0, 8)}`);
          // Save to session history (session-only — clears on page refresh)
          const _simEntry = {
            id: created.event_id,
            label: `${activeSType.replace(/_/g, ' ')} @ ${Number(lat).toFixed(3)}, ${Number(lon).toFixed(3)}`,
            ts: new Date().toISOString(),
            geojson: enriched,
            lat: Number(lat),
            lon: Number(lon),
            params: simParamsRef.current,
          };
          setSimHistory(prev => [_simEntry, ...prev.filter(s => s.id !== created.event_id).slice(0, 9)]);
          setActiveSimId(created.event_id);
          const trajFeature = geojson.features?.find(f => f.geometry?.type === 'LineString');
          const trajCoords = trajFeature?.geometry?.coordinates;
          const trajParam = trajCoords ? encodeURIComponent(JSON.stringify(trajCoords)) : '';
          const waveH = weather?.waves?.significant_height_m ?? '';
          const windMs = weather?.wind?.speed_ms ?? '';
          const analysisUrl = `/api/v1/zones/classify?lat=${lat}&lon=${lon}`
            + `&vessel_type=${encodeURIComponent(vesselType)}&persons=${persons}`
            + `&duration_h=24${trajParam ? `&traj=${trajParam}` : ''}`
            + `${waveH !== '' ? `&weather_wave=${waveH}` : ''}`
            + `${windMs !== '' ? `&weather_wind=${windMs}` : ''}`;
          fetchJson(apiBase, analysisUrl)
            .then(law => setMapPanel(prev => prev ? { ...prev, legalAnalysis: law } : prev))
            .catch(() => {});
          setMapPanel({ type: 'cone', feature: geojson.features?.[0] || null,
            eventId: created.event_id, caseStatus: 'completed',
            simParams: simParamsRef.current, legalAnalysis: null });
          mapRef.current?.flyTo({
            center: [Number(lon), Number(lat)],
            zoom: 8.4, essential: true, duration: 900,
          });
          return;
        }
        if (statusResp.status === 'processing' && caseStatusRef.current.startsWith('queued')) {
          setCaseStatus(`computing ${created.event_id.slice(0, 8)}`);
          pushCaseLog('Drift computing…');
        }
        const delay = i < 20 ? 2000 : i < 60 ? 3000 : 5000;
        await new Promise((resolve) => window.setTimeout(resolve, delay));
      }
      setCaseStatus('timeout');
      pushCaseLog('SAR case: timeout — server may still be computing');
    } catch (err) {
      setCaseStatus('error');
      setError(err.message || 'SAR case failed');
      pushCaseLog(`Error: ${err.message || 'unknown'}`);
    }
  }

  async function runSarCase(event) {
    if (event?.preventDefault) event.preventDefault();
    await runSarCaseAt(form.lat, form.lon, { scenarioType });
  }

  function updateSetting(key, value) {
    setLocalSettings((cur) => ({ ...cur, [key]: value }));
  }

  function setField(key, value) {
    setForm((cur) => ({ ...cur, [key]: value }));
  }

  function focusVessel(vessel) {
    setSelectedVessel(vessel);
    mapRef.current?.flyTo({
      center: [Number(vessel.lon), Number(vessel.lat)],
      zoom: 8.7,
      essential: true,
      duration: 800,
    });
  }

  function replaySim(sim) {
    const enriched = enrichCaseGeo(sim.geojson, sim.lat, sim.lon);
    setCaseGeojson(enriched);
    mapRef.current?.getSource('sar-case')?.setData(enriched);
    setActiveSimId(sim.id);
    setCaseStatus('completed');
    mapRef.current?.flyTo({ center: [sim.lon, sim.lat], zoom: 8.4, essential: true, duration: 900 });
    setMapPanel({
      type: 'cone',
      feature: sim.geojson.features?.[0] || null,
      eventId: sim.id,
      caseStatus: 'completed',
      simParams: sim.params,
      legalAnalysis: null,
    });
  }

  const intelStats = useMemo(() => {
    const by_type = {};
    const by_sev = {};
    for (const f of intelEvents) {
      const p = f.properties || {};
      if (p.type) by_type[p.type] = (by_type[p.type] || 0) + 1;
      if (p.severity) by_sev[p.severity] = (by_sev[p.severity] || 0) + 1;
    }
    return { total: intelEvents.length, by_type, by_sev };
  }, [intelEvents]);

  const isOnSim = activePanel === 'sim' || selectionMode;

  // ── Render ────────────────────────────────────────────────────────────────────
  return (
    <main className="cop-shell">
      <section className="map-stage">
        <div className="map-frame" ref={mapNodeRef} />

        <div className="map-toolbar">
          <div className="toolbar-pills">
            {topStats.map((stat) => (
              <Pill key={stat.label} label={`${stat.label}: ${stat.value}`} tone={stat.tone} />
            ))}
            <Pill label={MAPTILER_KEY ? 'Satellite' : 'OSM'} tone="info" />
          </div>
        </div>

        {error  ? <div className={`map-banner error ${sidebarOpen ? 'sidebar-open' : ''}`}>{error}</div> : null}
        {loading ? <div className={`map-banner ${sidebarOpen ? 'sidebar-open' : ''}`}>Connecting to backend…</div> : null}

        {isOnSim && cursorHint.visible ? (
          <div className="map-cursor-hint" style={{ left: cursorHint.x + 18, top: cursorHint.y + 22 }}>
            Click to set distress origin
          </div>
        ) : null}

        <div className={`map-overlay ${sidebarOpen ? 'sidebar-open' : ''}`}>
          <div className="overlay-card">
            <span className="overlay-label">Selected point</span>
            <strong>{Number.isFinite(selectedLat) ? `${selectedLat.toFixed(5)}, ${selectedLon.toFixed(5)}` : '—'}</strong>
            <span>{isOnSim ? 'Click map to set coordinates.' : 'Click map for point forecast.'}</span>
          </div>
        </div>

        {selectedVessel ? (
          <div className={`map-overlay-vessel ${sidebarOpen ? 'sidebar-open' : ''}`}>
            <div className="overlay-card">
              <span className="overlay-label">Selected vessel</span>
              <strong>{selectedVessel.ship_name || selectedVessel.name || selectedVessel.mmsi}</strong>
              <span>
                {(selectedVessel.type || selectedVessel.ship_type || 'unknown').toString()} · {selectedVessel.speed ?? selectedVessel.sog ?? '—'} kn · {selectedVessel.mmsi || 'n/a'}
              </span>
            </div>
          </div>
        ) : null}

        {caseLog.length > 0 ? (
          <div className="case-log-panel">
            <div className="log-header">Case log — {caseStatus}</div>
            <ul className="log-list">
              {caseLog.map((entry) => (
                <li key={entry.id}>
                  <span>{entry.message}</span>
                  <time>{new Date(entry.at).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</time>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {/* Cone detail panel — right side, appears when clicking a drift cone */}
        {mapPanel?.type === 'cone' && (
          <MapFloatingPanel
            panel={mapPanel}
            onClose={() => setMapPanel(null)}
            onComputeDrift={null}
          />
        )}

        {/* Scenario modal — center, appears when clicking empty map */}
        {showScenario && (
          <ScenarioModal
            lat={form.lat}
            lon={form.lon}
            form={form}
            onFormChange={setField}
            onConfirm={({ scenarioType: sType }) => {
              setScenarioType(sType);
              setShowScenario(false);
              runSarCaseAt(form.lat, form.lon, { scenarioType: sType });
            }}
            onClose={() => setShowScenario(false)}
          />
        )}
      </section>

      <button
        className={`sidebar-toggle ${sidebarOpen ? 'panel-open' : ''}`}
        onClick={() => setSidebarOpen((open) => !open)}
        title={sidebarOpen ? 'Close panel' : 'Open panel'}
      >
        {sidebarOpen ? '‹' : '›'}
      </button>

      <aside className={`sidebar ${sidebarOpen ? '' : 'is-closed'}`}>
        <header className="sidebar-header">
          <p className="sidebar-kicker">SeaCommons / SAR pilot</p>
          <h2>Operational dashboard</h2>
          <div className="sidebar-tabs sidebar-tabs--4">
            <button className={activePanel === 'sim'      ? 'is-active' : ''} onClick={() => setActivePanel('sim')}>Sim</button>
            <button className={activePanel === 'live'     ? 'is-active' : ''} onClick={() => setActivePanel('live')}>Live</button>
            <button className={activePanel === 'osint'    ? 'is-active' : ''} onClick={() => setActivePanel('osint')}>
              OSINT{intelEvents.length > 0 && <span className="tab-badge">{intelEvents.length}</span>}
            </button>
            <button className={activePanel === 'settings' ? 'is-active' : ''} onClick={() => setActivePanel('settings')}>Config</button>
          </div>
        </header>

        <div className="sidebar-inner">

          {/* ── LIVE TAB ── */}
          {activePanel === 'live' ? (
            <div className="panel-stack">
              <section className="panel-block">
                <p className="section-kicker">Live conditions</p>
                <h3>Operational weather</h3>
                <div className="info-grid">
                  <div className="info-box">
                    <strong>Overlay</strong>
                    <span>Native weather grid</span>
                  </div>
                  <div className="info-box">
                    <strong>Weather source</strong>
                    <span>{weather ? weather.source : 'Open-Meteo / CMEMS'}</span>
                  </div>
                </div>
                {weather ? (
                  <div className="weather-card">
                    <span>Wind {weather.wind?.speed_ms ?? '—'} m/s {weather.wind?.direction_label ?? ''}</span>
                    <span>Wave {weather.waves?.significant_height_m ?? '—'} m</span>
                    <span>Current {weather.ocean?.current_speed_ms ?? '—'} m/s</span>
                    <span>Drift {weather.sar_conditions?.drift_speed_ms ?? '—'} m/s — {weather.sar_conditions?.drift_dir_deg ?? '—'}°</span>
                  </div>
                ) : null}
                <div className="action-row">
                  <button onClick={loadWeather}>Load point forecast</button>
                  <button onClick={() => loadWeatherGridForMap(mapRef.current).catch((err) => setError(err.message || 'Weather grid unavailable'))}>Refresh overlay</button>
                </div>
              </section>

              <section className="panel-block">
                <p className="section-kicker">Recent signals</p>
                <h3>Event intake</h3>
                <ul className="signal-list">
                  {(stats?.signals?.recent_events || []).map((item) => (
                    <li key={`${item.timestamp}-${item.vessel_id || 'evt'}`}>
                      <strong>{item.ship_name || item.vessel_id || item.event_type}</strong>
                      <span>{item.adapter || item.protocol || 'unknown source'}</span>
                      <span>{item.status || item.event_type}</span>
                    </li>
                  ))}
                </ul>
              </section>
            </div>
          ) : null}

          {/* ── OSINT TAB ── */}
          {activePanel === 'osint' ? (
            <IntelDashboard
              apiBase={apiBase}
              intelEvents={intelEvents}
              intelDrifts={intelDrifts}
              intelStats={intelStats}
              intelFilter={intelFilter}
              setIntelFilter={setIntelFilter}
              intelMode={intelMode}
              showAisAlerts={showAisAlerts}
              setShowAisAlerts={setShowAisAlerts}
              triggeringDrift={triggeringDrift}
              triggerIntelDrift={triggerIntelDrift}
              mapRef={mapRef}
              setSidebarOpen={setSidebarOpen}
            />
          ) : null}

          {/* ── DEMO TAB ── */}
          {activePanel === 'sim' ? (
            <div className="panel-stack">
              <section className="panel-block">
                <p className="section-kicker">SAR simulation</p>
                <h3>New drift case</h3>
                <p className="panel-copy">
                  Click the map to set coordinates. Before computing drift, SeaCommons queries and displays the 5 nearest vessels to the distress point.
                </p>

                <form onSubmit={runSarCase}>
                  <div className="demo-form">
                    <label>
                      Latitude
                      <input value={form.lat} onChange={(e) => setField('lat', e.target.value)} />
                    </label>
                    <label>
                      Longitude
                      <input value={form.lon} onChange={(e) => setField('lon', e.target.value)} />
                    </label>
                    <label>
                      Persons aboard
                      <input type="number" min="1" value={form.persons} onChange={(e) => setField('persons', e.target.value)} />
                    </label>
                    <label>
                      Risk level
                      <select value={form.risk_level} onChange={(e) => setField('risk_level', e.target.value)}>
                        {RISK_LEVELS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
                      </select>
                    </label>
                  </div>

                  <div className="field-block" style={{ marginTop: 8 }}>
                    <span>Vessel type</span>
                    <select value={form.vessel_type} onChange={(e) => setField('vessel_type', e.target.value)}>
                      {VESSEL_TYPES.map((v) => <option key={v.value} value={v.value}>{v.label}</option>)}
                    </select>
                  </div>

                  <div className="action-row">
                    <button type="submit">Compute drift</button>
                    <button type="button" onClick={() => setSelectionMode((v) => !v)}>
                      {selectionMode ? 'Cancel selection' : 'Pick from map'}
                    </button>
                  </div>
                </form>

                {selectionMode ? (
                  <div className="demo-note">
                    Selection mode active — click the map to set coordinates.
                  </div>
                ) : null}

                <div className="status-strip">
                  <span>Status</span>
                  <strong>{caseStatus}</strong>
                </div>
              </section>

              <section className="panel-block">
                <p className="section-kicker">Proximity search</p>
                <h3>5 nearest vessels</h3>
                <ul className="service-list">
                  {nearestVessels.length ? nearestVessels.map((vessel, idx) => (
                    <li key={`${vessel.mmsi}-${vessel.distance_km}`}>
                      <div>
                        <strong>#{idx + 1} {vessel.ship_name}</strong>
                        <span>{(vessel.type || 'unknown').toString()} — {formatDistance(vessel)}</span>
                      </div>
                      <button className="link-button" type="button" onClick={() => focusVessel(vessel)}>
                        Focus
                      </button>
                    </li>
                  )) : (
                    <li>
                      <div>
                        <strong>No vessels found</strong>
                        <span>Select valid coordinates or check the AIS feed.</span>
                      </div>
                    </li>
                  )}
                </ul>
              </section>

              <SimHistory
                history={simHistory}
                activeId={activeSimId}
                onReplay={replaySim}
                onRemove={(id) => setSimHistory(prev => prev.filter(s => s.id !== id))}
                onClear={() => { setSimHistory([]); setActiveSimId(null); }}
              />
            </div>
          ) : null}


          {/* ── CONFIG TAB ── */}
          {activePanel === 'settings' ? (
            <div className="panel-stack">
              <section className="panel-block">
                <p className="section-kicker">Connectivity</p>
                <h3>API endpoint</h3>
                <label className="field-block">
                  API base
                  <input value={apiBase} onChange={(e) => setApiBase(e.target.value)} placeholder="http://127.0.0.1:8000" />
                </label>
                <div className="action-row" style={{ marginTop: 8 }}>
                  <a
                    href={`${apiBase}/docs`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="action-row button"
                    style={{ padding: '6px 11px', borderRadius: 3, background: 'linear-gradient(135deg,#83f4df,#70a2ff)', color: '#061015', fontWeight: 700, fontSize: 11, textDecoration: 'none', display: 'inline-flex', alignItems: 'center' }}
                  >
                    API docs (Swagger)
                  </a>
                  <a
                    href={`${apiBase}/redoc`}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ padding: '6px 11px', borderRadius: 3, background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)', color: '#dfeae7', fontWeight: 600, fontSize: 11, textDecoration: 'none', display: 'inline-flex', alignItems: 'center' }}
                  >
                    ReDoc
                  </a>
                </div>
              </section>

              <section className="panel-block">
                <p className="section-kicker">TimeZero bridge</p>
                <h3>Chart plotter</h3>
                <label className="field-block">
                  Host
                  <input value={localSettings.timezeroHost} onChange={(e) => updateSetting('timezeroHost', e.target.value)} />
                </label>
                <label className="field-block" style={{ marginTop: 7 }}>
                  Port
                  <input value={localSettings.timezeroPort} onChange={(e) => updateSetting('timezeroPort', e.target.value)} />
                </label>
              </section>

              <section className="panel-block">
                <p className="section-kicker">Service matrix</p>
                <h3>Runtime</h3>
                <ul className="service-list">
                  {serviceRows.map((service) => (
                    <li key={service.name}>
                      <div>
                        <strong>{service.name}</strong>
                        <span>{service.detail}</span>
                      </div>
                      <Pill
                        label={service.state}
                        tone={['reachable', 'live', 'ready', 'ok'].includes(service.state) ? 'ok' : service.state === 'degraded' ? 'warn' : 'default'}
                      />
                    </li>
                  ))}
                </ul>
              </section>
            </div>
          ) : null}

        </div>
      </aside>
    </main>
  );
}

createRoot(document.getElementById('root')).render(<App />);
