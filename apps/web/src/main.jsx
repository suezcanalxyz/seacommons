import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

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
  { value: 'rubber_boat', label: 'Gommone' },
  { value: 'fishing_vessel', label: 'Peschereccio' },
  { value: 'sailboat', label: 'Barca a vela' },
  { value: 'motorboat', label: 'Motoscafo' },
  { value: 'container_ship', label: 'Cargo' },
  { value: 'unknown', label: 'Sconosciuto' },
];

const RISK_LEVELS = [
  { value: 'high', label: 'Alto' },
  { value: 'medium', label: 'Medio' },
  { value: 'low', label: 'Basso' },
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
      geometry: {
        type: 'LineString',
        coordinates: [[lon, lat], [endLon, endLat]],
      },
      properties: {
        ...feature.properties,
      },
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

function App() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [activePanel, setActivePanel] = useState('demo');
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
  const [demoMode, setDemoMode] = useState(false);
  const [cursorHint, setCursorHint] = useState({ visible: false, x: 0, y: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [caseStatus, setCaseStatus] = useState('idle');
  const [caseLog, setCaseLog] = useState([]);
  const [form, setForm] = useState({
    lat: '35.889',
    lon: '14.519',
    persons: '37',
    vessel_type: 'rubber_boat',
    risk_level: 'high',
  });

  const mapNodeRef = useRef(null);
  const mapRef = useRef(null);
  const demoModeRef = useRef(false);
  const activePanelRef = useRef('demo');

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
    pushCaseLog(`Meteo ${payload.source} @ ${Number(lat).toFixed(3)}, ${Number(lon).toFixed(3)}`);
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
    demoModeRef.current = demoMode;
  }, [demoMode]);

  useEffect(() => {
    activePanelRef.current = activePanel;
  }, [activePanel]);

  useEffect(() => {
    window.localStorage.setItem('seacommons_tz_host', localSettings.timezeroHost);
    window.localStorage.setItem('seacommons_tz_port', localSettings.timezeroPort);
    window.localStorage.setItem('seacommons_tz_enabled', localSettings.timezeroEnabled);
  }, [localSettings]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    map.getCanvas().style.cursor = (activePanel === 'demo' || demoMode) ? 'crosshair' : '';
  }, [activePanel, demoMode, mapReady]);

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
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');

      let weatherTimer = null;
      map.on('moveend', () => {
        window.clearTimeout(weatherTimer);
        weatherTimer = window.setTimeout(() => {
          loadWeatherGridForMap(map).catch((err) => setError(err.message || 'Weather grid non disponibile'));
        }, 220);
      });

      map.on('load', () => {
        map.addSource('weather-points', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        map.addSource('weather-vectors', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        map.addSource('vessels', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        map.addSource('alerts', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        map.addSource('sar-case', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });

        map.addLayer({
          id: 'weather-vectors',
          type: 'line',
          source: 'weather-vectors',
          paint: {
            'line-color': [
              'interpolate',
              ['linear'],
              ['get', 'beaufort'],
              0, '#7dd3fc',
              4, '#22c55e',
              7, '#f59e0b',
              10, '#ef4444',
            ],
            'line-width': 2,
            'line-opacity': 0.68,
          },
        });
        map.addLayer({
          id: 'weather-points',
          type: 'circle',
          source: 'weather-points',
          paint: {
            'circle-radius': 3.5,
            'circle-opacity': 0.9,
            'circle-color': [
              'interpolate',
              ['linear'],
              ['get', 'beaufort'],
              0, '#7dd3fc',
              4, '#22c55e',
              7, '#f59e0b',
              10, '#ef4444',
            ],
            'circle-stroke-width': 0.8,
            'circle-stroke-color': '#04131a',
          },
        });

        map.addLayer({
          id: 'vessels-halo',
          type: 'circle',
          source: 'vessels',
          paint: { 'circle-radius': 8, 'circle-color': 'rgba(117,255,229,0.16)', 'circle-blur': 0.6 },
        });
        map.addLayer({
          id: 'vessels-layer',
          type: 'circle',
          source: 'vessels',
          paint: {
            'circle-radius': 5,
            'circle-color': '#8ff5e2',
            'circle-opacity': 0.96,
            'circle-stroke-width': 1.2,
            'circle-stroke-color': '#021318',
          },
        });
        map.addLayer({
          id: 'alerts-layer',
          type: 'line',
          source: 'alerts',
          filter: ['==', '$type', 'LineString'],
          paint: { 'line-color': '#ff7b54', 'line-width': 2.5, 'line-opacity': 0.9 },
        });
        map.addLayer({
          id: 'sar-case-cone',
          type: 'fill',
          source: 'sar-case',
          filter: ['==', '$type', 'Polygon'],
          paint: {
            'fill-color': ['match', ['get', 'type'], 'cone_6h', 'rgba(255,224,109,0.18)', 'cone_12h', 'rgba(255,180,80,0.14)', 'rgba(255,120,60,0.10)'],
            'fill-outline-color': ['match', ['get', 'type'], 'cone_6h', 'rgba(255,224,109,0.55)', 'cone_12h', 'rgba(255,180,80,0.45)', 'rgba(255,120,60,0.35)'],
          },
        });
        map.addLayer({
          id: 'sar-case-line',
          type: 'line',
          source: 'sar-case',
          filter: ['==', '$type', 'LineString'],
          paint: { 'line-color': '#ffe066', 'line-width': 3, 'line-opacity': 0.95 },
        });
        map.addLayer({
          id: 'sar-case-points',
          type: 'circle',
          source: 'sar-case',
          filter: ['==', '$type', 'Point'],
          paint: {
            'circle-radius': 5,
            'circle-color': '#fff4bf',
            'circle-stroke-width': 1.5,
            'circle-stroke-color': '#ff7b54',
          },
        });

        map.on('mouseenter', 'vessels-layer', () => {
          map.getCanvas().style.cursor = 'pointer';
        });
        map.on('mouseleave', 'vessels-layer', () => {
          map.getCanvas().style.cursor = (activePanelRef.current === 'demo' || demoModeRef.current) ? 'crosshair' : '';
        });
        map.on('click', 'vessels-layer', (event) => {
          const feature = event.features?.[0];
          if (!feature) return;
          const [lon, lat] = feature.geometry.coordinates;
          setSelectedVessel({
            ...feature.properties,
            lon,
            lat,
          });
          setSidebarOpen(true);
        });

        map.on('mousemove', (event) => {
          if (activePanelRef.current !== 'demo' && !demoModeRef.current) return;
          setCursorHint({ visible: true, x: event.point.x, y: event.point.y });
        });

        map.on('mouseleave', () => {
          setCursorHint((cur) => ({ ...cur, visible: false }));
        });

        map.on('click', (event) => {
          const targetLayers = event.features?.map((feature) => feature.layer?.id).filter(Boolean) || [];
          if (targetLayers.includes('vessels-layer')) return;

          const nextLat = event.lngLat.lat.toFixed(5);
          const nextLon = event.lngLat.lng.toFixed(5);
          setForm((cur) => ({ ...cur, lat: nextLat, lon: nextLon }));

          if (activePanelRef.current === 'demo' || demoModeRef.current) {
            setDemoMode(false);
            setCursorHint({ visible: false, x: 0, y: 0 });
            setActivePanel('demo');
            setSidebarOpen(true);
            loadNearestVessels(nextLat, nextLon).catch(() => {});
            return;
          }

          loadWeatherFor(nextLat, nextLon).catch((err) => {
            setError(err.message || 'Weather fetch failed');
          });
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

  useEffect(() => {
    let alive = true;
    async function loadAll() {
      try {
        const [summaryPayload, vesselsPayload, alertsPayload] = await Promise.all([
          fetchJson(apiBase, '/api/v1/ops/summary'),
          fetchJson(apiBase, '/api/v1/vessels'),
          fetchJson(apiBase, '/api/v1/alerts/geojson'),
        ]);
        if (!alive) return;
        setSummary(summaryPayload);
        setTimezero(summaryPayload.backend.timezero || null);
        setVessels(vesselsPayload);
        setAlerts(alertsPayload);
        setError('');
      } catch (err) {
        if (!alive) return;
        setError(err.message || 'Backend non raggiungibile');
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
    return () => {
      cancelled = true;
    };
  }, [apiBase, selectedLat, selectedLon]);

  const topStats = useMemo(() => {
    if (!summary) return [];
    return [
      { label: 'AIS', value: summary.traffic.registry.active_30m, tone: 'ok' },
      { label: 'Segnali', value: summary.signals.recent_event_count, tone: 'info' },
      { label: 'Allerte', value: summary.sar.open_alerts, tone: summary.sar.open_alerts > 0 ? 'warn' : 'default' },
      { label: 'Forensics', value: summary.sar.forensic_packets, tone: 'default' },
    ];
  }, [summary]);

  const serviceRows = useMemo(() => {
    if (!summary) return [];
    return [
      { name: 'AISStream', state: summary.backend.aisstream_live ? 'live' : 'mock', detail: summary.backend.aisstream_live ? 'feed live' : 'fallback vessel set' },
      { name: 'CMEMS', state: summary.backend.cmems_live ? 'ready' : 'optional', detail: summary.backend.cmems_live ? 'correnti live' : 'meteo free + fallback' },
      { name: 'Redis', state: summary.backend.redis_configured ? 'ok' : 'off', detail: summary.backend.redis_configured ? 'cache attiva' : 'non configurato' },
      { name: 'Database', state: summary.backend.database, detail: summary.backend.database === 'postgres' ? 'persistente' : 'locale' },
      { name: 'TimeZero', state: timezero ? (timezero.enabled ? (timezero.reachable ? 'reachable' : 'off') : 'disabled') : 'pending', detail: timezero ? `${timezero.host}:${timezero.port}` : 'in attesa' },
    ];
  }, [summary, timezero]);

  async function loadWeather() {
    setWeather(null);
    try {
      await loadWeatherFor(form.lat, form.lon);
    } catch (err) {
      setError(err.message || 'Meteo non disponibile');
    }
  }

  async function runSarCaseAt(lat, lon) {
    const persons = form.persons;
    const vesselType = form.vessel_type;
    setCaseStatus('avvio...');
    setCaseGeojson({ type: 'FeatureCollection', features: [] });
    setError('');

    let nearby = nearestVessels;
    if (!nearby.length) {
      try {
        nearby = await loadNearestVessels(lat, lon);
      } catch {
        nearby = [];
      }
    }

    pushCaseLog(`Caso SAR creato @ ${Number(lat).toFixed(4)}, ${Number(lon).toFixed(4)}`);
    if (nearby.length) {
      pushCaseLog(`Navi piu vicine: ${nearby.map((item) => `${item.ship_name} (${item.distance_nm.toFixed(1)}nm)`).join(', ')}`);
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
          domain: 'ocean_sar',
        }),
      });

      setCaseStatus(`in elaborazione ${created.event_id.slice(0, 8)}`);
      pushCaseLog(`Alert accodato ${created.event_id.slice(0, 8)}`);

      for (let i = 0; i < 120; i += 1) {
        const status = await fetchJson(apiBase, `/api/v1/alert/${created.event_id}`);
        if (status.status === 'failed') {
          throw new Error(status.drift_result?.metadata?.error || 'Simulazione fallita');
        }
        if (status.status === 'completed') {
          const geojson = await fetchJson(apiBase, `/api/v1/alert/${created.event_id}/geojson`);
          setCaseGeojson(geojson);
          setCaseStatus('completato');
          pushCaseLog(`Drift pronto ${created.event_id.slice(0, 8)}`);
          mapRef.current?.flyTo({
            center: [Number(lon), Number(lat)],
            zoom: 8.4,
            essential: true,
            duration: 900,
          });
          return;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 1500));
      }
      setCaseStatus('timeout');
      pushCaseLog('Caso SAR: timeout');
    } catch (err) {
      setCaseStatus('errore');
      setError(err.message || 'Caso SAR fallito');
      pushCaseLog(`Errore: ${err.message || 'sconosciuto'}`);
    }
  }

  async function runSarCase(event) {
    if (event?.preventDefault) event.preventDefault();
    await runSarCaseAt(form.lat, form.lon);
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

  const isOnDemo = activePanel === 'demo' || demoMode;

  return (
    <main className="cop-shell">
      <section className="map-stage">
        <div className="map-frame" ref={mapNodeRef} />

        <div className="map-toolbar">
          <div className="toolbar-pills">
            {topStats.map((stat) => (
              <Pill key={stat.label} label={`${stat.label}: ${stat.value}`} tone={stat.tone} />
            ))}
            <Pill label="Satellite default" tone="info" />
          </div>
        </div>

        {error ? <div className={`map-banner error ${sidebarOpen ? 'sidebar-open' : ''}`}>{error}</div> : null}
        {loading ? <div className={`map-banner ${sidebarOpen ? 'sidebar-open' : ''}`}>Connessione al backend...</div> : null}

        {isOnDemo && cursorHint.visible ? (
          <div className="map-cursor-hint" style={{ left: cursorHint.x + 18, top: cursorHint.y + 22 }}>
            Clicca per selezionare il punto di origine
          </div>
        ) : null}

        <div className={`map-overlay ${sidebarOpen ? 'sidebar-open' : ''}`}>
          <div className="overlay-card">
            <span className="overlay-label">Punto selezionato</span>
            <strong>{selectedLat.toFixed(5)}, {selectedLon.toFixed(5)}</strong>
            <span>{isOnDemo ? 'Clicca sulla mappa per impostare le coordinate.' : 'Clicca sulla mappa per condizioni meteo.'}</span>
          </div>
        </div>

        {selectedVessel ? (
          <div className={`map-overlay ${sidebarOpen ? 'sidebar-open' : ''}`} style={{ top: 16, bottom: 'auto' }}>
            <div className="overlay-card">
              <span className="overlay-label">Nave selezionata</span>
              <strong>{selectedVessel.ship_name || selectedVessel.name || selectedVessel.mmsi}</strong>
              <span>
                {(selectedVessel.type || selectedVessel.ship_type || 'unknown').toString()} · {selectedVessel.speed ?? selectedVessel.sog ?? '—'} kn · {selectedVessel.mmsi || 'n/a'}
              </span>
            </div>
          </div>
        ) : null}

        {caseLog.length > 0 ? (
          <div className="case-log-panel">
            <div className="log-header">Case log - {caseStatus}</div>
            <ul className="log-list">
              {caseLog.map((entry) => (
                <li key={entry.id}>
                  <span>{entry.message}</span>
                  <time>{new Date(entry.at).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</time>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>

      <button
        className={`sidebar-toggle ${sidebarOpen ? 'panel-open' : ''}`}
        onClick={() => setSidebarOpen((open) => !open)}
        title={sidebarOpen ? 'Chiudi pannello' : 'Apri pannello'}
      >
        {sidebarOpen ? '‹' : '›'}
      </button>

      <aside className={`sidebar ${sidebarOpen ? '' : 'is-closed'}`}>
        <header className="sidebar-header">
          <p className="sidebar-kicker">SeaCommons / SAR pilot</p>
          <h2>Dashboard operativa</h2>
          <div className="sidebar-tabs sidebar-tabs--4">
            <button className={activePanel === 'demo' ? 'is-active' : ''} onClick={() => setActivePanel('demo')}>Demo</button>
            <button className={activePanel === 'live' ? 'is-active' : ''} onClick={() => setActivePanel('live')}>Live</button>
            <button className={activePanel === 'layers' ? 'is-active' : ''} onClick={() => setActivePanel('layers')}>Layers</button>
            <button className={activePanel === 'settings' ? 'is-active' : ''} onClick={() => setActivePanel('settings')}>Config</button>
          </div>
        </header>

        <div className="sidebar-inner">
          {activePanel === 'live' ? (
            <div className="panel-stack">
              <section className="panel-block">
                <p className="section-kicker">Condizioni live</p>
                <h3>Meteo operativo</h3>
                <div className="info-grid">
                  <div className="info-box">
                    <strong>Overlay</strong>
                    <span>Weather grid nativo</span>
                  </div>
                  <div className="info-box">
                    <strong>Fonte meteo</strong>
                    <span>{weather ? weather.source : 'Open-Meteo / CMEMS'}</span>
                  </div>
                </div>
                {weather ? (
                  <div className="weather-card">
                    <span>Vento {weather.wind.speed_ms} m/s {weather.wind.direction_label}</span>
                    <span>Onda {weather.waves.significant_height_m} m</span>
                    <span>Corrente {weather.ocean.current_speed_ms} m/s</span>
                    <span>Deriva {weather.sar_conditions.drift_speed_ms} m/s - {weather.sar_conditions.drift_dir_deg}°</span>
                  </div>
                ) : null}
                <div className="action-row">
                  <button onClick={loadWeather}>Carica meteo locale</button>
                  <button onClick={() => loadWeatherGridForMap(mapRef.current).catch((err) => setError(err.message || 'Grid meteo non disponibile'))}>Aggiorna overlay</button>
                </div>
              </section>

              <section className="panel-block">
                <p className="section-kicker">Segnali recenti</p>
                <h3>Intake eventi</h3>
                <ul className="signal-list">
                  {(summary?.signals.recent_events || []).map((item) => (
                    <li key={`${item.timestamp}-${item.vessel_id || 'evt'}`}>
                      <strong>{item.ship_name || item.vessel_id || item.event_type}</strong>
                      <span>{item.adapter || item.protocol || 'fonte sconosciuta'}</span>
                      <span>{item.status || item.event_type}</span>
                    </li>
                  ))}
                </ul>
              </section>
            </div>
          ) : null}

          {activePanel === 'demo' ? (
            <div className="panel-stack">
              <section className="panel-block">
                <p className="section-kicker">Simulazione SAR</p>
                <h3>Nuovo caso di deriva</h3>
                <p className="panel-copy">
                  Clicca sulla mappa per impostare le coordinate. Prima del calcolo SeaCommons controlla e propone le 5 navi più vicine al punto distress.
                </p>

                <form onSubmit={runSarCase}>
                  <div className="demo-form">
                    <label>
                      Latitudine
                      <input value={form.lat} onChange={(e) => setField('lat', e.target.value)} />
                    </label>
                    <label>
                      Longitudine
                      <input value={form.lon} onChange={(e) => setField('lon', e.target.value)} />
                    </label>
                    <label>
                      Persone a bordo
                      <input type="number" min="1" value={form.persons} onChange={(e) => setField('persons', e.target.value)} />
                    </label>
                    <label>
                      Rischio
                      <select value={form.risk_level} onChange={(e) => setField('risk_level', e.target.value)}>
                        {RISK_LEVELS.map((risk) => <option key={risk.value} value={risk.value}>{risk.label}</option>)}
                      </select>
                    </label>
                  </div>

                  <div className="field-block" style={{ marginTop: 8 }}>
                    <span>Tipo imbarcazione</span>
                    <select value={form.vessel_type} onChange={(e) => setField('vessel_type', e.target.value)}>
                      {VESSEL_TYPES.map((vessel) => <option key={vessel.value} value={vessel.value}>{vessel.label}</option>)}
                    </select>
                  </div>

                  <div className="action-row">
                    <button type="submit">Calcola deriva</button>
                    <button type="button" onClick={() => setDemoMode((value) => !value)}>
                      {demoMode ? 'Annulla selezione' : 'Seleziona da mappa'}
                    </button>
                  </div>
                </form>

                {demoMode ? (
                  <div className="demo-note">
                    Modalita selezione attiva - clicca sulla mappa per impostare le coordinate.
                  </div>
                ) : null}

                <div className="status-strip">
                  <span>Stato</span>
                  <strong>{caseStatus}</strong>
                </div>
              </section>

              <section className="panel-block">
                <p className="section-kicker">Ricerca prossimità</p>
                <h3>5 navi più vicine</h3>
                <ul className="service-list">
                  {nearestVessels.length ? nearestVessels.map((vessel) => (
                    <li key={`${vessel.mmsi}-${vessel.distance_km}`}>
                      <div>
                        <strong>{vessel.ship_name}</strong>
                        <span>{(vessel.type || 'unknown').toString()} - {formatDistance(vessel)}</span>
                      </div>
                      <button className="link-button" type="button" onClick={() => focusVessel(vessel)}>
                        Apri
                      </button>
                    </li>
                  )) : (
                    <li>
                      <div>
                        <strong>Nessuna nave trovata</strong>
                        <span>Seleziona coordinate valide o verifica il feed AIS.</span>
                      </div>
                    </li>
                  )}
                </ul>
              </section>
            </div>
          ) : null}

          {activePanel === 'layers' ? (
            <div className="panel-stack">
              <section className="panel-block">
                <p className="section-kicker">Overview</p>
                <h3>Come si integra SeaCommons</h3>
                <p className="panel-copy">Tre livelli di utilizzo: browser dashboard, API REST, nodo edge autonomo.</p>
              </section>

              <section className="panel-block">
                <div className="layer-badge layer-badge--live">Watch</div>
                <h3>Dashboard operativa</h3>
                <p className="panel-copy">Satellite di default, overlay meteo grafico nativo e navi AIS cliccabili. Nessun layer Windy esterno: il meteo viene disegnato con dati gratuiti via API.</p>
              </section>

              <section className="panel-block">
                <div className="layer-badge layer-badge--api">API</div>
                <h3>REST + WebSocket</h3>
                <p className="panel-copy">Endpoint per drift, weather, vessels, alerts e forensic packets.</p>
                <div className="layer-endpoints">
                  <code>POST /api/v1/alert</code>
                  <code>GET /api/v1/vessels/nearest</code>
                  <code>GET /api/v1/weather/grid</code>
                  <code>WS /ws/events</code>
                </div>
              </section>

              <section className="panel-block">
                <div className="layer-badge layer-badge--edge">Edge</div>
                <h3>Nodo autonomo imbarcato</h3>
                <p className="panel-copy">Raspberry Pi 5 + sensori fisici + sync satellite. Stesso backend del pilot, ma ridotto per deploy robusto e più aperto.</p>
                <div className="layer-endpoints">
                  <code>bash apps/api/edge/firmware/firstboot.sh</code>
                  <code>docker compose -f deploy/docker-compose.ship.yml up</code>
                </div>
              </section>

              <section className="panel-block">
                <p className="section-kicker">Credenziali</p>
                <h3>Stato configurazione</h3>
                <ul className="cred-list">
                  <li className={MAPTILER_KEY ? 'cred-ok' : 'cred-missing'}>
                    <span>{MAPTILER_KEY ? '✓' : '✕'} MapTiler</span>
                    <span>{MAPTILER_KEY ? 'satellite attivo' : 'fallback OSM'}</span>
                  </li>
                  <li className={OWM_KEY ? 'cred-ok' : 'cred-missing'}>
                    <span>{OWM_KEY ? '✓' : '!'} OpenWeatherMap</span>
                    <span>{OWM_KEY ? 'chiave disponibile' : 'non necessaria nel pilot base'}</span>
                  </li>
                  <li className="cred-ok">
                    <span>✓ Open-Meteo</span>
                    <span>meteo gratuito attivo</span>
                  </li>
                  <li className="cred-ok">
                    <span>✓ Weather grid</span>
                    <span>overlay vettoriale nativo</span>
                  </li>
                </ul>
              </section>
            </div>
          ) : null}

          {activePanel === 'settings' ? (
            <div className="panel-stack">
              <section className="panel-block">
                <p className="section-kicker">Connettività</p>
                <h3>Servizi e TimeZero</h3>
                <label className="field-block">
                  API base
                  <input value={apiBase} onChange={(e) => setApiBase(e.target.value)} placeholder="http://127.0.0.1:8000" />
                </label>
                <label className="field-block" style={{ marginTop: 7 }}>
                  TimeZero host
                  <input value={localSettings.timezeroHost} onChange={(e) => updateSetting('timezeroHost', e.target.value)} />
                </label>
                <label className="field-block" style={{ marginTop: 7 }}>
                  TimeZero porta
                  <input value={localSettings.timezeroPort} onChange={(e) => updateSetting('timezeroPort', e.target.value)} />
                </label>
              </section>

              <section className="panel-block">
                <p className="section-kicker">Matrice servizi</p>
                <h3>Runtime</h3>
                <ul className="service-list">
                  {serviceRows.map((service) => (
                    <li key={service.name}>
                      <div>
                        <strong>{service.name}</strong>
                        <span>{service.detail}</span>
                      </div>
                      <Pill label={service.state} tone={['reachable', 'live', 'ready', 'ok'].includes(service.state) ? 'ok' : service.state === 'mock' ? 'info' : 'default'} />
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
