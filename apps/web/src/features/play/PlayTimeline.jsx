import React, { useEffect, useMemo, useRef, useState } from 'react';

import { fetchJson } from '../../services/api/client.js';
import {
  normalizeTimeline,
  satelliteRasterDescriptor,
  selectFrame,
  selectSatelliteObservation,
  statusLabel,
} from './timeline.js';

function mapStyle() {
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

function evidenceCollection(timeline, frameIndex) {
  return {
    type: 'FeatureCollection',
    features: timeline
      .slice(0, Math.max(0, frameIndex) + 1)
      .filter((item) => item.geometry)
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
    paint: { 'raster-opacity': 0.78, 'raster-fade-duration': 120 },
  }, 'play-evidence-fill');
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

export default function PlayTimeline({ apiBase }) {
  const mapNodeRef = useRef(null);
  const mapRef = useRef(null);
  const [mapReady, setMapReady] = useState(false);
  const [incidents, setIncidents] = useState([]);
  const [selectedId, setSelectedId] = useState('');
  const [caseData, setCaseData] = useState(null);
  const [frameIndex, setFrameIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const timeline = useMemo(
    () => normalizeTimeline(caseData?.timeline || []),
    [caseData],
  );
  const frame = useMemo(
    () => selectFrame(timeline, frameIndex),
    [timeline, frameIndex],
  );
  const satellite = useMemo(
    () => selectSatelliteObservation(timeline, frame.item?.at),
    [timeline, frame.item?.at],
  );

  useEffect(() => {
    let cancelled = false;
    async function loadIncidents() {
      try {
        const payload = await fetchJson(apiBase, '/api/v1/play/incidents?limit=100');
        if (cancelled) return;
        const rows = Array.isArray(payload?.incidents) ? payload.incidents : [];
        setIncidents(rows);
        setSelectedId((current) => current || rows[0]?.incident_id || '');
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
    let cancelled = false;
    if (!selectedId) {
      setCaseData(null);
      return () => { cancelled = true; };
    }
    setLoading(true);
    fetchJson(apiBase, `/api/v1/play/incidents/${encodeURIComponent(selectedId)}/timeline`)
      .then((payload) => {
        if (cancelled) return;
        setCaseData(payload);
        const ordered = normalizeTimeline(payload?.timeline || []);
        setFrameIndex(Math.max(0, ordered.length - 1));
        setError('');
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
        style: mapStyle(), center: [15.2, 36.1], zoom: 4.2,
        attributionControl: true,
      });
      map.addControl(new maplibregl.NavigationControl({ showCompass: true }), 'bottom-right');
      map.addControl(new maplibregl.ScaleControl({ maxWidth: 110, unit: 'nautical' }), 'bottom-right');
      map.on('load', () => {
        if (disposed) return;
        map.addSource('play-evidence', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        map.addLayer({
          id: 'play-evidence-fill', type: 'fill', source: 'play-evidence',
          filter: ['==', ['geometry-type'], 'Polygon'],
          paint: { 'fill-color': '#65d9d0', 'fill-opacity': 0.16 },
        });
        map.addLayer({
          id: 'play-evidence-line', type: 'line', source: 'play-evidence',
          filter: ['==', ['geometry-type'], 'LineString'],
          paint: {
            'line-color': ['match', ['get', 'kind'], 'drift', '#8ed8ff', '#f0b36b'],
            'line-width': ['match', ['get', 'kind'], 'drift', 3, 2],
            'line-opacity': 0.9,
          },
        });
        map.addLayer({
          id: 'play-evidence-point', type: 'circle', source: 'play-evidence',
          filter: ['==', ['geometry-type'], 'Point'],
          paint: {
            'circle-radius': 6,
            'circle-color': ['match', ['get', 'kind'], 'report', '#ff6b6b', '#f0b36b'],
            'circle-stroke-color': '#071014', 'circle-stroke-width': 1.5,
          },
        });
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
    const source = map.getSource('play-evidence');
    source?.setData(evidenceCollection(timeline, frame.index));
    addSatelliteLayer(map, satellite);

    const geometry = frame.geometry;
    if (geometry?.type === 'Point' && Array.isArray(geometry.coordinates)) {
      map.easeTo({ center: geometry.coordinates, zoom: Math.max(map.getZoom(), 7), duration: 500 });
    }
  }, [mapReady, timeline, frame.index, frame.geometry, satellite]);

  const selectedIncident = useMemo(
    () => incidents.find((item) => item.incident_id === selectedId) || null,
    [incidents, selectedId],
  );
  const status = caseData?.incident_status || selectedIncident?.incident_status || 'outcome_unknown';
  const frameProps = frame.item?.properties || {};
  const satelliteProps = satellite?.properties || {};

  return (
    <main className="play-shell">
      <header className="play-header">
        <div>
          <p className="play-eyebrow">SeaCommons / temporal OSINT reconstruction</p>
          <h1>PLAY</h1>
        </div>
        <div className="play-header__meta">
          <span>Historical evidence</span>
          <strong>{incidents.length} incidents</strong>
        </div>
      </header>

      <aside className="play-cases">
        <div className="play-section-head">
          <span>Timeline archive</span>
          <strong>&gt;24h</strong>
        </div>
        <div className="play-cases__list">
          {incidents.map((incident) => (
            <button
              key={incident.incident_id}
              type="button"
              className={`play-case ${selectedId === incident.incident_id ? 'is-active' : ''}`}
              onClick={() => setSelectedId(incident.incident_id)}
            >
              <span className="play-case__time">{itemTime(incident.reported_at)}</span>
              <strong>{incident.title || 'Humanitarian incident'}</strong>
              <span>{incident.source || 'source'} · {statusLabel(incident.incident_status)}</span>
            </button>
          ))}
          {!incidents.length && !loading ? (
            <div className="play-empty">No historical incidents available yet.</div>
          ) : null}
        </div>
      </aside>

      <section className="play-map-stage">
        <div className="play-map" ref={mapNodeRef} />
        {loading ? <div className="play-map-message">Loading temporal evidence…</div> : null}
        {error ? <div className="play-map-message is-error">{error}</div> : null}
        {selectedId ? (
          <div className="play-map-status">
            <span>{selectedIncident?.source || 'incident'}</span>
            <strong>{statusLabel(status)}</strong>
            {satellite ? (
              <span>{satelliteProps.mission || satellite.source} · {satelliteProps.temporal_relation || 'snapshot'}</span>
            ) : <span>No satellite snapshot at this frame</span>}
          </div>
        ) : null}
      </section>

      <aside className="play-evidence">
        <div className="play-section-head">
          <span>Evidence frame</span>
          <strong>{frame.item ? `${frame.index + 1}/${timeline.length}` : '—'}</strong>
        </div>
        <div className="play-evidence__scroll">
          <section className="play-card">
            <p>{frame.item?.type?.replaceAll('_', ' ') || 'No frame selected'}</p>
            <h2>{frame.item?.title || selectedIncident?.title || 'SeaCommons incident'}</h2>
            <time>{itemTime(frame.item?.at)}</time>
            <span>{frame.item?.source || '—'}</span>
          </section>
          <section className="play-card play-card--rows">
            <div><span>Status</span><strong>{statusLabel(status)}</strong></div>
            <div><span>Type</span><strong>{frame.item?.type || '—'}</strong></div>
            {frameProps.model ? <div><span>Model</span><strong>{frameProps.model}</strong></div> : null}
            {frameProps.reason_code ? <div><span>Reason</span><strong>{frameProps.reason_code}</strong></div> : null}
            {frameProps.url ? (
              <div><span>Source</span><a href={frameProps.url} target="_blank" rel="noreferrer">Open ↗</a></div>
            ) : null}
          </section>

          <section className="play-card">
            <p>Satellite context</p>
            <h3>{satelliteProps.mission || 'No snapshot selected'}</h3>
            {satellite ? <time>{itemTime(satellite.at)}</time> : null}
            <span>{satelliteProps.sensor_type || satellite?.source || '—'}</span>
            {Number.isFinite(Number(satelliteProps.temporal_delta_s)) ? (
              <span>Δt {Math.round(Number(satelliteProps.temporal_delta_s) / 3600)} h from report</span>
            ) : null}
            {satelliteProps.source_url ? (
              <a href={satelliteProps.source_url} target="_blank" rel="noreferrer">Acquisition record ↗</a>
            ) : null}
          </section>
        </div>
      </aside>

      <footer className="play-timeline-bar">
        <button
          type="button"
          disabled={!timeline.length || frame.index <= 0}
          onClick={() => setFrameIndex((value) => Math.max(0, value - 1))}
        >←</button>
        <input
          aria-label="Timeline frame"
          type="range"
          min="0"
          max={Math.max(0, timeline.length - 1)}
          value={Math.max(0, frame.index)}
          onChange={(event) => setFrameIndex(Number(event.target.value))}
          disabled={!timeline.length}
        />
        <button
          type="button"
          disabled={!timeline.length || frame.index >= timeline.length - 1}
          onClick={() => setFrameIndex((value) => Math.min(timeline.length - 1, value + 1))}
        >→</button>
        <div className="play-timeline-bar__label">
          <strong>{frame.item ? itemTime(frame.item.at) : 'No timeline'}</strong>
          <span>{frame.item?.type?.replaceAll('_', ' ') || '—'}</span>
        </div>
      </footer>
    </main>
  );
}
