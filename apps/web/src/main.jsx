import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';
import './suez-theme.css';
import MapFloatingPanel from './components/ConePanel.jsx';
import ScenarioModal from './components/ScenarioModal.jsx';
import SimHistory from './components/SimHistory.jsx';
import IntelDashboard from './components/IntelDashboard.jsx';
import LayerToggles, { LAYER_GROUPS } from './components/LayerToggles.jsx';
import { AuthGate } from './auth.jsx';
import CasesWorkspace from './components/CasesWorkspace.jsx';
import JobMonitor from './components/JobMonitor.jsx';
import PlayCesium from './components/PlayCesium.jsx';
import UnrealPixelStream from './components/UnrealPixelStream.jsx';
import ConnectorWorkspace from './components/ConnectorWorkspace.jsx';
import { buildEnvironmentSnapshot, createScenario } from './simulation/contracts.js';
import { loadStoredSimulations, storeScenario } from './simulation/scenarioStore.js';
import { computeDriftInWorker } from './simulation/workerClient.js';
import {
  decorateLiveTracking,
  liveTrackingCandidates,
  mergeLiveDrifts,
} from './simulation/liveTracking.js';

// Real-world-scaled circle radius: interpolate exponentially with zoom so
// `location_uncertainty_m` (meters) renders as an actually-to-scale area
// rather than a fixed pixel size. cos(37°) ≈ 0.8 approximates the whole
// Mediterranean band well enough for a visual "this is imprecise" cue.
const METERS_TO_PX_RADIUS = [
  'interpolate', ['exponential', 2], ['zoom'],
  0, ['/', ['coalesce', ['get', 'location_uncertainty_m'], 0], 156543.03392 * 0.8],
  22, ['/', ['coalesce', ['get', 'location_uncertainty_m'], 0], (156543.03392 * 0.8) / Math.pow(2, 22)],
];

const PUBLIC_DEMO_HOSTS = new Set(['play.seacommons.org', 'demo.seacommons.org']);
const LIVE_HOSTS = new Set(['live.seacommons.org', 'console.seacommons.org', 'engine.seacommons.org']);
const isPublicDemoHost = PUBLIC_DEMO_HOSTS.has(window.location.hostname);
const isPublicLiveHost = window.location.hostname === 'live.seacommons.org';
const isLiveHost = LIVE_HOSTS.has(window.location.hostname);
const APP_PROFILE = isLiveHost
  ? 'live'
  : isPublicDemoHost
    ? 'demo'
    : import.meta.env.VITE_APP_PROFILE === 'live'
      ? 'live'
      : 'demo';

function receivedSignalFeatures(features) {
  if (!Array.isArray(features)) return [];
  return features.filter((feature) => {
    const properties = feature?.properties || {};
    const policy = String(properties.source_policy || '').toLowerCase();
    const transport = String(properties.via || properties.scrape_source || '').toLowerCase();
    return !['nitter', 'twscrape', 'scrape', 'unofficial'].some(
      (blocked) => policy === blocked || transport.includes(blocked),
    )
      && properties.type !== 'sar_model'
      && properties.title !== 'Computed SAR drift product'
      && properties.source !== 'SeaCommons engine';
  });
}

function enrichCaseGeo(geojson, lat, lon) {
  // Idempotent: replaying an already-enriched collection must not duplicate the origin marker.
  if (geojson.features?.some((f) => f.properties?.type === 'origin_point')) return geojson;
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
  if (hostname === 'console.seacommons.org' || hostname === 'engine.seacommons.org') return 'https://api.seacommons.org';
  if (hostname === 'demo.seacommons.org') return 'https://demo-api.seacommons.org';
  // Other production deployments may provide a same-origin API proxy.
  // Ignore stale localStorage entries that may point to a retired backend.
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
    const token = window.__SEACOMMONS_ACCESS_TOKEN__;
    const headers = { ...(options?.headers || {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) };
    const response = await fetch(apiUrl(base, path), { signal: controller.signal, ...options, headers });
    if (!response.ok) {
      const text = await response.text().catch(() => '');
      // If the error body is HTML (proxy / cold-start page), surface a clean message.
      const msg = text && !text.trimStart().startsWith('<')
        ? text
        : `HTTP ${response.status} — backend unavailable`;
      throw new Error(msg);
    }
    const text = await response.text();
    if (!text || text.trimStart().startsWith('<')) {
      throw new Error('Backend returned non-JSON — may still be starting up');
    }
    return JSON.parse(text);
  } finally {
    window.clearTimeout(timer);
  }
}

async function fetchOpenMeteoEnvironment(lat, lon) {
  const latitude = Number(lat);
  const longitude = Number(lon);
  const edgeBase = String(import.meta.env.VITE_EDGE_API_BASE || '').replace(/\/$/, '');
  if (edgeBase) {
    const edgeController = new AbortController();
    const edgeTimer = window.setTimeout(() => edgeController.abort(), 8000);
    try {
      const edgeUrl = new URL(`${edgeBase}/v1/environment`);
      edgeUrl.searchParams.set('lat', latitude.toFixed(5));
      edgeUrl.searchParams.set('lon', longitude.toFixed(5));
      const edgeResponse = await fetch(edgeUrl, { signal: edgeController.signal });
      if (!edgeResponse.ok) throw new Error(`SeaCommons Edge ${edgeResponse.status}`);
      const edgePayload = await edgeResponse.json();
      if (!Array.isArray(edgePayload.forecast_frames) || !edgePayload.forecast_frames.length) {
        throw new Error('SeaCommons Edge returned no forcing frames');
      }
      return edgePayload;
    } catch {
      // Direct provider access remains a no-Oracle fallback while the edge
      // gateway is unavailable or before it is deployed.
    } finally {
      window.clearTimeout(edgeTimer);
    }
  }
  const weatherUrl = new URL('https://api.open-meteo.com/v1/forecast');
  weatherUrl.searchParams.set('latitude', latitude.toFixed(4));
  weatherUrl.searchParams.set('longitude', longitude.toFixed(4));
  weatherUrl.searchParams.set(
    'current',
    'temperature_2m,relative_humidity_2m,apparent_temperature,is_day,precipitation,weather_code,cloud_cover,visibility,surface_pressure,wind_speed_10m,wind_direction_10m,wind_gusts_10m',
  );
  weatherUrl.searchParams.set('hourly', 'wind_speed_10m,wind_direction_10m,wind_gusts_10m');
  weatherUrl.searchParams.set('wind_speed_unit', 'ms');
  weatherUrl.searchParams.set('timezone', 'UTC');
  weatherUrl.searchParams.set('past_days', '2');
  weatherUrl.searchParams.set('forecast_days', '3');

  const marineUrl = new URL('https://marine-api.open-meteo.com/v1/marine');
  marineUrl.searchParams.set('latitude', latitude.toFixed(4));
  marineUrl.searchParams.set('longitude', longitude.toFixed(4));
  marineUrl.searchParams.set(
    'current',
    'wave_height,wave_direction,wave_period,sea_surface_temperature,ocean_current_velocity,ocean_current_direction',
  );
  marineUrl.searchParams.set(
    'hourly',
    'wave_height,wave_direction,wave_period,sea_surface_temperature,ocean_current_velocity,ocean_current_direction',
  );
  marineUrl.searchParams.set('timezone', 'UTC');
  marineUrl.searchParams.set('past_days', '2');
  marineUrl.searchParams.set('forecast_days', '3');

  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 10000);
  try {
    const [weatherResponse, marineResponse] = await Promise.all([
      fetch(weatherUrl, { signal: controller.signal }),
      fetch(marineUrl, { signal: controller.signal }),
    ]);
    if (!weatherResponse.ok || !marineResponse.ok) {
      throw new Error(`Open-Meteo ${weatherResponse.status}/${marineResponse.status}`);
    }
    const [weatherPayload, marinePayload] = await Promise.all([
      weatherResponse.json(),
      marineResponse.json(),
    ]);
    const current = weatherPayload.current || {};
    const marine = marinePayload.current || {};
    const marineUnits = marinePayload.current_units || {};
    const currentVelocity = Number(marine.ocean_current_velocity);
    const currentSpeedMs = marineUnits.ocean_current_velocity === 'km/h'
      ? currentVelocity / 3.6
      : currentVelocity;
    const timestamp = String(current.time || marine.time || new Date().toISOString());
    const weatherHourly = weatherPayload.hourly || {};
    const marineHourly = marinePayload.hourly || {};
    const marineHourlyUnits = marinePayload.hourly_units || {};
    const marineIndexByTime = new Map(
      (marineHourly.time || []).map((time, index) => [time, index]),
    );
    const forecastFrames = (weatherHourly.time || []).map((time, weatherIndex) => {
      const marineIndex = marineIndexByTime.get(time);
      if (marineIndex === undefined) return null;
      const hourlyCurrent = Number(marineHourly.ocean_current_velocity?.[marineIndex]);
      const hourlyCurrentMs = marineHourlyUnits.ocean_current_velocity === 'km/h'
        ? hourlyCurrent / 3.6
        : hourlyCurrent;
      const values = [
        weatherHourly.wind_speed_10m?.[weatherIndex],
        weatherHourly.wind_direction_10m?.[weatherIndex],
        hourlyCurrentMs,
        marineHourly.ocean_current_direction?.[marineIndex],
        marineHourly.wave_height?.[marineIndex],
        marineHourly.wave_period?.[marineIndex],
        marineHourly.wave_direction?.[marineIndex],
      ].map(Number);
      if (!values.every(Number.isFinite)) return null;
      return {
        time_utc: `${time}:00Z`,
        wind: { speed_m_s: values[0], direction_deg: values[1] },
        current: { speed_m_s: values[2], direction_deg: values[3] },
        waves: {
          significant_height_m: values[4],
          period_s: values[5],
          direction_deg: values[6],
        },
      };
    }).filter(Boolean);

    return {
      timestamp_utc: timestamp.endsWith('Z') || timestamp.includes('+') ? timestamp : `${timestamp}:00Z`,
      source: 'Open-Meteo weather + marine best match',
      wind: {
        speed_ms: Number(current.wind_speed_10m),
        speed_kn: Number(current.wind_speed_10m) * 1.94384,
        direction_deg: Number(current.wind_direction_10m),
        gust_speed_ms: Number(current.wind_gusts_10m),
      },
      waves: {
        significant_height_m: Number(marine.wave_height),
        period_s: Number(marine.wave_period),
        direction_deg: Number(marine.wave_direction),
        direction_source: 'Open-Meteo marine model',
      },
      ocean: {
        water_temp_c: Number(marine.sea_surface_temperature),
        current_speed_ms: currentSpeedMs,
        current_dir_deg: Number(marine.ocean_current_direction),
      },
      air: {
        temp_c: Number(current.temperature_2m),
        apparent_temp_c: Number(current.apparent_temperature),
        humidity_pct: Number(current.relative_humidity_2m),
        pressure_hpa: Number(current.surface_pressure),
        visibility_km: Number(current.visibility) / 1000,
        cloud_cover_pct: Number(current.cloud_cover),
        precipitation_mm: Number(current.precipitation),
        weather_code: Number(current.weather_code),
        is_day: Number(current.is_day) === 1,
      },
      environmental_model: {
        kind: 'modelled-current-conditions',
        weather_resolution: 'best-match',
        marine_resolution: '5–9 km nominal',
        navigation_use: false,
      },
      forecast_frames: forecastFrames,
    };
  } finally {
    window.clearTimeout(timer);
  }
}

function mergeEnvironment(base, realtime) {
  if (!realtime) return base;
  return {
    ...base,
    ...realtime,
    wind: { ...(base?.wind || {}), ...realtime.wind },
    waves: { ...(base?.waves || {}), ...realtime.waves },
    ocean: { ...(base?.ocean || {}), ...realtime.ocean },
    air: { ...(base?.air || {}), ...realtime.air },
  };
}

function sceneEnvironmentSnapshot(weather) {
  if (!weather) return null;
  const windSpeed = Number(weather.wind?.speed_ms);
  const windDirection = Number(weather.wind?.direction_deg);
  const currentSpeed = Number(weather.ocean?.current_speed_ms);
  const currentDirection = Number(weather.ocean?.current_dir_deg);
  const waveHeight = Number(weather.waves?.significant_height_m);
  const wavePeriod = Number(weather.waves?.period_s);
  const waveDirection = Number(weather.waves?.direction_deg);
  if (![windSpeed, windDirection, currentSpeed, currentDirection, waveHeight, wavePeriod]
    .every(Number.isFinite)) return null;
  const hasWaveDirection = Number.isFinite(waveDirection);
  return {
    observed_at: weather.timestamp_utc || new Date().toISOString(),
    wind: {
      speed_m_s: Math.max(0, windSpeed),
      direction_deg: ((windDirection % 360) + 360) % 360,
      direction_convention: 'from',
      source: weather.source || 'environmental feed',
    },
    current: {
      speed_m_s: Math.max(0, currentSpeed),
      direction_deg: ((currentDirection % 360) + 360) % 360,
      direction_convention: 'to',
      source: weather.source || 'environmental feed',
    },
    waves: {
      significant_height_m: Math.max(0, waveHeight),
      period_s: Math.max(.1, wavePeriod),
      direction_deg: hasWaveDirection
        ? ((waveDirection % 360) + 360) % 360
        : ((windDirection % 360) + 360) % 360,
      direction_convention: 'from',
      direction_source: hasWaveDirection
        ? 'directional-wave-product'
        : 'wind-proxy',
    },
  };
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
const UNREAL_PIXEL_STREAM_URL = String(import.meta.env.VITE_UNREAL_PIXEL_STREAM_URL || '').trim();

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
  const [sidebarOpen, setSidebarOpen] = useState(isPublicLiveHost);
  const [activePanel, setActivePanel] = useState(
    isPublicLiveHost ? 'osint' : APP_PROFILE === 'demo' ? 'sim' : 'live',
  );
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
  const [play3D, setPlay3D] = useState(APP_PROFILE === 'demo');
  const [playRenderer, setPlayRenderer] = useState('cesium');
  const [playSimulationOpen, setPlaySimulationOpen] = useState(false);
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
  const [conePanelHidden, setConePanelHidden] = useState(false);
  const [showScenario, setShowScenario] = useState(false);
  const [scenarioType, setScenarioType] = useState('distress');
  const [caseEventId, setCaseEventId] = useState(null);
  const [simHistory, setSimHistory] = useState(loadStoredSimulations);
  const [activeScenario, setActiveScenario] = useState(null);
  const [activeSimId, setActiveSimId] = useState(null);
  const [intelEvents, setIntelEvents] = useState(() => {
    try {
      const cacheKey = isPublicLiveHost ? 'seacommons_live_signal_cache_v2' : 'seacommons_intel_cache';
      const cached = window.localStorage.getItem(cacheKey);
      if (cached) {
        const maxAgeDays = 30;
        const cutoff = new Date(Date.now() - maxAgeDays * 24 * 60 * 60 * 1000).toISOString();
        const parsed = JSON.parse(cached);
        const recent = parsed.filter(e => (e.properties?.timestamp_utc || '') >= cutoff);
        return isPublicLiveHost ? receivedSignalFeatures(recent) : recent;
      }
    } catch { /* ignore */ }
    return [];
  });
  const [intelDrifts, setIntelDrifts] = useState({ type: 'FeatureCollection', features: [] });
  const [browserLiveDrifts, setBrowserLiveDrifts] = useState({ type: 'FeatureCollection', features: [] });
  const [liveEstimateClock, setLiveEstimateClock] = useState(Date.now());
  const [intelConnected, setIntelConnected] = useState(false);
  const [intelMode, setIntelMode] = useState('offline'); // 'ws' | 'poll' | 'offline'
  const [intelFilter, setIntelFilter] = useState('all');
  const [showAisAlerts, setShowAisAlerts] = useState(false);
  const [showVesselLinks, setShowVesselLinks] = useState(false);
  const [layerVis, setLayerVis] = useState(() => {
    try {
      const saved = JSON.parse(window.localStorage.getItem('seacommons_layer_vis') || '{}');
      return { vessels: true, weather: true, intel: true, platforms: true, alerts: true, ...saved };
    } catch {
      return { vessels: true, weather: true, intel: true, platforms: true, alerts: true };
    }
  });
  const [triggeringDrift, setTriggeringDrift] = useState(() => new Set());
  const caseEventIdRef = useRef(null);
  const caseStatusRef = useRef('idle');
  const simParamsRef = useRef({});
  const intelWsRef = useRef(null);
  const liveTrackingRunsRef = useRef(new Map());
  const [form, setForm] = useState({
    lat: APP_PROFILE === 'demo' ? '35.52' : '',
    lon: APP_PROFILE === 'demo' ? '14.08' : '',
    persons: '1',
    vessel_type: 'rubber_boat',
    risk_level: 'high',
  });

  const mapNodeRef = useRef(null);
  const mapRef = useRef(null);
  const liveSignalsFramedRef = useRef(false);
  const selectionModeRef = useRef(false);
  const activePanelRef = useRef(isPublicLiveHost ? 'osint' : APP_PROFILE === 'demo' ? 'sim' : 'live');

  const selectedLat = parseFloat(form.lat);
  const selectedLon = parseFloat(form.lon);
  const displayedIntelDrifts = useMemo(
    () => mergeLiveDrifts(
      intelDrifts,
      browserLiveDrifts,
      intelEvents,
      new Date(liveEstimateClock),
    ),
    [intelDrifts, browserLiveDrifts, intelEvents, liveEstimateClock],
  );

  useEffect(() => {
    if (mapPanel?.type === 'cone') setConePanelHidden(false);
  }, [mapPanel]);

  // Mobile: the drift cone panel and the dashboard sheet are both bottom sheets,
  // so they must be mutually exclusive — opening the cone closes the dashboard.
  const coneVisible = mapPanel?.type === 'cone' && !conePanelHidden;
  useEffect(() => {
    if (coneVisible && window.matchMedia('(max-width: 680px)').matches) {
      setSidebarOpen(false);
    }
  }, [coneVisible]);

  function pushCaseLog(message) {
    setCaseLog((cur) => [
      { id: `${Date.now()}-${Math.random()}`, message, at: new Date().toISOString() },
      ...cur,
    ].slice(0, 20));
  }

  async function loadWeatherFor(lat, lon) {
    const [baseResult, realtimeResult] = await Promise.allSettled([
      fetchJson(
        apiBase,
        `/api/v1/weather?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}`,
      ),
      fetchOpenMeteoEnvironment(lat, lon),
    ]);
    if (baseResult.status === 'rejected' && realtimeResult.status === 'rejected') {
      throw baseResult.reason;
    }
    const payload = mergeEnvironment(
      baseResult.status === 'fulfilled' ? baseResult.value : {},
      realtimeResult.status === 'fulfilled' ? realtimeResult.value : null,
    );
    setWeather(payload);
    pushCaseLog(`Weather ${payload.source} @ ${Number(lat).toFixed(3)}, ${Number(lon).toFixed(3)}`);
    return payload;
  }

  async function loadWeatherGridForMap(map) {
    if (!map) return;   // guard: button can be pressed before map init completes
    if (map.getZoom() < 4) return;  // world/globe view — a 4x4 grid over the planet is meaningless
    const bounds = map.getBounds();
    const payload = await fetchJson(
      apiBase,
      `/api/v1/weather/grid?lat_min=${bounds.getSouth().toFixed(3)}&lat_max=${bounds.getNorth().toFixed(3)}&lon_min=${bounds.getWest().toFixed(3)}&lon_max=${bounds.getEast().toFixed(3)}&n=4`,
      undefined,
      25000,  // 25s — backend batch timeout is 20s + network headroom
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
  // Start REST polling immediately so data flows on first load. The dedicated
  // api.seacommons.org endpoint supports WebSocket upgrades; if the upgrade
  // fails, polling remains active.
  useEffect(() => {
    const wsBase = apiBase.replace(/^http/, 'ws');
    const feedPath = isPublicLiveHost
      ? '/api/v1/live/signals?limit=500&days=30'
      : '/api/v1/intel?limit=200&days=30';
    const streamPath = isPublicLiveHost ? '/api/v1/live/stream' : '/ws/intel';
    const pollIntervalMs = isPublicLiveHost ? 10000 : 30000;
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
          setIntelEvents(isPublicLiveHost ? receivedSignalFeatures(msg.features) : (msg.features || []));
        } else if (msg.type === 'Feature') {
          const incoming = isPublicLiveHost ? receivedSignalFeatures([msg]) : [msg];
          if (!incoming.length) return;
          setIntelEvents((prev) => [...incoming, ...prev].slice(0, 300));
          const mp = msg.properties || {};
          if (mp.type === 'distress' && ['critical', 'high'].includes(mp.severity)) {
            setActivePanel('osint');
            setSidebarOpen(true);
          }
        } else if (!isPublicLiveHost && msg.type === 'event_update' && msg.drift?.trajectory) {
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
        const data = await fetchJson(apiBase, feedPath);
        if (!alive) return;
        if (data.features) {
          const features = isPublicLiveHost ? receivedSignalFeatures(data.features) : data.features;
          setIntelEvents(features);
          const cacheKey = isPublicLiveHost ? 'seacommons_live_signal_cache_v2' : 'seacommons_intel_cache';
          try { window.localStorage.setItem(cacheKey, JSON.stringify(features)); } catch { /* quota */ }
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
        await new Promise((res) => { pollTimer = window.setTimeout(res, pollIntervalMs); });
      }
      polling = false;
    }

    function tryWs() {
      if (!alive || !wsAlive) return;
      const token = window.__SEACOMMONS_ACCESS_TOKEN__;
      ws = token
        ? new WebSocket(`${wsBase}${streamPath}`, ['bearer', token])
        : new WebSocket(`${wsBase}${streamPath}`);
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
    // A distinct API origin is a direct reverse-proxy endpoint and supports the
    // WebSocket upgrade. Same-origin CDN deployments retain REST polling only.
    const apiHost = apiBase.replace(/^https?:\/\//, '').split('/')[0];
    const isDirectBackend = apiBase !== window.location.origin
      || /^(localhost|127\.|192\.168\.|10\.|172\.(1[6-9]|2\d|3[01])\.)/.test(apiHost)
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

  // Alarm Phone live tracking runs independently in the browser. It consumes
  // hourly historical/current weather and marine fields, so an old report is
  // never advanced using a present-only field relabelled as historical data.
  useEffect(() => {
    if (!isPublicLiveHost) return undefined;
    const candidates = liveTrackingCandidates(intelEvents, new Date(), 48).slice(0, 12);
    for (const signal of candidates) {
      const properties = signal.properties || {};
      const coordinates = signal.geometry.coordinates;
      const id = String(properties.id || signal.id || '').replace(/^intel:/, '');
      const runKey = `${id}:${coordinates[0]}:${coordinates[1]}:${properties.timestamp_utc}`;
      const previousRun = liveTrackingRunsRef.current.get(runKey);
      if (previousRun === 'running' || previousRun === 'completed') continue;
      if (Number.isFinite(previousRun) && Date.now() - previousRun < 5 * 60_000) continue;
      liveTrackingRunsRef.current.set(runKey, 'running');
      (async () => {
        try {
          const environment = await fetchOpenMeteoEnvironment(coordinates[1], coordinates[0]);
          const snapshot = buildEnvironmentSnapshot(environment, coordinates[1], coordinates[0]);
          const elapsedHours = Math.max(
            0,
            (Date.now() - Date.parse(properties.timestamp_utc)) / 3_600_000,
          );
          const result = await computeDriftInWorker({
            scenario: {
              scenario_id: `live-${id}`,
              observed_at: properties.timestamp_utc,
              origin: { lat: Number(coordinates[1]), lon: Number(coordinates[0]) },
              subject: { kind: 'rubber_boat', persons: 1 },
            },
            environmentSnapshot: snapshot,
            options: {
              duration_hours: Math.min(72, Math.max(24, Math.ceil(elapsedHours) + 12)),
              particles: 64,
            },
          });
          const decorated = decorateLiveTracking(result, signal);
          setBrowserLiveDrifts((previous) => ({
            type: 'FeatureCollection',
            features: [
              ...(previous.features || []).filter(
                (feature) => String(feature.properties?.intel_event_id || '').replace(/^intel:/, '') !== id,
              ),
              ...decorated.features,
            ],
          }));
          liveTrackingRunsRef.current.set(runKey, 'completed');
        } catch {
          // A provider/network failure is retried after five minutes. No
          // synthetic or straight-line fallback is drawn on the map.
          liveTrackingRunsRef.current.set(runKey, Date.now());
        }
      })();
    }
    return undefined;
  }, [intelEvents]);

  useEffect(() => {
    if (!isPublicLiveHost) return undefined;
    const timer = window.setInterval(() => setLiveEstimateClock(Date.now()), 30_000);
    return () => window.clearInterval(timer);
  }, []);

  // ── Intel drift traces polling ───────────────────────────────────────────────
  useEffect(() => {
    let alive = true;
    let driftTimer = null;
    async function loadDrifts() {
      try {
        const path = isPublicLiveHost ? '/api/v1/live/drifts' : '/api/v1/intel/drifts';
        const data = await fetchJson(apiBase, path);
        if (alive && data.features) setIntelDrifts(data);
      } catch { /* ignore */ }
      if (alive) {
        driftTimer = window.setTimeout(loadDrifts, isPublicLiveHost ? 30_000 : 120_000);
      }
    }
    loadDrifts();
    return () => {
      alive = false;
      window.clearTimeout(driftTimer);
    };
  }, [apiBase]);

  useEffect(() => {
    if (isPublicLiveHost) return;
    fetchJson(apiBase, '/api/v1/zones/platforms')
      .then(d => { if (d.features) setPlatforms(d); })
      .catch(() => {});
  }, [apiBase]);

  // ── Rehydrate case history from the DB (survives page refresh) ──────────────
  // GeoJSON is loaded lazily on "Show" to keep the initial payload small.
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const data = await fetchJson(
          apiBase,
          APP_PROFILE === 'demo' ? '/api/v1/live/archives' : '/api/v1/alerts',
        );
        const records = Array.isArray(data) ? data : data?.archives;
        if (!alive || !Array.isArray(records)) return;
        const completed = APP_PROFILE === 'demo'
          ? records.slice(0, 8)
          : records.filter((alert) => alert.status === 'completed').slice(0, 8);
        if (!completed.length) return;
        setSimHistory((prev) => {
          const known = new Set(prev.map((s) => s.id));
          const restored = completed
            .filter((archive) => !known.has(archive.id || archive.event_id))
            .map((archive) => {
              const event = archive.event || archive;
              return {
              id: archive.id || archive.event_id,
              label: `${(event.vessel_type || 'case').replace(/_/g, ' ')} @ ${Number(event.lat).toFixed(3)}, ${Number(event.lon).toFixed(3)}`,
              ts: event.timestamp || new Date().toISOString(),
              geojson: null,   // fetched on first replay
              lat: Number(event.lat),
              lon: Number(event.lon),
              params: { vesselType: event.vessel_type, persons: event.persons },
            };
            });
          return [...prev, ...restored].slice(0, 10);
        });
      } catch { /* backend cold — history stays session-only */ }
    })();
    return () => { alive = false; };
  }, [apiBase]);

  useEffect(() => {
    if (isPublicLiveHost || isPublicDemoHost) return undefined;
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
    map.getCanvas().style.cursor = APP_PROFILE === 'demo' && (activePanel === 'sim' || selectionMode)
      ? 'crosshair'
      : '';
  }, [activePanel, selectionMode, mapReady]);

  useEffect(() => {
    const map = mapRef.current;
    if (!isPublicLiveHost || !map || !mapReady || window.innerWidth <= 820) return;
    map.easeTo({
      padding: { top: 0, right: 0, bottom: 0, left: sidebarOpen ? 392 : 0 },
      duration: 420,
      essential: true,
    });
  }, [sidebarOpen, mapReady]);

  useEffect(() => {
    const map = mapRef.current;
    const features = intelEvents || [];
    if (!isPublicLiveHost || !map || !mapReady || liveSignalsFramedRef.current || !features.length) return;
    let west = Infinity;
    let south = Infinity;
    let east = -Infinity;
    let north = -Infinity;
    let coordinateCount = 0;
    const extendCoordinates = (coordinates) => {
      if (!Array.isArray(coordinates)) return;
      if (
        coordinates.length >= 2
        && Number.isFinite(Number(coordinates[0]))
        && Number.isFinite(Number(coordinates[1]))
      ) {
        const longitude = Number(coordinates[0]);
        const latitude = Number(coordinates[1]);
        if (longitude < -6 || longitude > 37 || latitude < 28 || latitude > 47) return;
        west = Math.min(west, longitude);
        south = Math.min(south, latitude);
        east = Math.max(east, longitude);
        north = Math.max(north, latitude);
        coordinateCount += 1;
        return;
      }
      coordinates.forEach(extendCoordinates);
    };
    features.forEach((feature) => extendCoordinates(feature.geometry?.coordinates));
    if (coordinateCount < 2 || ![west, south, east, north].every(Number.isFinite)) return;
    liveSignalsFramedRef.current = true;
    map.fitBounds([[west, south], [east, north]], {
      padding: window.innerWidth > 820
        ? { top: 100, right: 100, bottom: 100, left: sidebarOpen ? 470 : 100 }
        : { top: 110, right: 38, bottom: 90, left: 38 },
      maxZoom: 7.2,
      duration: 1100,
      essential: true,
    });
  }, [intelEvents, mapReady, sidebarOpen]);

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
        center: APP_PROFILE === 'live' ? [15.2, 36.1] : [14.3, 31.0],
        zoom: APP_PROFILE === 'live' ? 4.15 : 1.9,
        padding: isPublicLiveHost && window.innerWidth > 820
          ? { top: 0, right: 0, bottom: 0, left: 392 }
          : 0,
        attributionControl: true,
      });

      // ── Globe intro: 3D globe that flattens to 2D as you zoom in ──────────
      map.on('style.load', () => {
        try { map.setProjection({ type: 'globe' }); } catch { /* projection unsupported — flat fallback */ }
      });

      // Slow rotation until the first user interaction
      let spinning = APP_PROFILE !== 'live';
      const SPIN_DEG_PER_STEP = 8;
      const SPIN_STEP_MS = 6000;
      function spinStep() {
        if (!spinning) return;
        const c = map.getCenter();
        map.easeTo({
          center: [c.lng - SPIN_DEG_PER_STEP, c.lat],
          duration: SPIN_STEP_MS,
          easing: (t) => t,
        });
      }
      function stopSpin() {
        if (!spinning) return;
        spinning = false;
        map.stop();
      }
      map.on('moveend', () => { if (spinning) spinStep(); });
      for (const ev of ['mousedown', 'wheel', 'touchstart', 'dragstart', 'pitchstart']) {
        map.on(ev, stopSpin);
      }

      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
      map.addControl(new maplibregl.GeolocateControl({
        positionOptions: { enableHighAccuracy: true },
        trackUserLocation: true,
        showUserHeading: true,
      }), 'top-right');
      map.addControl(new maplibregl.ScaleControl({ maxWidth: 110, unit: 'nautical' }), 'bottom-right');

      liveMap = map;

      let weatherTimer = null;
      map.on('moveend', () => {
        if (isPublicLiveHost) return;
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
        map.addSource('intel-distress',    { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        map.addSource('intel-archived',    { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        map.addSource('intel-drifts',      { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        map.addSource('intel-vessel-links', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        map.addSource('live-nearby-vessels', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });

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
              'critical', isPublicLiveHost ? 'rgba(255,59,59,0.15)' : 'rgba(255,59,59,0.08)',
              'high',     isPublicLiveHost ? 'rgba(255,123,84,0.14)' : 'rgba(255,123,84,0.07)',
                          isPublicLiveHost ? 'rgba(92,255,215,0.12)' : 'rgba(139,240,197,0.05)'],
            'fill-outline-color': ['match', ['get', 'intel_severity'],
              'critical', isPublicLiveHost ? 'rgba(255,90,74,0.62)' : 'rgba(255,59,59,0.28)',
              'high',     isPublicLiveHost ? 'rgba(255,150,100,0.58)' : 'rgba(255,123,84,0.22)',
                          isPublicLiveHost ? 'rgba(92,255,215,0.52)' : 'rgba(139,240,197,0.18)'],
          },
        });
        map.addLayer({
          id: 'intel-drift-line', type: 'line', source: 'intel-drifts',
          filter: ['==', '$type', 'LineString'],
          paint: {
            'line-color': ['match', ['get', 'intel_severity'],
              'critical', isPublicLiveHost ? 'rgba(255,72,62,0.94)' : 'rgba(255,59,59,0.55)',
              'high',     isPublicLiveHost ? 'rgba(255,132,84,0.92)' : 'rgba(255,123,84,0.50)',
                          isPublicLiveHost ? 'rgba(92,255,215,0.88)' : 'rgba(139,240,197,0.40)'],
            'line-width': isPublicLiveHost ? 2.4 : 1.5,
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
          filter: ['all', ['==', ['geometry-type'], 'LineString'], ['==', ['get', 'type'], 'trajectory']],
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
          filter: ['all', ['==', '$type', 'Point'], ['!=', ['get', 'type'], 'current_estimate']],
          paint: {
            'circle-radius': 4,
            'circle-color': ['match', ['get', 'intel_severity'],
              'critical', '#ff3b3b', 'high', '#ff7b54', '#8bf0c5'],
            'circle-opacity': 0.78,
            'circle-stroke-width': 1,
            'circle-stroke-color': '#04131a',
          },
        });
        map.addLayer({
          id: 'intel-current-estimate-halo', type: 'circle', source: 'intel-drifts',
          filter: ['all', ['==', '$type', 'Point'], ['==', ['get', 'type'], 'current_estimate']],
          paint: {
            'circle-radius': 13,
            'circle-color': 'rgba(255,224,109,.18)',
            'circle-blur': .65,
          },
        });
        map.addLayer({
          id: 'intel-current-estimate', type: 'circle', source: 'intel-drifts',
          filter: ['all', ['==', '$type', 'Point'], ['==', ['get', 'type'], 'current_estimate']],
          paint: {
            'circle-radius': 6,
            'circle-color': '#ffe06d',
            'circle-opacity': .96,
            'circle-stroke-width': 2,
            'circle-stroke-color': '#201b08',
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

        // Area indicator: when a report only carries a place/region centroid
        // (no exact position), show a real-world-scaled translucent circle
        // instead of a pin that implies false precision. Radius tracks
        // location_uncertainty_m in meters (not screen pixels) via the
        // standard MapLibre meters→pixels-per-zoom conversion.
        map.addLayer({
          id: 'intel-distress-area', type: 'circle', source: 'intel-distress',
          filter: ['>', ['coalesce', ['get', 'location_uncertainty_m'], 0], 20000],
          paint: {
            'circle-radius': METERS_TO_PX_RADIUS,
            'circle-color': 'rgba(255,59,59,0.10)',
            'circle-stroke-color': 'rgba(255,80,80,0.4)',
            'circle-stroke-width': 1,
          },
        });

        // ── Operational distress beacons — pulsing rings, topmost priority ──
        // Two concentric circle layers; the outer radius is animated in a
        // requestAnimationFrame loop (see distressPulse below).
        map.addLayer({
          id: 'intel-distress-pulse', type: 'circle', source: 'intel-distress',
          paint: {
            'circle-radius': 8,
            'circle-color': 'rgba(255,59,59,0.18)',
            'circle-stroke-color': 'rgba(255,80,80,0.9)',
            'circle-stroke-width': 1.5,
          },
        });
        map.addLayer({
          id: 'intel-distress-core', type: 'circle', source: 'intel-distress',
          paint: {
            'circle-radius': 5,
            'circle-color': '#ff3b3b',
            'circle-stroke-width': 1.5,
            'circle-stroke-color': '#fff4bf',
          },
        });
        const distressHoverPopup = new maplibregl.Popup({
          closeButton: false, closeOnClick: false, offset: 10,
          className: 'intel-hover-popup',
        });
        map.on('mouseenter', 'intel-distress-core', () => { map.getCanvas().style.cursor = 'pointer'; });
        map.on('mousemove', 'intel-distress-core', (event) => {
          const feature = event.features?.[0];
          if (!feature) return;
          const [lon, lat] = feature.geometry.coordinates;
          distressHoverPopup
            .setLngLat([lon, lat])
            .setHTML(`<strong>${lat.toFixed(4)}, ${lon.toFixed(4)}</strong>`)
            .addTo(map);
        });
        map.on('mouseleave', 'intel-distress-core', () => {
          map.getCanvas().style.cursor = APP_PROFILE === 'demo' && (activePanelRef.current === 'sim' || selectionModeRef.current) ? 'crosshair' : '';
          distressHoverPopup.remove();
        });
        map.on('click', 'intel-distress-core', (event) => {
          const feature = event.features?.[0];
          if (!feature) return;
          const [lon, lat] = feature.geometry.coordinates;
          map.flyTo({ center: [lon, lat], zoom: 9, duration: 800 });
          setActivePanel('osint');
          if (!window.matchMedia('(max-width: 680px)').matches) setSidebarOpen(true);
          const props = feature.properties || {};
          if (!isPublicLiveHost && props.id
              && props.drift_status !== 'completed' && props.drift_status !== 'computing') {
            triggerIntelDrift(props.id, lat, lon);
          }
          event.originalEvent?.stopPropagation?.();
        });

        // Pulse animation: oscillate the outer ring radius/opacity ~1.4s
        let pulseRaf = null;
        const pulseStart = performance.now();
        function distressPulse(now) {
          if (!map.getLayer('intel-distress-pulse')) return;
          const elapsed = Math.max(0, now - pulseStart);
          const t = (elapsed % 1400) / 1400;                  // 0..1
          const r = 8 + 14 * t;                               // grow ring
          const o = 0.45 * (1 - t);                           // fade out
          map.setPaintProperty('intel-distress-pulse', 'circle-radius', r);
          map.setPaintProperty('intel-distress-pulse', 'circle-color', `rgba(255,59,59,${o})`);
          map.setPaintProperty('intel-distress-pulse', 'circle-stroke-opacity', Math.min(1, Math.max(0, 1 - t)));
          pulseRaf = requestAnimationFrame(distressPulse);
        }
        pulseRaf = requestAnimationFrame(distressPulse);
        map.once('remove', () => { if (pulseRaf) cancelAnimationFrame(pulseRaf); });

        // ── Archived distress — resolved or aged out, kept readable but muted.
        // No pulse: this is history, not something demanding attention now.
        map.addLayer({
          id: 'intel-archived-area', type: 'circle', source: 'intel-archived',
          filter: ['>', ['coalesce', ['get', 'location_uncertainty_m'], 0], 20000],
          paint: {
            'circle-radius': METERS_TO_PX_RADIUS,
            'circle-color': 'rgba(180,180,190,0.08)',
            'circle-stroke-color': 'rgba(180,180,190,0.3)',
            'circle-stroke-width': 1,
          },
        });
        map.addLayer({
          id: 'intel-archived-layer', type: 'circle', source: 'intel-archived',
          paint: {
            'circle-radius': 4,
            'circle-color': '#9aa0ab',
            'circle-opacity': 0.75,
            'circle-stroke-width': 1,
            'circle-stroke-color': '#2a2e35',
          },
        });
        const archivedHoverPopup = new maplibregl.Popup({
          closeButton: false, closeOnClick: false, offset: 10,
          className: 'intel-hover-popup',
        });
        map.on('mouseenter', 'intel-archived-layer', () => { map.getCanvas().style.cursor = 'pointer'; });
        map.on('mousemove', 'intel-archived-layer', (event) => {
          const feature = event.features?.[0];
          if (!feature) return;
          const [lon, lat] = feature.geometry.coordinates;
          const props = feature.properties || {};
          archivedHoverPopup
            .setLngLat([lon, lat])
            .setHTML(`<strong>Archived</strong><br/>${props.title || ''}`)
            .addTo(map);
        });
        map.on('mouseleave', 'intel-archived-layer', () => {
          map.getCanvas().style.cursor = APP_PROFILE === 'demo' && (activePanelRef.current === 'sim' || selectionModeRef.current) ? 'crosshair' : '';
          archivedHoverPopup.remove();
        });
        map.on('click', 'intel-archived-layer', (event) => {
          const feature = event.features?.[0];
          if (!feature) return;
          const [lon, lat] = feature.geometry.coordinates;
          map.flyTo({ center: [lon, lat], zoom: 9, duration: 800 });
          setActivePanel('osint');
          if (!window.matchMedia('(max-width: 680px)').matches) setSidebarOpen(true);
          event.originalEvent?.stopPropagation?.();
        });

        // Vessels reported near an active Live distress point (AIS, refreshed
        // periodically — see the liveNearbyVessels effect below).
        map.addLayer({
          id: 'live-nearby-vessels-halo', type: 'circle', source: 'live-nearby-vessels',
          paint: { 'circle-radius': 11, 'circle-color': 'rgba(56,189,248,0.22)', 'circle-blur': 0.8 },
        });
        map.addLayer({
          id: 'live-nearby-vessels-layer', type: 'symbol', source: 'live-nearby-vessels',
          layout: {
            'icon-image': 'vessel-arrow',
            'icon-size': 0.48,
            'icon-rotate': ['coalesce', ['get', 'course'], 0],
            'icon-rotation-alignment': 'map',
            'icon-allow-overlap': true,
            'icon-ignore-placement': true,
          },
          paint: {
            'icon-color': '#38bdf8',
            'icon-halo-color': '#03212e',
            'icon-halo-width': 1.6,
          },
        });
        const liveVesselPopup = new maplibregl.Popup({
          closeButton: false, closeOnClick: false, offset: 10,
          className: 'intel-hover-popup',
        });
        map.on('mouseenter', 'live-nearby-vessels-layer', () => { map.getCanvas().style.cursor = 'pointer'; });
        map.on('mousemove', 'live-nearby-vessels-layer', (event) => {
          const feature = event.features?.[0];
          if (!feature) return;
          const [lon, lat] = feature.geometry.coordinates;
          const props = feature.properties || {};
          liveVesselPopup
            .setLngLat([lon, lat])
            .setHTML(`<strong>${props.ship_name || 'Vessel'}</strong><br/>${props.distance_km ?? '?'} km from distress`)
            .addTo(map);
        });
        map.on('mouseleave', 'live-nearby-vessels-layer', () => {
          map.getCanvas().style.cursor = APP_PROFILE === 'demo' && (activePanelRef.current === 'sim' || selectionModeRef.current) ? 'crosshair' : '';
          liveVesselPopup.remove();
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

        // Hover popup — shows the event's coordinates without needing to open the sidebar.
        const intelHoverPopup = new maplibregl.Popup({
          closeButton: false, closeOnClick: false, offset: 10,
          className: 'intel-hover-popup',
        });
        map.on('mouseenter', 'intel-events-layer', () => { map.getCanvas().style.cursor = 'pointer'; });
        map.on('mousemove', 'intel-events-layer', (event) => {
          const feature = event.features?.[0];
          if (!feature) return;
          const [lon, lat] = feature.geometry.coordinates;
          intelHoverPopup
            .setLngLat([lon, lat])
            .setHTML(`<strong>${lat.toFixed(4)}, ${lon.toFixed(4)}</strong>`)
            .addTo(map);
        });
        map.on('mouseleave', 'intel-events-layer', () => {
          map.getCanvas().style.cursor = APP_PROFILE === 'demo' && (activePanelRef.current === 'sim' || selectionModeRef.current) ? 'crosshair' : '';
          intelHoverPopup.remove();
        });
        map.on('click', 'intel-events-layer', (event) => {
          const feature = event.features?.[0];
          if (!feature) return;
          const [lon, lat] = feature.geometry.coordinates;
          map.flyTo({ center: [lon, lat], zoom: 9, duration: 800 });
          setActivePanel('osint');
          // On mobile the sheet would cover the point we just flew to — keep map visible.
          if (!window.matchMedia('(max-width: 680px)').matches) setSidebarOpen(true);
          const props = feature.properties || {};
          if (props.id && props.drift_status !== 'completed' && props.drift_status !== 'computing') {
            triggerIntelDrift(props.id, lat, lon);
          }
          event.originalEvent?.stopPropagation?.();
        });
        map.on('mouseenter', 'intel-drift-line', () => { map.getCanvas().style.cursor = 'pointer'; });
        map.on('mouseleave', 'intel-drift-line', () => {
          map.getCanvas().style.cursor = APP_PROFILE === 'demo' && (activePanelRef.current === 'sim' || selectionModeRef.current) ? 'crosshair' : '';
        });
        map.on('click', 'intel-drift-line', (event) => {
          const feature = event.features?.[0];
          if (!feature) return;
          setMapPanel({
            type: 'trajectory',
            feature,
            caseStatus: feature.properties?.verification_status || 'modelled',
          });
          setConePanelHidden(false);
          event.originalEvent?.stopPropagation?.();
        });

        // vessel click (commercial + NGO share same handler)
        for (const lyr of ['vessels-layer', 'vessels-stationary', 'vessels-ngo', 'vessels-ngo-stationary', 'proximity-vessels-layer']) {
          map.on('mouseenter', lyr, () => { map.getCanvas().style.cursor = 'pointer'; });
          map.on('mouseleave', lyr, () => {
            map.getCanvas().style.cursor = APP_PROFILE === 'demo' && (activePanelRef.current === 'sim' || selectionModeRef.current) ? 'crosshair' : '';
          });
          map.on('click', lyr, (event) => {
            const feature = event.features?.[0];
            if (!feature) return;
            const [lon, lat] = feature.geometry.coordinates;
            setSelectedVessel({ ...feature.properties, lon, lat });
            // Vessel details render as a map overlay card — opening the sheet on
            // mobile would hide both the vessel and its card.
            if (!window.matchMedia('(max-width: 680px)').matches) setSidebarOpen(true);
            event.originalEvent?.stopPropagation?.();
          });
        }

        // Drift cone click
        map.on('mouseenter', 'sar-case-cone', () => { map.getCanvas().style.cursor = 'pointer'; });
        map.on('mouseleave', 'sar-case-cone', () => {
          map.getCanvas().style.cursor = APP_PROFILE === 'demo' && (activePanelRef.current === 'sim' || selectionModeRef.current) ? 'crosshair' : '';
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
          map.getCanvas().style.cursor = APP_PROFILE === 'demo' && (activePanelRef.current === 'sim' || selectionModeRef.current) ? 'crosshair' : '';
        });
        map.on('click', 'sar-case-points', (event) => {
          const feature = event.features?.[0];
          if (feature) {
            setMapPanel({ type: 'cone', feature, eventId: caseEventIdRef.current, caseStatus: caseStatusRef.current, simParams: simParamsRef.current });
            event.originalEvent?.stopPropagation?.();
          }
        });

        map.on('mousemove', (event) => {
          if (APP_PROFILE !== 'demo' || (activePanelRef.current !== 'sim' && !selectionModeRef.current)) return;
          setCursorHint({ visible: true, x: event.point.x, y: event.point.y });
        });
        map.on('mouseleave', () => {
          setCursorHint((cur) => ({ ...cur, visible: false }));
        });

        map.on('click', (event) => {
          // Globe intro: at world zoom a click dives into the Mediterranean
          // instead of opening the SAR scenario modal.
          if (map.getZoom() < 4.5) {
            stopSpin();
            map.flyTo({ center: [14.3, 35.8], zoom: 6.3, duration: 2400, essential: true });
            return;
          }
          if (isPublicLiveHost) return;
          const hit = map.queryRenderedFeatures(event.point, {
            layers: ['sar-case-cone', 'sar-case-points', 'vessels-layer', 'vessels-stationary', 'vessels-ngo', 'vessels-ngo-stationary', 'proximity-vessels-layer', 'intel-events-layer'],
          });
          if (hit.length > 0) return;

          const nextLat = event.lngLat.lat.toFixed(5);
          const nextLon = event.lngLat.lng.toFixed(5);
          setForm((cur) => ({ ...cur, lat: nextLat, lon: nextLon }));
          setSelectionMode(false);
          setCursorHint({ visible: false, x: 0, y: 0 });
          if (APP_PROFILE === 'demo' && (activePanelRef.current === 'sim' || selectionModeRef.current)) {
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
        if (!isPublicLiveHost) loadWeatherGridForMap(map).catch(() => {});
        spinStep();   // begin the globe intro rotation
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

  // Layer group visibility — applied to every MapLibre layer in the group
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    for (const group of LAYER_GROUPS) {
      const enabled = isPublicLiveHost
        ? group.key === 'intel'
        : layerVis[group.key] !== false;
      const vis = enabled ? 'visible' : 'none';
      for (const id of group.layers) {
        if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', vis);
      }
    }
    try { window.localStorage.setItem('seacommons_layer_vis', JSON.stringify(layerVis)); } catch { /* quota */ }
  }, [layerVis, mapReady]);

  function toggleLayerGroup(key) {
    setLayerVis((cur) => ({ ...cur, [key]: cur[key] === false }));
  }

  // Intel events map layer — split into three buckets driven by the backend's
  // `kind`: "distress" (active, pulsing), "archived" (resolved/aged out —
  // kept visible but muted, never dropped), "context" (news, static).
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !map.isStyleLoaded()) return;
    const positioned = intelEvents.filter((f) => f.geometry?.coordinates);
    const kindOf = (f) => {
      const p = f.properties || {};
      if (p.kind === 'archived') return 'archived';
      if (p.kind === 'distress' || p.tier === 'operational' || p.type === 'distress') return 'distress';
      return 'context';
    };
    const distress = positioned.filter((f) => kindOf(f) === 'distress');
    const archived = positioned.filter((f) => kindOf(f) === 'archived');
    const bucketedIds = new Set([...distress, ...archived].map((f) => f.properties?.id));
    const others = positioned.filter((f) => !bucketedIds.has(f.properties?.id));
    map.getSource('intel-events')?.setData({ type: 'FeatureCollection', features: others });
    map.getSource('intel-distress')?.setData({ type: 'FeatureCollection', features: distress });
    map.getSource('intel-archived')?.setData({ type: 'FeatureCollection', features: archived });
  }, [intelEvents, mapReady]);

  // Live nearby vessels: AIS positions around each active distress point,
  // refreshed on an interval. /api/v1/vessels/nearest reads an already-cached
  // in-memory registry (no new AIS/network call per request), so this is
  // cheap even polled every few minutes — 3 min balances "feels live" against
  // request volume on the free-tier API box.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return undefined;
    const LIVE_VESSEL_REFRESH_MS = 3 * 60 * 1000;
    const MAX_DISTRESS_POINTS = 8;
    const VESSELS_PER_POINT = 4;
    let alive = true;
    let timer = null;

    async function refresh() {
      const points = intelEvents
        .filter((f) => {
          const p = f.properties || {};
          return (p.tier === 'operational' || p.type === 'distress') && f.geometry?.coordinates;
        })
        .slice(0, MAX_DISTRESS_POINTS);
      if (!points.length) {
        map.getSource('live-nearby-vessels')?.setData({ type: 'FeatureCollection', features: [] });
        return;
      }
      const results = await Promise.all(points.map(async (point) => {
        const [lon, lat] = point.geometry.coordinates;
        try {
          const data = await fetchJson(
            apiBase,
            `/api/v1/vessels/nearest?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}&limit=${VESSELS_PER_POINT}`,
            undefined,
            8000,
          );
          return (data?.vessels || []).map((v) => ({ ...v, distress_id: point.properties?.id }));
        } catch {
          return [];
        }
      }));
      if (!alive) return;
      const byMmsi = new Map();
      for (const vessel of results.flat()) {
        const key = vessel.mmsi || `${vessel.lat},${vessel.lon}`;
        const existing = byMmsi.get(key);
        if (!existing || (vessel.distance_km ?? Infinity) < (existing.distance_km ?? Infinity)) {
          byMmsi.set(key, vessel);
        }
      }
      const features = Array.from(byMmsi.values())
        .filter((v) => Number.isFinite(v.lat) && Number.isFinite(v.lon))
        .map((v) => ({
          type: 'Feature',
          geometry: { type: 'Point', coordinates: [v.lon, v.lat] },
          properties: {
            mmsi: v.mmsi, ship_name: v.ship_name, course: v.course,
            distance_km: v.distance_km, distress_id: v.distress_id,
          },
        }));
      map.getSource('live-nearby-vessels')?.setData({ type: 'FeatureCollection', features });
    }

    refresh();
    timer = window.setInterval(refresh, LIVE_VESSEL_REFRESH_MS);
    return () => { alive = false; if (timer) window.clearInterval(timer); };
  }, [intelEvents, mapReady, apiBase]);

  // Intel drift traces map layer
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !map.isStyleLoaded()) return;
    map.getSource('intel-drifts')?.setData(displayedIntelDrifts);
  }, [displayedIntelDrifts, mapReady]);

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
    if (isPublicLiveHost) {
      setVessels({ type: 'FeatureCollection', features: [] });
      setAlerts({ type: 'FeatureCollection', features: [] });
      setLoading(false);
      return undefined;
    }
    let alive = true;
    let running = false;           // guard: skip tick if previous loadAll still in flight
    let consecutiveErrors = 0;
    let lastVesselTs = null;       // ISO timestamp of last successful vessel fetch
    let vesselSnapshot = null;     // latest merged GeoJSON snapshot
    const seenAt = new Map();      // mmsi → epoch ms of last appearance in a feed diff
    const VESSEL_TTL_MS = 30 * 60 * 1000;  // drop vessels silent for 30 min

    async function fetchVessels() {
      // First call: full load. Subsequent: incremental diff via ?since=.
      const isFirst = !lastVesselTs;
      const url = lastVesselTs ? `/api/v1/vessels?since=${encodeURIComponent(lastVesselTs)}` : '/api/v1/vessels';
      const timeoutMs = isFirst ? 20000 : 12000;
      const data = await fetchJson(apiBase, url, undefined, timeoutMs);
      if (!data?.features) return;
      lastVesselTs = new Date().toISOString();
      const now = Date.now();
      data.features.forEach((f) => { if (f.properties?.mmsi) seenAt.set(f.properties.mmsi, now); });
      if (!vesselSnapshot) {
        vesselSnapshot = data;
      } else {
        const updated = new Map(data.features.map((f) => [f.properties?.mmsi, f]));
        const merged = vesselSnapshot.features.map((f) => updated.get(f.properties?.mmsi) || f);
        data.features.forEach((f) => { if (!vesselSnapshot.features.some((e) => e.properties?.mmsi === f.properties?.mmsi)) merged.push(f); });
        // Expire vessels not seen in any diff for VESSEL_TTL_MS — otherwise a
        // vessel that left the feed stays painted on the map until full reload.
        const fresh = merged.filter((f) => {
          const ts = seenAt.get(f.properties?.mmsi);
          return ts === undefined || (now - ts) < VESSEL_TTL_MS;
        });
        vesselSnapshot = { type: 'FeatureCollection', features: fresh };
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
      if (running) return;  // previous fetch still in flight — skip this tick
      running = true;
      try {
        const [vesselsPayload, alertsPayload] = await Promise.all([
          fetchVessels(),
          isPublicLiveHost
            ? Promise.resolve({ type: 'FeatureCollection', features: [] })
            : fetchJson(apiBase, '/api/v1/alerts/geojson'),
        ]);
        if (!alive) return;
        if (vesselsPayload) setVessels(vesselsPayload);
        setAlerts(alertsPayload);
        setError('');
        consecutiveErrors = 0;
      } catch (err) {
        if (!alive) return;
        consecutiveErrors += 1;
        // Only show error after 2 consecutive failures to avoid transient flicker
        if (consecutiveErrors >= 2) setError(err.message || 'Backend unreachable');
      } finally {
        running = false;
        if (alive) setLoading(false);
      }
      loadSummary();
    }
    loadAll();
    // 30s interval: vessels update on AIS heartbeat (~every 2 min) so 15s was wasteful
    const id = window.setInterval(loadAll, 30000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, [apiBase]);

  useEffect(() => {
    if (!Number.isFinite(selectedLat) || !Number.isFinite(selectedLon)) return;
    let cancelled = false;
    // Debounced: lat/lon also change on every keystroke in the manual inputs,
    // so wait for typing to settle before hitting /vessels/nearest.
    const timer = window.setTimeout(() => {
      loadNearestVessels(selectedLat, selectedLon).catch(() => {
        if (!cancelled) setNearestVessels([]);
      });
      loadWeatherFor(selectedLat, selectedLon).catch(() => {
        // The renderer retains its last valid environmental state.
      });
    }, 400);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [apiBase, selectedLat, selectedLon]);

  // ── Derived data ─────────────────────────────────────────────────────────────
  const topStats = useMemo(() => {
    if (!summary) return [];
    const openAlerts = stats?.sar?.open_alerts ?? 0;
    return [
      { label: 'AIS',      value: summary.traffic?.registry?.active_30m ?? '—', tone: 'ok' },
      { label: 'Signals',  value: intelEvents.length || stats?.signals?.recent_event_count || 0, tone: 'info' },
      { label: 'Feed',     value: intelMode === 'ws' ? 'stream' : intelMode === 'poll' ? 'live' : 'sync', tone: intelConnected ? 'ok' : 'info' },
      { label: 'Alerts',   value: openAlerts,                                    tone: openAlerts > 0 ? 'warn' : 'default' },
      { label: 'Forensics',value: stats?.sar?.forensic_packets ?? '—',           tone: 'default' },
    ];
  }, [summary, stats, intelEvents.length, intelMode, intelConnected]);

  const serviceRows = useMemo(() => {
    if (!summary) return [];
    return [
      { name: 'AISStream', state: summary.backend?.aisstream_connected ? 'live' : 'degraded', detail: summary.backend?.aisstream_connected ? `live feed (${summary.backend?.aisstream_messages} msgs)` : 'feed unavailable' },
      { name: 'CMEMS',     state: summary.backend?.cmems_configured ? 'ready' : 'degraded', detail: summary.backend?.cmems_configured ? 'live currents configured' : 'credentials missing' },
      { name: 'Redis',     state: summary.backend?.redis_configured ? 'ok' : 'off',      detail: summary.backend?.redis_configured ? 'cache active' : 'not configured' },
      { name: 'Database',  state: summary.backend?.database ?? '—',                      detail: summary.backend?.database === 'postgres' ? 'persistent' : 'local' },
      { name: 'Scheduler', state: summary.scheduler?.running ? 'live' : 'off',           detail: summary.scheduler?.running ? `${summary.scheduler?.jobs?.length || 0} jobs active` : 'not running' },
      { name: 'TimeZero',  state: timezero ? (timezero.enabled ? (timezero.reachable ? 'reachable' : 'off') : 'disabled') : 'pending', detail: timezero ? `${timezero.host}:${timezero.port}` : 'pending' },
      { name: 'WhatsApp',  state: summary.channels?.whatsapp?.configured ? 'ready' : 'off', detail: summary.channels?.whatsapp?.outbound_ready ? 'Twilio inbound and outbound credentials ready' : summary.channels?.whatsapp?.inbound_ready ? 'Twilio signed inbound ready' : 'Twilio credentials missing' },
      { name: 'Telegram',  state: summary.channels?.telegram?.configured ? 'ready' : 'off', detail: summary.channels?.telegram?.configured ? (summary.channels?.telegram?.operations_chat ? 'inbound and operations chat ready' : 'inbound ready; operations chat missing') : 'bot or webhook secret missing' },
      { name: 'Partner link', state: summary.channels?.partner_webhook?.configured ? 'ready' : 'off', detail: summary.channels?.partner_webhook?.configured ? 'signed partner webhook ready' : 'partner webhook secret missing' },
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
    const latitude = Number(lat);
    const longitude = Number(lon);
    const personsAboard = Number(persons);
    if (!Number.isFinite(latitude) || latitude < -90 || latitude > 90 ||
        !Number.isFinite(longitude) || longitude < -180 || longitude > 180) {
      setCaseStatus('invalid coordinates');
      setError('Enter valid coordinates: latitude -90..90 and longitude -180..180.');
      return;
    }
    if (!Number.isInteger(personsAboard) || personsAboard < 1 || personsAboard > 10000) {
      setCaseStatus('invalid persons');
      setError('Persons aboard must be a whole number between 1 and 10,000.');
      return;
    }
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

    // Public Play is independent from Oracle: live forcing is snapshotted and
    // numerical integration runs inside a Web Worker. OpenDrift can validate
    // this same scenario asynchronously when dedicated capacity is available.
    if (APP_PROFILE === 'demo') {
      try {
        setCaseStatus('loading live fields');
        const liveWeather = await loadWeatherFor(latitude, longitude);
        const environmentSnapshot = buildEnvironmentSnapshot(liveWeather, latitude, longitude);
        const localScenarioId = globalThis.crypto?.randomUUID?.() || `scenario-${Date.now()}`;
        const observedAt = new Date().toISOString();
        setCaseEventId(localScenarioId);
        setCaseStatus('computing in browser');
        pushCaseLog(`Live snapshot ${environmentSnapshot.snapshot_id} · ${environmentSnapshot.frames.length} forcing frames`);

        const simulationResult = await computeDriftInWorker({
          scenario: {
            scenario_id: localScenarioId,
            observed_at: observedAt,
            origin: { lat: latitude, lon: longitude },
            subject: { kind: vesselType, persons: personsAboard },
          },
          environmentSnapshot,
          options: { duration_hours: 24, particles: 128 },
        }, (progress) => setCaseStatus(`computing ${Math.round(progress * 100)}%`));
        const scenario = createScenario({
          scenarioId: localScenarioId,
          lat: latitude,
          lon: longitude,
          observedAt,
          scenarioType: activeSType,
          vesselType,
          persons: personsAboard,
          riskLevel,
          environmentSnapshot,
          simulationResult,
        });
        const enriched = enrichCaseGeo(simulationResult.geojson, latitude, longitude);
        setCaseGeojson(enriched);
        mapRef.current?.getSource('sar-case')?.setData(enriched);
        setCaseStatus('completed · live browser engine');
        pushCaseLog(
          `Trajectory ready locally · ${simulationResult.diagnostics.particles} particles · ${simulationResult.diagnostics.steps} steps`,
        );
        const entry = {
          id: localScenarioId,
          label: `${activeSType.replace(/_/g, ' ')} @ ${latitude.toFixed(3)}, ${longitude.toFixed(3)}`,
          ts: observedAt,
          geojson: enriched,
          lat: latitude,
          lon: longitude,
          params: simParamsRef.current,
          scenario,
        };
        storeScenario(scenario);
        setActiveScenario(scenario);
        setSimHistory((previous) => [entry, ...previous.filter((item) => item.id !== localScenarioId)].slice(0, 10));
        setActiveSimId(localScenarioId);
        const cone = enriched.features.find((feature) => feature.properties?.type === 'cone_24h')
          || enriched.features.find((feature) => feature.geometry?.type === 'Polygon');
        setMapPanel({
          type: 'cone',
          feature: cone,
          eventId: localScenarioId,
          caseStatus: 'live browser engine',
          simParams: simParamsRef.current,
          legalAnalysis: null,
        });
        mapRef.current?.flyTo({
          center: [longitude, latitude], zoom: 8.4, essential: true, duration: 900,
        });
        return;
      } catch (err) {
        setCaseStatus('environment unavailable');
        setError(err.message || 'Live environmental simulation failed');
        pushCaseLog(`Simulation stopped: ${err.message || 'live fields unavailable'}`);
        return;
      }
    }

    try {
      const created = await fetchJson(apiBase, '/api/v1/alert', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          lat: latitude,
          lon: longitude,
          timestamp: new Date().toISOString(),
          persons: personsAboard,
          vessel_type: vesselType,
          risk_level: riskLevel,
          scenario_type: activeSType,
          domain: 'ocean_sar',
          environment: sceneEnvironmentSnapshot(weather),
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

  async function replaySim(sim) {
    let geojson = sim.geojson;
    if (!geojson) {
      // Persisted case restored from DB — fetch its drift GeoJSON on demand
      try {
        const archivePath = APP_PROFILE === 'demo'
          ? `/api/v1/live/archives/${encodeURIComponent(sim.id)}/geojson`
          : `/api/v1/alert/${encodeURIComponent(sim.id)}/geojson`;
        geojson = await fetchJson(apiBase, archivePath);
        setSimHistory((prev) => prev.map((s) => (s.id === sim.id ? { ...s, geojson } : s)));
      } catch (err) {
        setError(err.message || 'Could not load saved case');
        return;
      }
    }
    const enriched = enrichCaseGeo(geojson, sim.lat, sim.lon);
    setCaseGeojson(enriched);
    setActiveScenario(sim.scenario || null);
    mapRef.current?.getSource('sar-case')?.setData(enriched);
    setActiveSimId(sim.id);
    setCaseStatus('completed');
    mapRef.current?.flyTo({ center: [sim.lon, sim.lat], zoom: 8.4, essential: true, duration: 900 });
    setMapPanel({
      type: 'cone',
      feature: enriched.features?.[0] || null,
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

  const liveSourceCount = useMemo(
    () => new Set(intelEvents.map((feature) => feature.properties?.source).filter(Boolean)).size,
    [intelEvents],
  );
  const liveDistressCount = useMemo(
    () => intelEvents.filter((feature) => {
      const properties = feature.properties || {};
      return properties.kind === 'distress' || properties.type === 'distress';
    }).length,
    [intelEvents],
  );

  const isOnSim = APP_PROFILE === 'demo' && (activePanel === 'sim' || selectionMode);
  const simulationRunning = caseStatus.startsWith('starting') || caseStatus.startsWith('queued') || caseStatus.startsWith('computing');

  // ── Render ────────────────────────────────────────────────────────────────────
  return (
    <main className={`cop-shell ${play3D && APP_PROFILE === 'demo' ? 'is-play-mode' : ''} ${isPublicLiveHost ? 'is-live-mode' : ''}`}>
      <section className="map-stage">
        <div className={`map-frame ${play3D ? 'is-concealed' : ''}`} ref={mapNodeRef} />
        {APP_PROFILE === 'demo' ? (
          <PlayCesium
            active={play3D && playRenderer === 'cesium'}
            geojson={caseGeojson}
            weather={weather}
            lat={form.lat}
            lon={form.lon}
            persons={form.persons}
            selectionEnabled={playSimulationOpen && selectionMode}
            onPick={(pickedLat, pickedLon) => {
              setForm((current) => ({ ...current, lat: pickedLat.toFixed(5), lon: pickedLon.toFixed(5) }));
              setSelectionMode(false);
              loadWeatherFor(pickedLat, pickedLon).catch(() => {});
              loadNearestVessels(pickedLat, pickedLon).catch(() => {});
            }}
          />
        ) : null}
        {APP_PROFILE === 'demo' && UNREAL_PIXEL_STREAM_URL ? (
          <UnrealPixelStream
            active={play3D && playRenderer === 'unreal'}
            streamUrl={UNREAL_PIXEL_STREAM_URL}
            scenario={activeScenario}
          />
        ) : null}

        <div className={`map-toolbar ${play3D ? 'is-3d' : ''}`}>
          <div className="toolbar-pills">
            {APP_PROFILE === 'demo' ? (
              <button className={`map-toggle ${play3D ? 'is-on' : ''}`} type="button" onClick={() => setPlay3D((current) => !current)}>
                {play3D ? '3D sea' : '2D chart'}
              </button>
            ) : null}
            {APP_PROFILE === 'demo' && play3D && UNREAL_PIXEL_STREAM_URL ? (
              <button
                className={`map-toggle ${playRenderer === 'unreal' ? 'is-on' : ''}`}
                type="button"
                onClick={() => setPlayRenderer((current) => current === 'cesium' ? 'unreal' : 'cesium')}
              >
                {playRenderer === 'unreal' ? 'Unreal stream' : 'Cesium local'}
              </button>
            ) : null}
            {topStats.map((stat) => (
              <Pill key={stat.label} label={`${stat.label}: ${stat.value}`} tone={stat.tone} />
            ))}
            <Pill label={play3D ? 'WGS84' : MAPTILER_KEY ? 'Satellite' : 'OSM'} tone="info" />
          </div>
        </div>

        {!play3D ? <LayerToggles visibility={layerVis} onToggle={toggleLayerGroup} /> : null}

        {error  ? <div className={`map-banner error ${sidebarOpen ? 'sidebar-open' : ''}`}>{error}</div> : null}
        {loading ? <div className={`map-banner ${sidebarOpen ? 'sidebar-open' : ''}`}>Connecting to backend…</div> : null}

        {isOnSim && cursorHint.visible ? (
          <div className="map-cursor-hint" style={{ left: cursorHint.x + 18, top: cursorHint.y + 22 }}>
            Click to set distress origin
          </div>
        ) : null}

        {!play3D && !isPublicLiveHost ? (
          <div className={`map-overlay ${sidebarOpen ? 'sidebar-open' : ''}`}>
            <div className="overlay-card">
              <span className="overlay-label">Selected point</span>
              <strong>{Number.isFinite(selectedLat) ? `${selectedLat.toFixed(5)}, ${selectedLon.toFixed(5)}` : '—'}</strong>
              <span>{isOnSim ? 'Click map to set coordinates.' : 'Click map for point forecast.'}</span>
            </div>
          </div>
        ) : null}

        {selectedVessel && !play3D ? (
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
        {['cone', 'trajectory'].includes(mapPanel?.type) && !conePanelHidden && (
          <MapFloatingPanel
            panel={mapPanel}
            onClose={() => setConePanelHidden(true)}
            onComputeDrift={null}
          />
        )}
        {['cone', 'trajectory'].includes(mapPanel?.type) && conePanelHidden && (
          <button
            className="cone-reopen-btn"
            onClick={() => setConePanelHidden(false)}
            title="Open drift panel"
          >
            SAR ›
          </button>
        )}

        {/* Scenario modal — center, appears when clicking empty map */}
        {APP_PROFILE === 'demo' && showScenario && (
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

        {APP_PROFILE === 'demo' ? (
          <>
            <button
              type="button"
              className={`play-simulation-launch ${playSimulationOpen ? 'is-open' : ''}`}
              aria-expanded={playSimulationOpen}
              onClick={() => {
                setPlaySimulationOpen((open) => {
                  const next = !open;
                  setSelectionMode(next);
                  return next;
                });
              }}
            >
              <span className="play-simulation-launch__pulse" />
              <span>
                <small>ENGINE</small>
                SIMULATION
              </span>
              <b>{playSimulationOpen ? '×' : '+'}</b>
            </button>

            <aside className={`play-simulation-panel ${playSimulationOpen ? 'is-open' : ''}`} aria-hidden={!playSimulationOpen}>
              <header className="play-simulation-panel__header">
                <div>
                  <p className="section-kicker">Live fields / browser physics</p>
                  <h2>Drift simulation</h2>
                </div>
                <span className={`play-origin-state ${selectionMode ? 'is-selecting' : ''}`}>
                  {selectionMode ? 'CLICK SEA' : 'ORIGIN SET'}
                </span>
              </header>

              <div className="play-origin-readout">
                <span>ORIGIN / WGS84</span>
                <strong>{form.lat}, {form.lon}</strong>
                <small>Click the 3D sea to move the simulation origin.</small>
              </div>

              <form onSubmit={runSarCase} className="play-simulation-form">
                <div className="demo-form">
                  <label>
                    Latitude
                    <input inputMode="decimal" value={form.lat} onChange={(e) => setField('lat', e.target.value)} />
                  </label>
                  <label>
                    Longitude
                    <input inputMode="decimal" value={form.lon} onChange={(e) => setField('lon', e.target.value)} />
                  </label>
                  <label>
                    Persons
                    <input type="number" min="1" value={form.persons} onChange={(e) => setField('persons', e.target.value)} />
                  </label>
                  <label>
                    Risk
                    <select value={form.risk_level} onChange={(e) => setField('risk_level', e.target.value)}>
                      {RISK_LEVELS.map((risk) => <option key={risk.value} value={risk.value}>{risk.label}</option>)}
                    </select>
                  </label>
                </div>

                <label className="field-block">
                  Vessel type
                  <select value={form.vessel_type} onChange={(e) => setField('vessel_type', e.target.value)}>
                    {VESSEL_TYPES.map((vessel) => <option key={vessel.value} value={vessel.value}>{vessel.label}</option>)}
                  </select>
                </label>

                <div className="play-simulation-actions">
                  <button type="submit" disabled={simulationRunning}>
                    {simulationRunning ? 'COMPUTING…' : 'RUN SIMULATION'}
                  </button>
                  <button
                    type="button"
                    className={selectionMode ? 'is-active' : ''}
                    disabled={simulationRunning}
                    onClick={() => setSelectionMode((active) => !active)}
                  >
                    {selectionMode ? 'CANCEL PICK' : 'PICK ON SEA'}
                  </button>
                </div>
              </form>

              <div className="play-engine-state">
                <span>ENGINE STATUS</span>
                <strong>{caseStatus}</strong>
              </div>

              <section className="play-nearest">
                <div className="play-nearest__head">
                  <span>NEAREST LIVE AIS</span>
                  <b>{nearestVessels.length}</b>
                </div>
                <ul>
                  {nearestVessels.slice(0, 5).map((vessel, index) => (
                    <li key={`${vessel.mmsi}-${vessel.distance_km}`}>
                      <span>0{index + 1}</span>
                      <strong>{vessel.ship_name}</strong>
                      <small>{formatDistance(vessel)}</small>
                    </li>
                  ))}
                </ul>
              </section>

              <section className="play-archive">
                <div className="play-nearest__head">
                  <span>RECENT SIMULATION ARCHIVE</span>
                  <b>{simHistory.length}</b>
                </div>
                {simHistory.length ? (
                  <ul>
                    {simHistory.slice(0, 6).map((simulation, index) => (
                      <li key={simulation.id} className={simulation.id === activeSimId ? 'is-active' : ''}>
                        <span>0{index + 1}</span>
                        <div>
                          <strong>{simulation.label}</strong>
                          <small>{new Date(simulation.ts).toLocaleString('en-GB', {
                            day: '2-digit',
                            month: 'short',
                            hour: '2-digit',
                            minute: '2-digit',
                          })}</small>
                        </div>
                        <button
                          type="button"
                          onClick={() => {
                            setSelectionMode(false);
                            replaySim(simulation);
                          }}
                        >
                          {simulation.id === activeSimId ? 'LOADED' : 'LOAD 3D'}
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p>No completed simulation is available yet.</p>
                )}
              </section>
            </aside>
          </>
        ) : null}
      </section>

      {isPublicLiveHost ? (
        <>
          <aside className={`live-feed-panel ${sidebarOpen ? 'is-open' : 'is-collapsed'}`} aria-hidden={!sidebarOpen}>
            <header className="live-feed-panel__header">
              <div className="live-feed-panel__eyebrow">
                <span className="live-feed-panel__mark">SC</span>
                <span>SEACOMMONS / MEDITERRANEAN</span>
                <b><i /> 24 / 7</b>
              </div>
              <div className="live-feed-panel__title">
                <div>
                  <p>PUBLIC SIGNAL FIELD</p>
                  <h1>Live feed</h1>
                </div>
                <button type="button" onClick={() => setSidebarOpen(false)} aria-label="Collapse live feed">−</button>
              </div>
              <div className="live-feed-panel__metrics">
                <div>
                  <span>SOURCES</span>
                  <strong>{liveSourceCount}</strong>
                </div>
                <div>
                  <span>PUBLISHED</span>
                  <strong>{intelEvents.length}</strong>
                </div>
                <div>
                  <span>DISTRESS</span>
                  <strong>{liveDistressCount}</strong>
                </div>
                <div>
                  <span>TRANSPORT</span>
                  <strong>{intelMode === 'ws' ? 'WS' : intelMode === 'poll' ? 'REST' : 'SYNC'}</strong>
                </div>
              </div>
              <p className="live-feed-panel__continuity">
                <span />
                Approved collectors remain active when this map is closed.
              </p>
            </header>

            <div className="live-feed-panel__body">
              <IntelDashboard
                apiBase={apiBase}
                publicMode
                intelEvents={intelEvents}
                intelDrifts={displayedIntelDrifts}
                intelStats={intelStats}
                intelFilter={intelFilter}
                setIntelFilter={setIntelFilter}
                intelMode={intelMode}
                showAisAlerts={showAisAlerts}
                setShowAisAlerts={setShowAisAlerts}
                triggeringDrift={triggeringDrift}
                triggerIntelDrift={triggerIntelDrift}
                mapRef={mapRef}
                setSidebarOpen={(open) => {
                  if (window.matchMedia('(max-width: 820px)').matches) setSidebarOpen(open);
                }}
              />
            </div>
          </aside>
          <button
            type="button"
            className={`live-feed-toggle ${sidebarOpen ? 'is-panel-open' : ''}`}
            onClick={() => setSidebarOpen((open) => !open)}
            aria-label={sidebarOpen ? 'Collapse live feed' : 'Open live feed'}
          >
            <i />
            LIVE FEED
          </button>
        </>
      ) : null}

      {!isPublicLiveHost && APP_PROFILE !== 'demo' ? (
        <>
      <nav className="workspace-nav" aria-label="Operational views">
        <span className={`runtime-badge runtime-badge--${APP_PROFILE}`}>{APP_PROFILE}</span>
        <button className={!sidebarOpen ? 'is-active' : ''} onClick={() => setSidebarOpen(false)}>Map</button>
        {['cases','live','osint','settings'].map((view) => (
          <button key={view} className={sidebarOpen && activePanel === view ? 'is-active' : ''} onClick={() => { setActivePanel(view); setSidebarOpen(true); }}>
            {view === 'settings' ? 'Config' : view}
          </button>
        ))}
      </nav>
      <section className={`workspace-overlay ${sidebarOpen ? 'is-open' : ''}`} aria-hidden={!sidebarOpen}>
        <button type="button" className="workspace-close" aria-label="Close workspace" onClick={() => setSidebarOpen(false)}>×</button>
        {/* Mobile bottom-sheet grab handle — hidden on desktop via CSS */}
        <header className="workspace-header">
          <p className="workspace-kicker">SeaCommons / SAR pilot</p>
          <h2>Operational dashboard</h2>
          <div className="sidebar-tabs sidebar-tabs--4">
            <button className={activePanel === 'cases' ? 'is-active' : ''} onClick={() => setActivePanel('cases')}>Cases</button>
            <button className={activePanel === 'live'     ? 'is-active' : ''} onClick={() => setActivePanel('live')}>Live</button>
            <button className={activePanel === 'osint'    ? 'is-active' : ''} onClick={() => setActivePanel('osint')}>
              OSINT{intelEvents.length > 0 && <span className="tab-badge">{intelEvents.length}</span>}
            </button>
            <button className={activePanel === 'settings' ? 'is-active' : ''} onClick={() => setActivePanel('settings')}>Config</button>
          </div>
        </header>

        <div className="workspace-content">

          {activePanel === 'cases' ? (
            <CasesWorkspace apiBase={apiBase} fetchJson={fetchJson} onLocate={(lat, lon) => {
              setForm(cur => ({ ...cur, lat: String(lat), lon: String(lon) }));
              mapRef.current?.flyTo({ center: [Number(lon), Number(lat)], zoom: 8 });
            }} />
          ) : null}

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
              publicMode={isPublicLiveHost}
              intelEvents={intelEvents}
              intelDrifts={displayedIntelDrifts}
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
          {APP_PROFILE === 'demo' && activePanel === 'sim' ? (
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
                      <input inputMode="decimal" value={form.lat} onChange={(e) => setField('lat', e.target.value)} />
                    </label>
                    <label>
                      Longitude
                      <input inputMode="decimal" value={form.lon} onChange={(e) => setField('lon', e.target.value)} />
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
                    <button type="submit" disabled={simulationRunning}>{simulationRunning ? 'Computing…' : 'Compute drift'}</button>
                    <button type="button" disabled={simulationRunning} onClick={() => setSelectionMode((v) => !v)}>
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
              <ConnectorWorkspace apiBase={apiBase} fetchJson={fetchJson} />
              <JobMonitor apiBase={apiBase} fetchJson={fetchJson} />
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
      </section>
        </>
      ) : null}
    </main>
  );
}

createRoot(document.getElementById('root')).render(<AuthGate><App /></AuthGate>);
