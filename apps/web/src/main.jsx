import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';
import MapFloatingPanel from './components/ConePanel.jsx';
import ScenarioModal from './components/ScenarioModal.jsx';

function guessApiBase() {
  const envBase = import.meta.env.VITE_API_BASE;
  if (envBase) return envBase.replace(/\/$/, '');
  const saved = window.localStorage.getItem('seacommons_api_base');
  if (saved) return saved.replace(/\/$/, '');
  const { protocol, hostname, port, origin } = window.location;
  if (hostname === 'localhost' || hostname === '127.0.0.1') return `${protocol}//${hostname}:8000`;
  if (port === '3000' || port === '5173' || port === '4173') return `${protocol}//${hostname}:8000`;
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

async function fetchJson(base, path, options) {
  const response = await fetch(apiUrl(base, path), options);
  if (!response.ok) {
    const text = await response.text().catch(() => '');
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.json();
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

function App() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [activePanel, setActivePanel] = useState('sim');
  const [apiBase, setApiBase] = useState(guessApiBase);
  const [localSettings, setLocalSettings] = useState(loadLocalSettings);
  const [summary, setSummary] = useState(null);
  const [vessels, setVessels] = useState({ type: 'FeatureCollection', features: [] });
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
  const [intelEvents, setIntelEvents] = useState([]);
  const [intelConnected, setIntelConnected] = useState(false);
  const [intelFilter, setIntelFilter] = useState('all');
  const caseEventIdRef = useRef(null);
  const caseStatusRef = useRef('idle');
  const simParamsRef = useRef({});
  const intelWsRef = useRef(null);
  const [form, setForm] = useState({
    lat: '35.889',
    lon: '14.519',
    persons: '37',
    vessel_type: 'rubber_boat',
    risk_level: 'high',
  });

  const mapNodeRef = useRef(null);
  const mapRef = useRef(null);
  const selectionModeRef = useRef(false);
  const activePanelRef = useRef('sim');

  const selectedLat = Number(form.lat);
  const selectedLon = Number(form.lon);

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

  // ── Intel feed: WebSocket with REST polling fallback ─────────────────────────
  // Vercel's HTTP rewrite proxy strips WebSocket upgrade headers, so WS only
  // works when the API is served from the same origin or via a real WS proxy.
  // After 3 failed WS attempts we fall back to polling /api/v1/intel every 30s.
  useEffect(() => {
    const wsBase = apiBase.replace(/^http/, 'ws');
    let ws = null;
    let reconnectTimer = null;
    let pollTimer = null;
    let failCount = 0;
    let alive = true;
    const MAX_WS_FAILS = 3;

    async function pollIntel() {
      if (!alive) return;
      try {
        const data = await fetchJson(apiBase, '/api/v1/intel?limit=200');
        if (alive && data.features) {
          setIntelEvents(data.features);
          setIntelConnected(true);
        }
      } catch { /* ignore */ }
      if (alive) pollTimer = window.setTimeout(pollIntel, 30000);
    }

    function startPolling() {
      setIntelConnected(false);
      pollIntel();
    }

    function connect() {
      if (!alive) return;
      ws = new WebSocket(`${wsBase}/ws/intel`);
      intelWsRef.current = ws;

      const openTimer = window.setTimeout(() => {
        // If socket hasn't opened in 4s, count as failure
        if (ws.readyState !== WebSocket.OPEN) {
          ws.close();
        }
      }, 4000);

      ws.onopen = () => {
        window.clearTimeout(openTimer);
        failCount = 0;
        setIntelConnected(true);
      };
      ws.onclose = () => {
        window.clearTimeout(openTimer);
        setIntelConnected(false);
        if (!alive) return;
        failCount += 1;
        if (failCount >= MAX_WS_FAILS) {
          // Switch permanently to REST polling
          startPolling();
        } else {
          reconnectTimer = window.setTimeout(connect, 5000);
        }
      };
      ws.onerror = () => { window.clearTimeout(openTimer); ws.close(); };
      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data);
          if (msg.type === 'ping') return;
          if (msg.type === 'snapshot') {
            setIntelEvents(msg.features || []);
          } else if (msg.type === 'Feature') {
            setIntelEvents((prev) => [msg, ...prev].slice(0, 300));
          }
        } catch { /* ignore */ }
      };
    }

    connect();
    return () => {
      alive = false;
      window.clearTimeout(reconnectTimer);
      window.clearTimeout(pollTimer);
      ws?.close();
    };
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
        // sources
        map.addSource('weather-points',    { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        map.addSource('weather-vectors',   { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        map.addSource('vessels',           { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        map.addSource('alerts',            { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        map.addSource('sar-case',          { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        map.addSource('proximity-lines',   { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        map.addSource('proximity-vessels', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        map.addSource('intel-events',      { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });

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

        // AIS vessels
        map.addLayer({
          id: 'vessels-halo', type: 'circle', source: 'vessels',
          paint: { 'circle-radius': 8, 'circle-color': 'rgba(117,255,229,0.16)', 'circle-blur': 0.6 },
        });
        map.addLayer({
          id: 'vessels-layer', type: 'circle', source: 'vessels',
          paint: {
            'circle-radius': 5, 'circle-color': '#8ff5e2', 'circle-opacity': 0.96,
            'circle-stroke-width': 1.2, 'circle-stroke-color': '#021318',
          },
        });

        // SAR drift result
        map.addLayer({
          id: 'alerts-layer', type: 'line', source: 'alerts',
          filter: ['==', '$type', 'LineString'],
          paint: { 'line-color': '#ff7b54', 'line-width': 2.5, 'line-opacity': 0.9 },
        });
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
            'line-width': 2.5,
            'line-opacity': 0.92,
            'line-dasharray': [6, 4],
          },
        });
        map.addLayer({
          id: 'sar-case-points', type: 'circle', source: 'sar-case',
          filter: ['==', '$type', 'Point'],
          paint: {
            'circle-radius': 5, 'circle-color': '#fff4bf',
            'circle-stroke-width': 1.5, 'circle-stroke-color': '#ff7b54',
          },
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

        // Proximity: highlighted vessel circles (orange, larger)
        map.addLayer({
          id: 'proximity-vessels-halo', type: 'circle', source: 'proximity-vessels',
          paint: { 'circle-radius': 12, 'circle-color': 'rgba(249,115,22,0.18)', 'circle-blur': 0.7 },
        });
        map.addLayer({
          id: 'proximity-vessels-layer', type: 'circle', source: 'proximity-vessels',
          paint: {
            'circle-radius': 7,
            'circle-color': '#fb923c',
            'circle-opacity': 0.97,
            'circle-stroke-width': 2,
            'circle-stroke-color': '#431407',
          },
        });

        // Intel event circles
        map.addLayer({
          id: 'intel-events-halo', type: 'circle', source: 'intel-events',
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

        map.on('mouseenter', 'intel-events-layer', () => { map.getCanvas().style.cursor = 'pointer'; });
        map.on('mouseleave', 'intel-events-layer', () => {
          map.getCanvas().style.cursor = (activePanelRef.current === 'sim' || selectionModeRef.current) ? 'crosshair' : '';
        });
        map.on('click', 'intel-events-layer', (event) => {
          const feature = event.features?.[0];
          if (!feature) return;
          const [lon, lat] = feature.geometry.coordinates;
          map.flyTo({ center: [lon, lat], zoom: 9, duration: 800 });
          setActivePanel('intel');
          setSidebarOpen(true);
          event.originalEvent?.stopPropagation?.();
        });

        // vessel click
        map.on('mouseenter', 'vessels-layer', () => { map.getCanvas().style.cursor = 'pointer'; });
        map.on('mouseleave', 'vessels-layer', () => {
          map.getCanvas().style.cursor = (activePanelRef.current === 'sim' || selectionModeRef.current) ? 'crosshair' : '';
        });
        map.on('click', 'vessels-layer', (event) => {
          const feature = event.features?.[0];
          if (!feature) return;
          const [lon, lat] = feature.geometry.coordinates;
          setSelectedVessel({ ...feature.properties, lon, lat });
          setSidebarOpen(true);
        });

        // proximity vessel click — same behaviour
        map.on('mouseenter', 'proximity-vessels-layer', () => { map.getCanvas().style.cursor = 'pointer'; });
        map.on('mouseleave', 'proximity-vessels-layer', () => {
          map.getCanvas().style.cursor = (activePanelRef.current === 'sim' || selectionModeRef.current) ? 'crosshair' : '';
        });
        map.on('click', 'proximity-vessels-layer', (event) => {
          const feature = event.features?.[0];
          if (!feature) return;
          const [lon, lat] = feature.geometry.coordinates;
          setSelectedVessel({ ...feature.properties, lon, lat });
          setSidebarOpen(true);
        });

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
            layers: ['sar-case-cone', 'sar-case-points', 'vessels-layer', 'proximity-vessels-layer', 'intel-events-layer'],
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
        map.getSource('alerts')?.setData(alerts);
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
    map.getSource('alerts')?.setData(alerts);
  }, [alerts, mapReady]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !map.isStyleLoaded()) return;
    map.getSource('sar-case')?.setData(caseGeojson);
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

  // ── Initial data load + polling ──────────────────────────────────────────────
  useEffect(() => {
    let alive = true;
    let lastVesselTs = null; // ISO timestamp of last full vessel fetch
    let vesselSnapshot = null; // latest full GeoJSON snapshot

    async function fetchVessels() {
      // First call: full load. Subsequent: incremental diff only (much smaller payload).
      const url = lastVesselTs ? `/api/v1/vessels?since=${encodeURIComponent(lastVesselTs)}` : '/api/v1/vessels';
      const data = await fetchJson(apiBase, url);
      if (!data?.features) return;
      lastVesselTs = new Date().toISOString();
      if (!vesselSnapshot || !lastVesselTs) {
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

    async function loadAll() {
      try {
        const [summaryPayload, vesselsPayload, alertsPayload] = await Promise.all([
          fetchJson(apiBase, '/api/v1/ops/summary'),
          fetchVessels(),
          fetchJson(apiBase, '/api/v1/alerts/geojson'),
        ]);
        if (!alive) return;
        setSummary(summaryPayload);
        setTimezero(summaryPayload.backend.timezero || null);
        if (vesselsPayload) setVessels(vesselsPayload);
        setAlerts(alertsPayload);
        setError('');
      } catch (err) {
        if (!alive) return;
        setError(err.message || 'Backend unreachable');
      } finally {
        if (alive) setLoading(false);
      }
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
    return [
      { label: 'AIS',      value: summary.traffic.registry.active_30m,   tone: 'ok' },
      { label: 'Signals',  value: summary.signals.recent_event_count,     tone: 'info' },
      { label: 'Alerts',   value: summary.sar.open_alerts,                tone: summary.sar.open_alerts > 0 ? 'warn' : 'default' },
      { label: 'Forensics',value: summary.sar.forensic_packets,           tone: 'default' },
    ];
  }, [summary]);

  const serviceRows = useMemo(() => {
    if (!summary) return [];
    return [
      { name: 'AISStream', state: summary.backend.aisstream_connected ? 'live' : 'degraded', detail: summary.backend.aisstream_connected ? `live feed (${summary.backend.aisstream_messages} msgs)` : 'feed unavailable' },
      { name: 'CMEMS',     state: summary.backend.cmems_configured ? 'ready' : 'degraded', detail: summary.backend.cmems_configured ? 'live currents configured' : 'credentials missing' },
      { name: 'Redis',     state: summary.backend.redis_configured ? 'ok' : 'off',      detail: summary.backend.redis_configured ? 'cache active' : 'not configured' },
      { name: 'Database',  state: summary.backend.database,                             detail: summary.backend.database === 'postgres' ? 'persistent' : 'local' },
      { name: 'Scheduler', state: summary.scheduler?.running ? 'live' : 'off',          detail: summary.scheduler?.running ? `${summary.scheduler.jobs?.length || 0} jobs active` : 'not running' },
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
    setCaseGeojson({ type: 'FeatureCollection', features: [] });
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
        try {
          const status = await fetchJson(apiBase, `/api/v1/alert/${created.event_id}`);
          consecutiveErrors = 0;
          if (status.status === 'failed') {
            throw new Error(status.drift_result?.metadata?.error || 'Simulation failed');
          }
          if (status.status === 'completed') {
            const geojson = await fetchJson(apiBase, `/api/v1/alert/${created.event_id}/geojson`);
            setCaseGeojson(geojson);
            setCaseStatus('completed');
            pushCaseLog(`Drift ready ${created.event_id.slice(0, 8)}`);
            mapRef.current?.flyTo({
              center: [Number(lon), Number(lat)],
              zoom: 8.4,
              essential: true,
              duration: 900,
            });
            return;
          }
          // Show computing status once computation starts (vs queued)
          if (status.status === 'processing' && caseStatusRef.current.startsWith('queued')) {
            setCaseStatus(`computing ${created.event_id.slice(0, 8)}`);
            pushCaseLog('Drift computing…');
          }
        } catch (pollErr) {
          consecutiveErrors += 1;
          // Transient network error — back off, don't fail immediately
          if (consecutiveErrors >= 5) throw pollErr;
          pushCaseLog(`Poll retry ${consecutiveErrors}/5…`);
        }
        // Adaptive polling: faster at start, slower as time passes
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

  const intelEventsFiltered = useMemo(() => {
    if (intelFilter === 'all') return intelEvents;
    return intelEvents.filter((f) => f.properties?.severity === intelFilter);
  }, [intelEvents, intelFilter]);

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
            <strong>{selectedLat.toFixed(5)}, {selectedLon.toFixed(5)}</strong>
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
                    <span>Wind {weather.wind.speed_ms} m/s {weather.wind.direction_label}</span>
                    <span>Wave {weather.waves.significant_height_m} m</span>
                    <span>Current {weather.ocean.current_speed_ms} m/s</span>
                    <span>Drift {weather.sar_conditions.drift_speed_ms} m/s — {weather.sar_conditions.drift_dir_deg}°</span>
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
                  {(summary?.signals.recent_events || []).map((item) => (
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

          {/* ── OSINT TAB (unified Data + Intel) ── */}
          {activePanel === 'osint' ? (
            <div className="panel-stack">
              {/* Stats row */}
              <section className="panel-block">
                <p className="section-kicker">Open Source Intelligence</p>
                <div className="osint-stats-row">
                  <div className="osint-stat">
                    <strong>{intelStats.total}</strong><span>events</span>
                  </div>
                  <div className="osint-stat osint-stat--critical">
                    <strong>{intelStats.by_sev['critical'] || 0}</strong><span>critical</span>
                  </div>
                  <div className="osint-stat osint-stat--high">
                    <strong>{intelStats.by_sev['high'] || 0}</strong><span>high</span>
                  </div>
                  <div className="osint-stat">
                    <strong>{summary?.traffic?.registry?.active_30m ?? '—'}</strong><span>AIS live</span>
                  </div>
                  <div className="osint-stat">
                    <strong>{summary?.sar?.open_alerts ?? '—'}</strong><span>alerts</span>
                  </div>
                </div>
              </section>

              {/* Filter + feed */}
              <section className="panel-block" style={{ paddingBottom: 0 }}>
                <div className="osint-feed-header">
                  <span className="osint-feed-title">
                    Intel feed{' '}
                    <span className={intelConnected ? 'intel-connected' : 'intel-offline'}>
                      {intelConnected ? '●' : '○'}
                    </span>
                  </span>
                  <div className="intel-filter-row">
                    {['all', 'critical', 'high', 'medium', 'low'].map((f) => (
                      <button
                        key={f}
                        className={`intel-filter-btn ${intelFilter === f ? 'is-active' : ''}`}
                        onClick={() => setIntelFilter(f)}
                      >{f}</button>
                    ))}
                  </div>
                </div>
              </section>

              <section className="panel-block" style={{ padding: 0 }}>
                <ul className="intel-list">
                  {intelEventsFiltered.length === 0 ? (
                    <li className="intel-empty">
                      {intelConnected ? `No events${intelFilter !== 'all' ? ` (${intelFilter})` : ''} yet` : 'Connecting…'}
                    </li>
                  ) : intelEventsFiltered.map((feat) => {
                    const p = feat.properties || {};
                    const coords = feat.geometry?.coordinates;
                    const ts = p.timestamp_utc ? new Date(p.timestamp_utc) : null;
                    const canDrift = coords && coords[0] != null && coords[1] != null;
                    return (
                      <li
                        key={p.id || p.title}
                        className="intel-event"
                        onClick={() => {
                          if (coords) mapRef.current?.flyTo({ center: coords, zoom: 9, duration: 800 });
                        }}
                      >
                        <div className="intel-event-header">
                          <span className={`intel-sev intel-sev--${p.severity || 'low'}`}>{p.severity || 'low'}</span>
                          {ts && <time>{ts.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}</time>}
                          {canDrift && (
                            <button
                              className="intel-drift-btn"
                              title="Run SAR drift from this position"
                              onClick={(e) => {
                                e.stopPropagation();
                                setForm((cur) => ({ ...cur, lat: String(coords[1].toFixed(5)), lon: String(coords[0].toFixed(5)) }));
                                setActivePanel('sim');
                                runSarCaseAt(coords[1], coords[0], { scenarioType });
                              }}
                            >⟳ Drift</button>
                          )}
                        </div>
                        <strong className="intel-title">{p.title}</strong>
                        <span className="intel-source">{p.source} · {(p.type || '').replace(/_/g, ' ')}</span>
                        {p.text && (
                          <p className="intel-text">{p.text.slice(0, 120)}{p.text.length > 120 ? '…' : ''}</p>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </section>

              {/* Channel breakdown */}
              {Object.keys(intelStats.by_type).length > 0 && (
                <section className="panel-block">
                  <p className="section-kicker">By channel</p>
                  <ul className="signal-list" style={{ marginTop: 4 }}>
                    {Object.entries(intelStats.by_type).sort((a, b) => b[1] - a[1]).map(([type, count]) => (
                      <li key={type}>
                        <strong>{type.replace(/_/g, ' ')}</strong>
                        <span>{count}</span>
                      </li>
                    ))}
                  </ul>
                </section>
              )}
            </div>
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
