import React, { useEffect, useMemo, useRef, useState } from 'react';

import { fetchJson } from '../../services/api/client.js';
import {
  incidentCollection,
  incidentStatusAtCutoff,
  incidentsAtCutoff,
  normalizeTimeline,
  resolveGlobalTimelinePosition,
  satelliteRasterDescriptor,
  selectFrame,
  selectSatelliteObservation,
  statusLabel,
  timelineAtCutoff,
} from './timeline.js';

const TIMELINE_MAX = 1000;

function recentGibsDate() {
  const date = new Date(Date.now() - 24 * 3600 * 1000);
  return date.toISOString().slice(0, 10);
}

function mapStyle() {
  const day = recentGibsDate();
  return {
    version: 8,
    sources: {
      satelliteContext: {
        type: 'raster',
        tiles: [`https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/VIIRS_SNPP_CorrectedReflectance_TrueColor/default/${day}/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg`],
        tileSize: 256,
        attribution: 'NASA EOSDIS GIBS / VIIRS',
      },
      labels: {
        type: 'raster',
        tiles: ['https://a.tile.openstreetmap.org/{z}/{x}/{y}.png'],
        tileSize: 256,
        attribution: '&copy; OpenStreetMap contributors',
      },
    },
    layers: [
      { id: 'satellite-context', type: 'raster', source: 'satelliteContext' },
      { id: 'labels', type: 'raster', source: 'labels', paint: { 'raster-opacity': 0.16 } },
    ],
  };
}

function evidenceCollection(timeline = []) {
  return {
    type: 'FeatureCollection',
    features: timeline
      .filter((item) => item?.geometry)
      .map((item) => ({
        type: 'Feature',
        geometry: item.geometry,
        properties: {
          id: item.id,
          kind: item.type,
          at: item.at,
          title: item.title || '',
        },
      })),
  };
}

function removeSatelliteLayer(map) {
  if (!map) return;
  if (map.getLayer('play-satellite')) map.removeLayer('play-satellite');
  if (map.getSource('play-satellite')) map.removeSource('play-satellite');
}

function addSatelliteLayer(map, observation) {
  removeSatelliteLayer(map);
  const descriptor = satelliteRasterDescriptor(observation);
  if (!descriptor) return;
  map.addSource('play-satellite', descriptor);
  map.addLayer({
    id: 'play-satellite',
    type: 'raster',
    source: 'play-satellite',
    paint: { 'raster-opacity': 0.72, 'raster-fade-duration': 120 },
  }, 'play-incidents');
}

function itemTime(value) {
  try {
    return new Intl.DateTimeFormat('en-GB', {
      day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
      timeZone: 'UTC', hour12: false,
    }).format(new Date(value));
  } catch {
    return value || '—';
  }
}

function cutoffLabel(state) {
  if (state.mode === 'all') return 'ALL';
  try {
    return new Intl.DateTimeFormat('en-GB', {
      day: '2-digit', month: 'short', year: 'numeric',
      timeZone: 'UTC',
    }).format(new Date(state.cutoff));
  } catch {
    return state.cutoff || 'PAST';
  }
}

export default function PlayTimeline({ apiBase }) {
  const mapNodeRef = useRef(null);
  const mapRef = useRef(null);
  const [mapReady, setMapReady] = useState(false);
  const [incidents, setIncidents] = useState([]);
  const [selectedId, setSelectedId] = useState('');
  const [caseData, setCaseData] = useState(null);
  const [globalPosition, setGlobalPosition] = useState(TIMELINE_MAX);
  const [casesOpen, setCasesOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const globalState = useMemo(
    () => resolveGlobalTimelinePosition(incidents, globalPosition, TIMELINE_MAX),
    [incidents, globalPosition],
  );
  const visibleIncidents = useMemo(
    () => incidentsAtCutoff(incidents, globalState.cutoff),
    [incidents, globalState.cutoff],
  );
  const selectedIncident = useMemo(
    () => visibleIncidents.find((item) => item.incident_id === selectedId) || null,
    [visibleIncidents, selectedId],
  );
  const fullTimeline = useMemo(
    () => normalizeTimeline(caseData?.timeline || []),
    [caseData],
  );
  const visibleTimeline = useMemo(
    () => timelineAtCutoff(fullTimeline, globalState.cutoff),
    [fullTimeline, globalState.cutoff],
  );
  const frame = useMemo(
    () => selectFrame(visibleTimeline, Math.max(0, visibleTimeline.length - 1)),
    [visibleTimeline],
  );
  const satellite = useMemo(
    () => selectSatelliteObservation(visibleTimeline, frame.item?.at),
    [visibleTimeline, frame.item?.at],
  );

  useEffect(() => {
    let cancelled = false;
    async function loadIncidents() {
      try {
        const all = [];
        let offset = 0;
        let pages = 0;
        while (!cancelled && pages < 100) {
          const payload = await fetchJson(apiBase, `/api/v1/play/incidents?limit=500&offset=${offset}`);
          all.push(...(Array.isArray(payload?.incidents) ? payload.incidents : []));
          if (payload?.next_offset == null) break;
          offset = Number(payload.next_offset);
          pages += 1;
        }
        if (cancelled) return;
        const unique = [...new Map(all.map((item) => [item.incident_id, item])).values()];
        setIncidents(unique);
        setError('');
      } catch (exc) {
        if (!cancelled) setError(exc?.message || 'Play archive unavailable');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    loadIncidents();
    const timer = window.setInterval(loadIncidents, 60_000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [apiBase]);

  useEffect(() => {
    if (selectedId && !visibleIncidents.some((item) => item.incident_id === selectedId)) {
      setSelectedId('');
      setCaseData(null);
    }
  }, [selectedId, visibleIncidents]);

  useEffect(() => {
    let cancelled = false;
    if (!selectedId) {
      setCaseData(null);
      return () => { cancelled = true; };
    }
    setLoading(true);
    fetchJson(apiBase, `/api/v1/play/incidents/${encodeURIComponent(selectedId)}/timeline`)
      .then((payload) => {
        if (!cancelled) {
          setCaseData(payload);
          setError('');
        }
      })
      .catch((exc) => { if (!cancelled) setError(exc?.message || 'Timeline unavailable'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [apiBase, selectedId]);

  useEffect(() => {
    let disposed = false;
    async function initMap() {
      await import('maplibre-gl/dist/maplibre-gl.css');
      const { default: maplibregl } = await import('maplibre-gl');
      if (disposed || !mapNodeRef.current || mapRef.current) return;
      const map = new maplibregl.Map({
        container: mapNodeRef.current,
        style: mapStyle(), center: [14.8, 35.7], zoom: 3.55,
        attributionControl: true,
      });
      map.addControl(new maplibregl.NavigationControl({ showCompass: true }), 'bottom-right');
      map.on('load', () => {
        if (disposed) return;
        map.addSource('play-incidents', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        map.addLayer({
          id: 'play-incidents', type: 'circle', source: 'play-incidents',
          paint: {
            'circle-radius': ['case', ['==', ['get', 'incident_id'], selectedId], 8, 5],
            'circle-color': ['match', ['get', 'domain'], 'maritime', '#8ed8ff', '#ff746f'],
            'circle-opacity': 0.9,
            'circle-stroke-color': '#071014', 'circle-stroke-width': 1.5,
          },
        });
        map.addSource('play-evidence', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        map.addLayer({
          id: 'play-evidence-fill', type: 'fill', source: 'play-evidence',
          filter: ['==', ['geometry-type'], 'Polygon'],
          paint: { 'fill-color': '#65d9d0', 'fill-opacity': 0.16 },
        });
        map.addLayer({
          id: 'play-evidence-line', type: 'line', source: 'play-evidence',
          filter: ['==', ['geometry-type'], 'LineString'],
          paint: { 'line-color': '#8ed8ff', 'line-width': 3, 'line-opacity': 0.9 },
        });
        map.on('click', 'play-incidents', (event) => {
          const id = event.features?.[0]?.properties?.incident_id;
          if (id) {
            setSelectedId(String(id));
            setCasesOpen(false);
          }
        });
        map.on('mouseenter', 'play-incidents', () => { map.getCanvas().style.cursor = 'pointer'; });
        map.on('mouseleave', 'play-incidents', () => { map.getCanvas().style.cursor = ''; });
        mapRef.current = map;
        setMapReady(true);
      });
    }
    initMap().catch((exc) => setError(exc?.message || 'Map unavailable'));
    return () => {
      disposed = true;
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!mapReady || !map) return;
    map.getSource('play-incidents')?.setData(incidentCollection(visibleIncidents));
    map.getSource('play-evidence')?.setData(evidenceCollection(visibleTimeline));
    if (map.getLayer('play-incidents')) {
      map.setPaintProperty('play-incidents', 'circle-radius', ['case', ['==', ['get', 'incident_id'], selectedId], 8, 5]);
    }
    addSatelliteLayer(map, satellite);

    const geometry = selectedIncident?.geometry;
    if (selectedId && geometry?.type === 'Point' && Array.isArray(geometry.coordinates)) {
      const mobile = window.matchMedia?.('(max-width: 680px)')?.matches;
      map.easeTo({
        center: geometry.coordinates,
        zoom: Math.max(map.getZoom(), 6.5),
        padding: mobile ? { top: 40, bottom: 250, left: 24, right: 24 } : { top: 20, bottom: 20, left: 20, right: 20 },
        duration: 450,
      });
    }
  }, [mapReady, visibleIncidents, visibleTimeline, selectedId, selectedIncident, satellite]);

  useEffect(() => {
    const map = mapRef.current;
    if (mapReady && map) window.setTimeout(() => map.resize(), 40);
  }, [mapReady, selectedId, casesOpen]);

  const status = selectedIncident ? incidentStatusAtCutoff(selectedIncident, globalState.cutoff) : 'outcome_unknown';
  const frameProps = frame.item?.properties || {};
  const satelliteProps = satellite?.properties || {};
  const modeLabel = cutoffLabel(globalState);

  return (
    <main className={`play-shell ${selectedId ? 'has-selection' : ''}`}>
      <header className="play-header">
        <div>
          <p className="play-eyebrow">SeaCommons / temporal OSINT reconstruction</p>
          <h1>PLAY</h1>
        </div>
        <div className="play-header__actions">
          <button className="play-mobile-cases-toggle" type="button" onClick={() => setCasesOpen((value) => !value)}>
            Archive · {visibleIncidents.length}
          </button>
          <div className="play-header__meta">
            <span>{globalState.mode === 'all' ? 'Complete archive' : 'Historical cutoff'}</span>
            <strong>{visibleIncidents.length} / {incidents.length}</strong>
          </div>
        </div>
      </header>

      <aside className={`play-cases ${casesOpen ? 'is-open' : ''}`}>
        <div className="play-section-head">
          <span>Archive</span>
          <button type="button" onClick={() => setCasesOpen(false)}>Close</button>
        </div>
        <div className="play-cases__list">
          {visibleIncidents.map((incident) => (
            <button
              key={incident.incident_id}
              type="button"
              className={`play-case ${selectedId === incident.incident_id ? 'is-active' : ''}`}
              onClick={() => { setSelectedId(incident.incident_id); setCasesOpen(false); }}
            >
              <span className="play-case__time">{itemTime(incident.reported_at)}</span>
              <strong>{incident.title || 'SeaCommons incident'}</strong>
              <span>{incident.domain || 'humanitarian'} · {incident.source || 'source'} · {statusLabel(incidentStatusAtCutoff(incident, globalState.cutoff))}</span>
            </button>
          ))}
          {!visibleIncidents.length && !loading ? <div className="play-empty">No incidents at this time.</div> : null}
        </div>
      </aside>

      <section className="play-map-stage">
        <div className="play-map" ref={mapNodeRef} />
        <div className="play-all-badge"><strong>{modeLabel}</strong><span>{visibleIncidents.length} points</span></div>
        {loading ? <div className="play-map-message">Loading temporal evidence…</div> : null}
        {error ? <div className="play-map-message is-error">{error}</div> : null}
        {selectedId ? (
          <div className="play-map-status">
            <span>{selectedIncident?.source || 'incident'}</span>
            <strong>{statusLabel(status)}</strong>
            {satellite ? <span>{satelliteProps.mission || satellite.source} · {satelliteProps.temporal_relation || 'snapshot'}</span> : null}
          </div>
        ) : null}
      </section>

      <aside className={`play-evidence ${selectedId ? 'is-open' : ''}`}>
        <div className="play-sheet-handle" />
        <div className="play-section-head">
          <span>Case dossier</span>
          <button type="button" onClick={() => setSelectedId('')}>Close</button>
        </div>
        <div className="play-evidence__scroll">
          <section className="play-card">
            <p>{selectedIncident?.domain || caseData?.domain || 'incident'}</p>
            <h2>{selectedIncident?.title || 'SeaCommons incident'}</h2>
            <time>{itemTime(selectedIncident?.reported_at)}</time>
            <span>{selectedIncident?.source || '—'}</span>
          </section>
          <section className="play-card play-card--rows">
            <div><span>Status</span><strong>{statusLabel(status)}</strong></div>
            <div><span>View</span><strong>{modeLabel}</strong></div>
            <div><span>Evidence known</span><strong>{visibleTimeline.length}</strong></div>
            {frame.item ? <div><span>Latest at cutoff</span><strong>{frame.item.type}</strong></div> : null}
            {frameProps.model ? <div><span>Model</span><strong>{frameProps.model}</strong></div> : null}
            {frameProps.reason_code ? <div><span>Reason</span><strong>{frameProps.reason_code}</strong></div> : null}
          </section>
          <section className="play-card">
            <p>Latest evidence at this time</p>
            <h3>{frame.item?.title || 'No evidence available before this cutoff'}</h3>
            {frame.item ? <time>{itemTime(frame.item.at)}</time> : null}
            <span>{frame.item?.source || '—'}</span>
            {frameProps.url ? <a href={frameProps.url} target="_blank" rel="noreferrer">Source ↗</a> : null}
          </section>
          <section className="play-card">
            <p>Satellite context</p>
            <h3>{satelliteProps.mission || 'No acquisition before this time'}</h3>
            {satellite ? <time>{itemTime(satellite.at)}</time> : null}
            <span>{satelliteProps.sensor_type || satellite?.source || '—'}</span>
            {Number.isFinite(Number(satelliteProps.temporal_delta_s)) ? <span>Δt {Math.round(Number(satelliteProps.temporal_delta_s) / 3600)} h from report</span> : null}
            {satelliteProps.source_url ? <a href={satelliteProps.source_url} target="_blank" rel="noreferrer">Acquisition record ↗</a> : null}
          </section>
        </div>
      </aside>

      <footer className="play-timeline-bar">
        <span className="play-timeline-end">PAST</span>
        <button type="button" disabled={globalPosition <= 0} onClick={() => setGlobalPosition((value) => Math.max(0, value - 50))}>←</button>
        <input
          aria-label="Global archive timeline"
          type="range"
          min="0"
          max={TIMELINE_MAX}
          value={globalPosition}
          onChange={(event) => setGlobalPosition(Number(event.target.value))}
        />
        <button type="button" disabled={globalPosition >= TIMELINE_MAX} onClick={() => setGlobalPosition((value) => Math.min(TIMELINE_MAX, value + 50))}>→</button>
        <div className="play-timeline-bar__label"><strong>{modeLabel}</strong><span>{globalState.mode === 'all' ? 'complete archive' : 'evidence available by cutoff'}</span></div>
        <button className="play-all-reset" type="button" disabled={globalState.mode === 'all'} onClick={() => setGlobalPosition(TIMELINE_MAX)}>ALL</button>
      </footer>
    </main>
  );
}
