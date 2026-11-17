import React, { useEffect, useMemo, useRef, useState } from 'react';

import { fetchJson } from '../../services/api/client.js';
import { timelineReport, humanizeDetectorText } from '../live/reportNarrative.js';
import SanctionsCatalog from '../../components/SanctionsCatalog.jsx';
import { historicalDriftFeatures } from './driftGeometry.js';
import { reconstructAisGaps, aisGapMapFeatures } from './aisGapGeometry.js';
import { configureMaplibreWorker } from '../map/maplibreWorker.js';
import { createVesselArrowImage, VESSEL_COLOR } from '../map/vesselMarker.js';
import { createAttackMarkerImage, isAttackIncident } from '../map/attackMarker.js';
import { createFallbackMap } from '../map/fallbackRenderer.js';
import {
  incidentCollection,
  mergeIncidentPages,
  playMapStyle,
  incidentStatusAtCutoff,
  incidentsAtCutoff,
  normalizeTimeline,
  resolveGlobalTimelinePosition,
  satelliteRasterDescriptor,
  satelliteFootprintCollection,
  selectFrame,
  selectPreferredSatelliteObservation,
  statusLabel,
  timelineAtCutoff,
  archiveCoverage,
  groupArchiveByMonth,
  satelliteContextTileUrl,
} from './timeline.js';

const TIMELINE_MAX = 1000;
function evidenceLabel(item) {
  if (item?.corroborated === true || item?.verification_status === 'multi_source_corroborated') return 'Confirmed by independent sources';
  if (item?.verification_status === 'contested' || item?.evidence_state === 'contested') return 'Conflicting evidence';
  if (item?.verification_status === 'verified') return 'Verified';
  if (item?.evidence_stage === 'multi_indicator') return 'Multiple supporting clues';
  return 'Not independently confirmed';
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

function geometryBounds(geometry) {
  if (!geometry) return null;
  const coordinates = [];
  const collect = (value) => {
    if (Array.isArray(value) && value.length >= 2
        && Number.isFinite(Number(value[0])) && Number.isFinite(Number(value[1]))) {
      coordinates.push([Number(value[0]), Number(value[1])]);
      return;
    }
    if (Array.isArray(value)) value.forEach(collect);
  };
  collect(geometry.coordinates);
  if (!coordinates.length) return null;
  const lons = coordinates.map((point) => point[0]);
  const lats = coordinates.map((point) => point[1]);
  return {
    west: Math.min(...lons), south: Math.min(...lats),
    east: Math.max(...lons), north: Math.max(...lats),
    center: [
      (Math.min(...lons) + Math.max(...lons)) / 2,
      (Math.min(...lats) + Math.max(...lats)) / 2,
    ],
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
  }, 'play-clusters');
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
  const fallbackMapRef = useRef(null);
  const [mapReady, setMapReady] = useState(false);
  const [fallbackReady, setFallbackReady] = useState(false);
  const [mapContentReady, setMapContentReady] = useState(false);
  const [mapError, setMapError] = useState('');
  const [incidents, setIncidents] = useState([]);
  const [archiveNow, setArchiveNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setArchiveNow(Date.now()), 60_000);
    return () => window.clearInterval(timer);
  }, []);
  // LIVE owns the rolling last 24h; PLAY retains older evidence without deleting records.
  const historicalIncidents = useMemo(() => incidents.filter((incident) => {
    const reported = Date.parse(String(incident.reported_at || ''));
    return Number.isFinite(reported) && reported < archiveNow - 24 * 60 * 60 * 1000;
  }), [incidents, archiveNow]);
  const [archiveTotal, setArchiveTotal] = useState(null);
  const [selectedId, setSelectedId] = useState('');
  const [overlapIds, setOverlapIds] = useState([]);
  const [caseData, setCaseData] = useState(null);
  const [reportOpen, setReportOpen] = useState(false);
  const [globalPosition, setGlobalPosition] = useState(TIMELINE_MAX);
  const [casesOpen, setCasesOpen] = useState(false);
  const [mobileTab, setMobileTab] = useState('map');
  const [selectedDay, setSelectedDay] = useState('');
  const [guideOpen, setGuideOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [startupGraceExpired, setStartupGraceExpired] = useState(false);
  useEffect(() => {
    const timeout = window.setTimeout(() => setStartupGraceExpired(true), 25_000);
    return () => window.clearTimeout(timeout);
  }, []);
  const [error, setError] = useState('');
  const [satelliteMission, setSatelliteMission] = useState('auto');
  const [archiveFilter, setArchiveFilter] = useState('all');
  const [visibleCaseLimit, setVisibleCaseLimit] = useState(80);
  const [incidentTypeFilter, setIncidentTypeFilter] = useState('all');
  const [evidenceFilter, setEvidenceFilter] = useState('all');
  const [satelliteOnly, setSatelliteOnly] = useState(false);
  const [sanctionsOnly, setSanctionsOnly] = useState(false);
  const [investigationsOnly, setInvestigationsOnly] = useState(false);
  const [satelliteVisible, setSatelliteVisible] = useState(false);
  const [satelliteContextMission, setSatelliteContextMission] = useState('VIIRS NOAA-21');

  const globalState = useMemo(
    () => resolveGlobalTimelinePosition(historicalIncidents, globalPosition, TIMELINE_MAX),
    [historicalIncidents, globalPosition],
  );
  const visibleIncidents = useMemo(() => {
    if (globalState.mode === 'all' && !selectedDay) return historicalIncidents;
    const day = selectedDay || globalState.cutoff?.slice(0, 10);
    return historicalIncidents.filter((incident) => String(incident.reported_at || '').slice(0, 10) === day);
  }, [historicalIncidents, globalState.mode, globalState.cutoff, selectedDay]);
  const categoryIncidents = useMemo(() => visibleIncidents.filter((incident) => {
    const mainCategory = incident.main_category || incident.domain;
    if (archiveFilter === 'humanitarian') return mainCategory === 'humanitarian';
    if (archiveFilter === 'maritime') return mainCategory === 'maritime';
    if (archiveFilter === 'attacks') return isAttackIncident(incident);
    return true;
  }), [visibleIncidents, archiveFilter]);
  const incidentTypes = useMemo(
    () => [...new Set(categoryIncidents.map((incident) => incident.incident_type).filter(Boolean))].sort(),
    [categoryIncidents],
  );
  const filteredIncidents = useMemo(() => categoryIncidents.filter((incident) => {
    if (incidentTypeFilter !== 'all' && incident.incident_type !== incidentTypeFilter) return false;
    if (evidenceFilter === 'confirmed' && !incident.corroborated && incident.verification_status !== 'multi_source_corroborated') return false;
    if (evidenceFilter === 'unconfirmed' && (incident.corroborated || incident.verification_status === 'multi_source_corroborated')) return false;
    if (evidenceFilter === 'conflicting' && incident.verification_status !== 'contested' && incident.evidence_state !== 'contested') return false;
    if (satelliteOnly && !incident.has_satellite) return false;
    if (sanctionsOnly && !incident.sanctions_matched) return false;
    if (investigationsOnly && !incident.investigation) return false;
    return true;
  }), [
    categoryIncidents,
    incidentTypeFilter,
    evidenceFilter,
    satelliteOnly,
    sanctionsOnly,
    investigationsOnly,
  ]);
  const coverage = useMemo(() => archiveCoverage(historicalIncidents), [historicalIncidents]);
  const mappedIncidents = useMemo(() => incidentCollection(filteredIncidents), [filteredIncidents]);
  const mappedIncidentCount = mappedIncidents.features.length;
  // Keep the full archive available for map, timeline and search, but never
  // mount thousands of heavyweight dossier buttons at once (mobile/WebGL OOM).
  const displayedCases = useMemo(() => filteredIncidents.slice(0, visibleCaseLimit), [filteredIncidents, visibleCaseLimit]);
  const archiveGroups = useMemo(() => groupArchiveByMonth(displayedCases), [displayedCases]);
  useEffect(() => { setVisibleCaseLimit(80); }, [archiveFilter, incidentTypeFilter, evidenceFilter, satelliteOnly, sanctionsOnly, investigationsOnly, globalState.mode, globalState.cutoff, selectedDay]);
  const selectedIncident = useMemo(
    () => visibleIncidents.find((item) => item.incident_id === selectedId) || null,
    [visibleIncidents, selectedId],
  );
  const overlapIncidents = useMemo(
    () => overlapIds.map((id) => filteredIncidents.find((item) => item.incident_id === id)).filter(Boolean),
    [overlapIds, filteredIncidents],
  );
  // Derived voyage evidence must exist before the map effect depends on it.
  const voyageVessels = useMemo(() => (caseData?.voyage_evidence?.vessels || []).map((v) => ({
    ...v, track_points: (v.track_points || []).filter((p) =>
      !globalState.cutoff || Date.parse(p.at) <= Date.parse(globalState.cutoff)),
  })), [caseData?.voyage_evidence, globalState.cutoff]);
  const aisReconstruction = useMemo(() => reconstructAisGaps(voyageVessels), [voyageVessels]);
  const gapFeatures = useMemo(() => aisGapMapFeatures(aisReconstruction.gaps), [aisReconstruction]);
  const contextDay = useMemo(() => {
    const value = selectedDay || globalState.cutoff || selectedIncident?.reported_at || coverage.end;
    return value ? String(value).slice(0, 10) : new Date(Date.now() - 24 * 3600 * 1000).toISOString().slice(0, 10);
  }, [selectedDay, globalState.cutoff, selectedIncident?.reported_at, coverage.end]);
  const fullTimeline = useMemo(
    () => normalizeTimeline(caseData?.timeline || []),
    [caseData],
  );
  const dossierReasonCodes = useMemo(() => {
    if (Array.isArray(caseData?.reason_codes)) return caseData.reason_codes;
    if (Array.isArray(selectedIncident?.reason_codes)) return selectedIncident.reason_codes;
    return [];
  }, [caseData, selectedIncident]);
  const visibleTimeline = useMemo(
    () => timelineAtCutoff(fullTimeline, globalState.cutoff),
    [fullTimeline, globalState.cutoff],
  );
  const frame = useMemo(
    () => selectFrame(visibleTimeline, Math.max(0, visibleTimeline.length - 1)),
    [visibleTimeline],
  );
  const satellite = useMemo(
    () => selectPreferredSatelliteObservation(visibleTimeline, frame.item?.at, satelliteMission),
    [visibleTimeline, frame.item?.at, satelliteMission],
  );
  const satelliteMissions = useMemo(
    () => [...new Set(visibleTimeline
      .filter((item) => item?.type === 'satellite' && item?.properties?.mission)
      .map((item) => item.properties.mission))],
    [visibleTimeline],
  );

  useEffect(() => {
    let cancelled = false;
    async function loadIncidents({ full = true } = {}) {
      try {
        let collected = [];
        let offset = 0;
        const seenOffsets = new Set();
        while (!cancelled) {
          if (seenOffsets.has(offset)) throw new Error('Play archive pagination repeated an offset');
          seenOffsets.add(offset);
          const payload = await fetchJson(apiBase, `/api/v1/play/incidents?limit=100&offset=${offset}`, undefined, 30_000);
          const page = Array.isArray(payload?.incidents) ? payload.incidents : [];
          collected = mergeIncidentPages(collected, page);
          if (cancelled) return;
          setIncidents((previous) => mergeIncidentPages((offset > 0 || !full) ? previous : [], collected));
          if (offset === 0) setLoading(false);
          if (payload?.next_offset == null || !full) break;
          const nextOffset = Number(payload.next_offset);
          if (!Number.isFinite(nextOffset) || nextOffset <= offset) {
            throw new Error('Play archive pagination returned an invalid next_offset');
          }
          offset = nextOffset;
        }
        if (!cancelled) setError('');
      } catch (exc) {
        if (!cancelled) setError(exc?.message || 'Play archive unavailable');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    loadIncidents({ full: true });
    const timer = window.setInterval(() => { if (document.visibilityState !== 'hidden') loadIncidents({ full: false }); }, 60_000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [apiBase]);

  useEffect(() => {
    let cancelled = false;
    async function loadCounts() {
      try {
        const payload = await fetchJson(apiBase, '/api/v1/play/counts', undefined, 30_000);
        if (!cancelled && Number.isFinite(Number(payload?.total_count))) {
          setArchiveTotal(Number(payload.total_count));
        }
      } catch {
        // Map/archive loading remains usable even if the lightweight counter is unavailable.
      }
    }
    loadCounts();
    const timer = window.setInterval(() => { if (document.visibilityState !== 'hidden') loadCounts(); }, 60_000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [apiBase]);

  useEffect(() => {
    setSatelliteMission('auto');
  }, [selectedId]);

  useEffect(() => {
    if (incidentTypeFilter !== 'all' && !incidentTypes.includes(incidentTypeFilter)) {
      setIncidentTypeFilter('all');
    }
  }, [incidentTypeFilter, incidentTypes]);

  useEffect(() => {
    if (satelliteMission !== 'auto' && !satelliteMissions.includes(satelliteMission)) {
      setSatelliteMission('auto');
    }
  }, [satelliteMission, satelliteMissions]);

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
    let fallbackStarted = false;
    let mapStartupTimer = null;
    let mapCanvas = null;
    let contextLossHandler = null;

    function rendererFailureIsFatal(error) {
      const message = String(error?.message || error || '');
      return /\bwebgl\b|webglcontextlost|worker\s+(?:terminated|failed|crashed|unavailable)|failed to (?:initialize|create) (?:the )?(?:map|renderer|worker)|style (?:parse|validation) error/i.test(message);
    }

    async function failToFallback(error) {
      if (disposed || fallbackStarted) return;
      fallbackStarted = true;
      if (mapStartupTimer) clearTimeout(mapStartupTimer);
      // Keep the fallback usable, but preserve the renderer failure for browser CI.
      // Never log incident payloads, coordinates, or source evidence.
      console.warn('[PLAY_MAP_RENDERER_FALLBACK]', error?.name || 'Error', String(error?.message || 'unknown').slice(0, 240));
      if (window.__SEACOMMONS_EXPOSE_PLAY_MAP__ === true) delete window.__SEACOMMONS_PLAY_MAP__;
      return activateFallbackMap().catch(() => {
        if (!disposed) setMapError('Map unavailable. Archive cases remain available.');
      });
    }

    async function initMap() {
      if (window.__SEACOMMONS_FORCE_MAP_FALLBACK__ === true) throw new Error('forced map fallback');
      await import('maplibre-gl/dist/maplibre-gl.css');
      const maplibreModule = await import('maplibre-gl');
      // ESM builds expose Map/NavigationControl as named exports; a default export
      // is not guaranteed (and may be undefined in Vite/browser builds).
      const maplibregl = maplibreModule.Map ? maplibreModule : maplibreModule.default;
      configureMaplibreWorker(maplibregl);
      if (typeof maplibregl?.Map !== 'function') {
        throw new TypeError('MapLibre module did not export a Map constructor');
      }
      if (disposed || !mapNodeRef.current || mapRef.current) return;
      const map = new maplibregl.Map({
        container: mapNodeRef.current,
        style: playMapStyle(), center: [14.8, 35.7], zoom: 3.55,
        attributionControl: false,
      });
      mapRef.current = map;
      map.addControl(new maplibregl.NavigationControl({ showCompass: true }), 'bottom-right');
      // Opt-in E2E diagnostics expose the real production-style map without replacing its style.
      if (window.__SEACOMMONS_EXPOSE_PLAY_MAP__ === true) window.__SEACOMMONS_PLAY_MAP__ = map;
      mapStartupTimer = setTimeout(() => {
        void failToFallback(new Error('MapLibre startup timed out before the style loaded'));
      }, 15_000);
      map.on('error', (event) => {
        if (rendererFailureIsFatal(event?.error)) void failToFallback(event.error);
      });
      mapCanvas = map.getCanvas();
      contextLossHandler = (event) => {
        event.preventDefault();
        void failToFallback(new Error('webglcontextlost'));
      };
      mapCanvas.addEventListener('webglcontextlost', contextLossHandler, false);
      // Initialize case layers when the style is ready, without waiting for remote
      // satellite/OSM raster tiles to load. A slow basemap must not hide evidence.
      map.on('style.load', () => {
        if (disposed || fallbackStarted) return;
        if (mapStartupTimer) clearTimeout(mapStartupTimer);
        map.addImage('vessel-arrow', createVesselArrowImage(48), { sdf: true });
        map.addImage('attack-crosshair', createAttackMarkerImage());
        map.addSource('play-incidents', {
          type: 'geojson', data: { type: 'FeatureCollection', features: [] },
          cluster: true, clusterMaxZoom: 7, clusterRadius: 42,
        });
        // A cluster represents a viewport grouping, never a deduplicated archive record.
        map.addLayer({
          id: 'play-clusters', type: 'circle', source: 'play-incidents',
          filter: ['has', 'point_count'],
          paint: {
            'circle-radius': ['step', ['get', 'point_count'], 14, 20, 18, 100, 23],
            'circle-color': '#27566b', 'circle-opacity': 0.94,
            'circle-stroke-color': '#b3e8fa', 'circle-stroke-width': 1.5,
          },
        });
        map.addLayer({
          id: 'play-search-areas-fill', type: 'fill', source: 'play-incidents',
          filter: ['all', ['==', ['get', 'marker_kind'], 'search_area'], ['==', ['get', 'incident_id'], selectedId]],
          paint: {
            'fill-color': ['coalesce', ['get', 'visual_color'], '#ff3b3b'],
            'fill-opacity': ['case', ['==', ['get', 'incident_id'], selectedId], 0.18, 0.08],
          },
        });
        map.addLayer({
          id: 'play-search-areas-line', type: 'line', source: 'play-incidents',
          filter: ['all', ['==', ['get', 'marker_kind'], 'search_area'], ['==', ['get', 'incident_id'], selectedId]],
          paint: {
            'line-color': ['coalesce', ['get', 'visual_color'], '#ff3b3b'],
            'line-width': ['case', ['==', ['get', 'incident_id'], selectedId], 2.4, 1.4],
            'line-opacity': 0.9,
            'line-dasharray': [3, 2],
          },
        });
        map.addLayer({
          id: 'play-incidents', type: 'circle', source: 'play-incidents',
          filter: ['all', ['!', ['has', 'point_count']], ['any', ['!=', ['get', 'marker_kind'], 'vessel'], ['!=', ['get', 'has_course'], true]]],
          paint: {
            'circle-radius': ['case', ['==', ['get', 'incident_id'], selectedId], 8, 5],
            'circle-color': ['coalesce', ['get', 'visual_color'], '#c6a6ff'],
            'circle-opacity': 0.9,
            'circle-stroke-color': '#071014', 'circle-stroke-width': 1,
          },
        });
        map.addLayer({
          id: 'play-vessels', type: 'symbol', source: 'play-incidents',
          filter: ['all', ['!', ['has', 'point_count']], ['==', ['get', 'marker_kind'], 'vessel'], ['==', ['get', 'has_course'], true]],
          layout: {
            'icon-image': 'vessel-arrow',
            'icon-size': ['interpolate', ['linear'], ['zoom'], 3, 0.20, 7, 0.34, 10, 0.46],
            'icon-rotate': ['coalesce', ['get', 'course'], 0],
            'icon-rotation-alignment': 'map',
            'icon-allow-overlap': true,
          },
          paint: { 'icon-color': ['coalesce', ['get', 'visual_color'], '#c6a6ff'], 'icon-opacity': 0.94 },
        });
        map.addLayer({
          id: 'play-vessels-unknown-course', type: 'circle', source: 'play-incidents',
          filter: ['all', ['==', ['get', 'marker_kind'], 'vessel'], ['==', ['get', 'course'], null]],
          paint: { 'circle-radius': 5, 'circle-color': ['coalesce', ['get', 'visual_color'], VESSEL_COLOR],
            'circle-stroke-color': '#071014', 'circle-stroke-width': 1.5 },
        });
        map.addSource('play-attacks', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        map.addLayer({ id: 'play-attack-markers', type: 'symbol', source: 'play-attacks',
          layout: { 'icon-image': 'attack-crosshair', 'icon-size': 0.42,
            'icon-allow-overlap': true, 'icon-ignore-placement': true } });
        map.addSource('play-historical-drifts', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        map.addLayer({
          id: 'play-historical-drift-uncertainty', type: 'fill', source: 'play-historical-drifts',
          filter: ['==', ['get', 'geometry_semantics'], 'model_uncertainty_area'],
          paint: { 'fill-color': '#bb8cff', 'fill-opacity': 0.13 },
        });
        map.addLayer({
          id: 'play-historical-drift-uncertainty-outline', type: 'line', source: 'play-historical-drifts',
          filter: ['==', ['get', 'geometry_semantics'], 'model_uncertainty_area'],
          paint: { 'line-color': '#bb8cff', 'line-width': 1.4, 'line-dasharray': [3, 2] },
        });
        map.addLayer({
          id: 'play-historical-drift-trajectory', type: 'line', source: 'play-historical-drifts',
          filter: ['==', ['get', 'geometry_semantics'], 'simulated_trajectory'],
          paint: { 'line-color': '#d2aaff', 'line-width': 2.5, 'line-dasharray': [2, 1] },
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
          paint: { 'line-color': ['match', ['get', 'kind'], 'observed_ais_track', '#76b7fa', 'drift', '#ffad66', 'drift_model', '#ffad66', '#b9a1f6'], 'line-width': 3, 'line-opacity': 0.9 },
        });
        map.addSource('play-ais-gaps', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        map.addLayer({ id: 'play-ais-gap-connection', type: 'line', source: 'play-ais-gaps',
          filter: ['==', ['get', 'kind'], 'ais_gap_unobserved_connection'],
          paint: { 'line-color': '#ffba65', 'line-width': 2.6, 'line-dasharray': [2, 2], 'line-opacity': 0.95 } });
        map.addLayer({ id: 'play-ais-gap-endpoints', type: 'circle', source: 'play-ais-gaps',
          filter: ['==', ['geometry-type'], 'Point'],
          paint: { 'circle-radius': 7, 'circle-color': ['match', ['get', 'kind'],
            'ais_last_observed', '#ff8859', 'ais_first_reappearance', '#55e0c0', '#ffffff'],
            'circle-stroke-color': '#071014', 'circle-stroke-width': 2 } });
        // Tap/click either observed endpoint to inspect the same bounded gap.
        map.on('click', 'play-ais-gap-endpoints', (event) => {
          const feature = event.features?.[0];
          if (!feature || feature.geometry?.type !== 'Point') return;
          const props = feature.properties || {};
          const endpoint = props.kind === 'ais_last_observed' ? 'Last AIS observation' : 'First AIS reappearance';
          const coordinates = feature.geometry.coordinates;
          new maplibregl.Popup({ closeButton: true, maxWidth: '300px' })
            .setLngLat(coordinates)
            .setText(`${endpoint} · ${props.at || 'time unknown'} UTC · MMSI ${props.mmsi || 'unknown'} · ${props.duration_min} min without stored AIS fixes · ${props.distance_km} km between endpoints. Actual route unknown.`)
            .addTo(map);
        });
        map.on('mouseenter', 'play-ais-gap-endpoints', () => { map.getCanvas().style.cursor = 'pointer'; });
        map.on('mouseleave', 'play-ais-gap-endpoints', () => { map.getCanvas().style.cursor = ''; });
        map.addSource('play-satellite-footprints', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        map.addLayer({
          id: 'play-satellite-footprint-fill', type: 'fill', source: 'play-satellite-footprints',
          paint: { 'fill-color': '#75a7ff', 'fill-opacity': 0.08 },
        });
        map.addLayer({
          id: 'play-satellite-footprint-line', type: 'line', source: 'play-satellite-footprints',
          paint: { 'line-color': '#75a7ff', 'line-width': 1.5, 'line-opacity': 0.85, 'line-dasharray': [2, 2] },
        });
        const selectArchiveFeature = (event) => {
          const rendered = map.queryRenderedFeatures(event.point, { layers: ['play-incidents', 'play-vessels'] });
          const ids = [...new Set(rendered
            .map((feature) => feature.properties?.incident_id)
            .filter(Boolean)
            .map(String))];
          if (ids.length > 1) {
            setOverlapIds(ids);
            return;
          }
          const id = ids[0] || event.features?.[0]?.properties?.incident_id;
          if (id) {
            setOverlapIds([]);
            setSelectedId(String(id));
            setCasesOpen(false);
          }
        };
        map.on('click', 'play-clusters', async (event) => {
          const clusterId = event.features?.[0]?.properties?.cluster_id;
          const coordinates = event.features?.[0]?.geometry?.coordinates;
          if (clusterId == null || !Array.isArray(coordinates)) return;
          setOverlapIds([]);
          try {
            const zoom = await map.getSource('play-incidents').getClusterExpansionZoom(clusterId);
            map.easeTo({ center: coordinates, zoom: Math.min(zoom, 18) });
          } catch { /* source replaced during navigation */ }
        });
        // Cluster clicks only expand the group; they must never open a synthetic dossier.
        // Match individual markers: make expandable groups discoverable without changing evidence.
        map.on('mouseenter', 'play-clusters', () => { map.getCanvas().style.cursor = 'pointer'; });
        map.on('mouseleave', 'play-clusters', () => { map.getCanvas().style.cursor = ''; });
        for (const layerId of ['play-search-areas-fill', 'play-search-areas-line', 'play-incidents', 'play-vessels', 'play-vessels-unknown-course']) {
          map.on('click', layerId, selectArchiveFeature);
          map.on('mouseenter', layerId, () => { map.getCanvas().style.cursor = 'pointer'; });
          map.on('mouseleave', layerId, () => { map.getCanvas().style.cursor = ''; });
        }
        // Explicitly opt-in for deterministic browser E2E; never enabled for normal visitors.
        map.resize();
        setMapError('');
        setMapReady(true);
        // MapLibre style.load precedes worker GeoJSON processing. Keep the
        // loading shield until incident markers have actually been decoded.
        const revealWhenIncidentsReady = () => {
          if (!disposed && map.getSource('play-incidents') && map.isSourceLoaded('play-incidents')) {
            setMapContentReady(true);
            map.off('sourcedata', revealWhenIncidentsReady);
          }
        };
        map.on('sourcedata', revealWhenIncidentsReady);
        revealWhenIncidentsReady();
        // A style can load while its GeoJSON worker remains stalled. Do not
        // leave visitors with an empty but apparently healthy WebGL canvas.
        mapStartupTimer = window.setTimeout(() => {
          if (disposed || fallbackStarted) return;
          if (!map.getSource('play-incidents') || !map.isSourceLoaded('play-incidents')) {
            void failToFallback(new Error('PLAY incident source did not finish loading'));
          }
        }, 15_000);
      });
    }
    async function activateFallbackMap() {
      if (disposed || !mapNodeRef.current) return;
      setMapReady(false);
      setMapContentReady(false);
      if (mapCanvas && contextLossHandler) mapCanvas.removeEventListener('webglcontextlost', contextLossHandler, false);
      try { mapRef.current?.remove(); } catch { /* partial MapLibre init */ }
      mapRef.current = null;
      mapNodeRef.current.replaceChildren();
      const fallback = await createFallbackMap({
        container: mapNodeRef.current,
        center: [14.8, 35.7],
        zoom: 3.55,
        onFeatureSelect: (feature) => {
          const incidentId = feature?.properties?.incident_id;
          if (incidentId) {
            setSelectedId(String(feature.properties.incident_id));
            setCasesOpen(false);
          }
        },
      });
      if (disposed) { fallback.destroy(); return; }
      fallbackMapRef.current = fallback;
      setMapError('');
      setFallbackReady(true);
      setMapContentReady(true);
    }
    initMap().catch(failToFallback);
    return () => {
      disposed = true;
      if (mapStartupTimer) clearTimeout(mapStartupTimer);
      if (mapCanvas && contextLossHandler) mapCanvas.removeEventListener('webglcontextlost', contextLossHandler, false);
      try { mapRef.current?.remove(); } catch { /* already removed */ }
      mapRef.current = null;
      if (window.__SEACOMMONS_EXPOSE_PLAY_MAP__ === true) delete window.__SEACOMMONS_PLAY_MAP__;
      fallbackMapRef.current?.destroy();
      fallbackMapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const fallback = fallbackMapRef.current;
    if (!fallbackReady || !fallback) return;
    fallback.setFeatures(mappedIncidents.features);
    if (mappedIncidents.features.length) fallback.fitFeatures(mappedIncidents.features);
    const geometry = selectedIncident?.geometry;
    const bounds = geometryBounds(geometry);
    if (selectedId && bounds) {
      fallback.flyTo({ center: bounds.center, zoom: geometry?.type === 'Point' ? 6.5 : 5.2 });
    }
  }, [fallbackReady, mappedIncidents, selectedId, selectedIncident]);

  useEffect(() => {
    const map = mapRef.current;
    if (!mapReady || !map) return;
    map.getSource('play-incidents')?.setData(mappedIncidents);
    map.getSource('play-attacks')?.setData({ type: 'FeatureCollection', features: mappedIncidents.features.filter((f) => f.geometry?.type === 'Point' && isAttackIncident(f.properties)) });
    if (map.getLayer('play-attack-markers')) map.moveLayer('play-attack-markers');
    const datedEvidence = evidenceCollection(visibleTimeline);
    datedEvidence.features.push(...aisReconstruction.observed.features);
    map.getSource('play-evidence')?.setData(datedEvidence);
    map.getSource('play-ais-gaps')?.setData(gapFeatures);
    map.getSource('play-historical-drifts')?.setData(historicalDriftFeatures(visibleTimeline));
    map.getSource('play-satellite-footprints')?.setData(satelliteFootprintCollection(visibleTimeline));
  }, [mapReady, mappedIncidents, visibleTimeline, aisReconstruction, gapFeatures]);

  useEffect(() => {
    const map = mapRef.current;
    if (!mapReady || !map) return;
    if (map.getLayer('play-incidents')) {
      map.setPaintProperty('play-incidents', 'circle-radius', ['case', ['==', ['get', 'incident_id'], selectedId], 8, 5]);
    }
    if (map.getLayer('play-search-areas-fill')) {
      map.setFilter('play-search-areas-fill', ['all', ['==', ['get', 'marker_kind'], 'search_area'], ['==', ['get', 'incident_id'], selectedId]]);
      map.setPaintProperty('play-search-areas-fill', 'fill-opacity', ['case', ['==', ['get', 'incident_id'], selectedId], 0.18, 0.08]);
    }
    if (map.getLayer('play-search-areas-line')) {
      map.setFilter('play-search-areas-line', ['all', ['==', ['get', 'marker_kind'], 'search_area'], ['==', ['get', 'incident_id'], selectedId]]);
      map.setPaintProperty('play-search-areas-line', 'line-width', ['case', ['==', ['get', 'incident_id'], selectedId], 2.4, 1.4]);
    }
    if (map.getLayer('play-vessels')) {
      map.setLayoutProperty('play-vessels', 'icon-size', ['interpolate', ['linear'], ['zoom'], 3, ['case', ['==', ['get', 'incident_id'], selectedId], 0.30, 0.20], 7, ['case', ['==', ['get', 'incident_id'], selectedId], 0.46, 0.34], 10, ['case', ['==', ['get', 'incident_id'], selectedId], 0.58, 0.46]]);
    }
    addSatelliteLayer(map, satellite);
    // Always render evidence markers above footprints, routes and satellite rasters.
    for (const layerId of ['play-incidents', 'play-vessels']) {
      if (map.getLayer(layerId)) map.moveLayer(layerId);
    }
  }, [mapReady, selectedId, satellite]);

  const selectedLongitude = selectedIncident?.geometry?.type === 'Point' ? selectedIncident.geometry.coordinates?.[0] : null;
  const selectedLatitude = selectedIncident?.geometry?.type === 'Point' ? selectedIncident.geometry.coordinates?.[1] : null;

  // Camera movement is a selection action, not an evidence-refresh side effect.
  // Timeline fetches and satellite updates must not override an analyst's pan/zoom
  // or a WebGL test's explicit camera movement while the same dossier is selected.
  useEffect(() => {
    const map = mapRef.current;
    if (!mapReady || !map || !selectedId) return;
    if (!Number.isFinite(selectedLongitude) || !Number.isFinite(selectedLatitude)) return;
    const mobile = window.matchMedia?.('(max-width: 680px)')?.matches;
    map.easeTo({
      center: [selectedLongitude, selectedLatitude],
      zoom: Math.max(map.getZoom(), 6.5),
      padding: mobile ? { top: 16, bottom: Math.round(window.innerHeight * 0.52), left: 24, right: 24 } : { top: 20, bottom: 80, left: 412, right: 340 },
      duration: 450,
    });
    // Primitive coordinate dependencies prevent unrelated evidence refreshes from recentering.
  }, [mapReady, selectedId, selectedLongitude, selectedLatitude]);

  // Search-area selection is a geographic extent, never a fabricated point fix.
  // Only a selection change moves the camera; background evidence refresh does not.
  useEffect(() => {
    const map = mapRef.current;
    if (!mapReady || !map || !selectedId) return;
    const geometry = selectedIncident?.geometry;
    if (!['Polygon', 'MultiPolygon'].includes(geometry?.type)) return;
    const bounds = geometryBounds(geometry);
    if (!bounds) return;
    const mobile = window.matchMedia?.('(max-width: 680px)')?.matches;
    map.fitBounds(
      [[bounds.west, bounds.south], [bounds.east, bounds.north]],
      { padding: mobile ? { top: 24, bottom: Math.round(window.innerHeight * 0.66), left: 24, right: 24 } : { top: 20, bottom: 80, left: 412, right: 340 },
        maxZoom: 6.2, duration: 450 },
    );
  }, [mapReady, selectedId, selectedIncident?.geometry]);

  useEffect(() => {
    const map = mapRef.current;
    if (mapReady && map) window.setTimeout(() => map.resize(), 40);
  }, [mapReady, selectedId, casesOpen, filteredIncidents.length]);

  useEffect(() => {
    const map = mapRef.current;
    if (!mapReady || !map) return;
    const source = map.getSource('satelliteContext');
    source?.setTiles?.([satelliteContextTileUrl(contextDay, satelliteContextMission)]);
    if (map.getLayer('satellite-context')) map.setLayoutProperty('satellite-context', 'visibility', satelliteVisible ? 'visible' : 'none');
  }, [mapReady, satelliteVisible, contextDay, satelliteContextMission]);

  const status = selectedIncident ? incidentStatusAtCutoff(selectedIncident, globalState.cutoff) : 'outcome_unknown';
  const reportTrack = useMemo(() => timelineReport(visibleTimeline), [visibleTimeline]);
  const reportEvidence = visibleTimeline.filter((item) => item?.type !== 'satellite');
  const frameProps = frame.item?.properties || {};
  const satelliteProps = satellite?.properties || {};
  const modeLabel = cutoffLabel(globalState);
  const report = selectedIncident ? {
    schema: 'org.seacommons.play-case-report/v1',
    generated_at: new Date().toISOString(),
    case_id: selectedIncident.incident_id,
    title: selectedIncident.title || 'Maritime incident',
    reported_at: selectedIncident.reported_at || null,
    source: selectedIncident.source || null,
    status_at_cutoff: status,
    cutoff: globalState.cutoff || null,
    archive_decision: caseData?.archive_decision || selectedIncident.archive_decision || null,
    verification_status: caseData?.verification_status || null,
    corroborated: caseData?.corroborated ?? null,
    independent_lineages: caseData?.independence_groups || [],
    reason_codes: dossierReasonCodes,
    counter_indicators: caseData?.counter_indicators || [],
    evidence_count_at_cutoff: visibleTimeline.length,
    geometry: selectedIncident.geometry || null,
    evidence: visibleTimeline.map((item) => ({
      id: item.id, at: item.at, type: item.type, title: item.title || '',
      source: item.source || null, url: item.properties?.url || item.properties?.source_url || null,
      properties: item.properties || {}, geometry: item.geometry || null,
    })),
    assessment: caseData?.assessment || selectedIncident.assessment || null,
    limitations: 'This report represents evidence available at the selected historical cutoff. Unknown outcomes and unverified observations must not be interpreted as confirmed events.',
  } : null;
  const downloadReport = () => {
    if (!report) return;
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `seacommons-play-report-${String(report.case_id).replace(/[^a-zA-Z0-9_-]/g, '_')}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const startupPending = !startupGraceExpired && (loading || (!mapContentReady && !mapError));

  return (
    <main className={`cop-shell is-live-mode play-public-shell play-shell ${selectedId ? 'has-selection' : ''}`}>
      {startupPending ? (
        <div className="play-startup-overlay" role="status" aria-live="polite" aria-label="Loading SeaCommons PLAY">
          <div className="play-startup-overlay__inner">
            <span className="play-startup-overlay__eyebrow">SEACOMMONS / TEMPORAL INTELLIGENCE</span>
            <strong>Preparing PLAY</strong>
            <span className="play-startup-overlay__spinner" aria-hidden="true" />
            <p>{loading ? 'Loading historical evidence…' : 'Initializing the interactive map…'}</p>
            <small>Historical records remain distinct from simulated drift and unobserved AIS gaps.</small>
          </div>
        </div>
      ) : null}
      <header className="play-header" aria-hidden="true">
        <div>
          <p className="play-eyebrow">SeaCommons / temporal OSINT reconstruction</p>
          <h1>PLAY</h1>
        </div>
        <div className="play-header__actions">
          <div className="play-header__meta">
            <span>{globalState.mode === 'all' && !selectedDay ? 'Complete archive' : 'Selected day'}</span>
            <strong>{globalState.mode === 'all' && !selectedDay && archiveTotal != null ? archiveTotal : visibleIncidents.length}</strong>
          </div>
        </div>
      </header>

      <button className="live-feed-toggle play-mobile-cases-toggle" type="button" onClick={() => setCasesOpen((value) => !value)}>
        Archive · {globalState.mode === 'all' && !selectedDay && archiveTotal != null ? archiveTotal : visibleIncidents.length}
      </button>

      <aside className={`live-feed-panel is-open play-archive-panel play-cases ${casesOpen ? 'is-mobile-open' : ''}`}>
        <header className="live-feed-panel__header">
          <div className="live-feed-panel__eyebrow">
            <span className="live-feed-panel__mark">SC</span>
            <span>SEACOMMONS / MEDITERRANEAN</span>
            <b><i /> ARCHIVE</b>
          </div>
          <div className="live-feed-panel__title">
            <div><p>TEMPORAL OSINT RECONSTRUCTION</p><h1>Play</h1></div>
            <button type="button" onClick={() => setCasesOpen(false)} aria-label="Close archive">−</button>
          </div>
          <div className="signals-selector play-filter-selector" role="group" aria-label="Play archive filters">
            <div className="signals-selector__list">
              <button type="button" className={`signals-selector__link ${archiveFilter === 'all' ? 'is-active' : ''}`} onClick={() => setArchiveFilter('all')}><span className="signals-selector__box" aria-hidden="true" />ALL</button>
              <button type="button" className={`signals-selector__link ${archiveFilter === 'humanitarian' ? 'is-active' : ''}`} onClick={() => setArchiveFilter('humanitarian')}><span className="signals-selector__box" aria-hidden="true" />HUMANITARIAN</button>
              <button type="button" className={`signals-selector__link ${archiveFilter === 'maritime' ? 'is-active' : ''}`} onClick={() => setArchiveFilter('maritime')}><span className="signals-selector__box" aria-hidden="true" />MARITIME</button>
              <button type="button" className={`signals-selector__link ${archiveFilter === 'attacks' ? 'is-active' : ''}`} onClick={() => { setArchiveFilter('attacks'); setIncidentTypeFilter('all'); }}><span className="signals-selector__box" aria-hidden="true" />ATTACKS</button>
            </div>
            <label className="play-satellite-selector">
              <span>Incident type</span>
              <select value={incidentTypeFilter} onChange={(event) => setIncidentTypeFilter(event.target.value)}>
                <option value="all">All incident types</option>
                {incidentTypes.map((type) => (
                  <option key={type} value={type}>{type.replace(/_/g, ' ')}</option>
                ))}
              </select>
            </label>
            <label className="play-satellite-selector">
              <span>Evidence confidence</span>
              <select value={evidenceFilter} onChange={(event) => setEvidenceFilter(event.target.value)} aria-label="Filter by evidence confidence">
                <option value="all">All evidence levels</option>
                <option value="confirmed">Confirmed by independent sources</option>
                <option value="unconfirmed">Not independently confirmed</option>
                <option value="conflicting">Conflicting evidence</option>
              </select>
            </label>
            <div className="signals-selector__list" aria-label="Evidence facets">
              <button type="button" className={`signals-selector__link ${satelliteOnly ? 'is-active' : ''}`} onClick={() => setSatelliteOnly((value) => !value)}><span className="signals-selector__box" aria-hidden="true" />SATELLITE</button>
              <button type="button" className={`signals-selector__link ${sanctionsOnly ? 'is-active' : ''}`} onClick={() => setSanctionsOnly((value) => !value)}><span className="signals-selector__box" aria-hidden="true" />SANCTIONS</button>
              <button type="button" className={`signals-selector__link ${investigationsOnly ? 'is-active' : ''}`} onClick={() => setInvestigationsOnly((value) => !value)}><span className="signals-selector__box" aria-hidden="true" />INVESTIGATION</button>
            </div>
          </div>
          <div className="play-archive-continuity">
            <p className="live-feed-panel__continuity"><span />Evidence is bounded to what was knowable at the selected cutoff.</p>
            {coverage.start && coverage.end ? (
              <p>{coverage.start.slice(0, 10)} → {coverage.end.slice(0, 10)} · {coverage.coveredMonths.length} months with public cases · {coverage.missingMonths.length} continuity gaps</p>
            ) : null}
          </div>
        </header>
        <details className="play-sanctions-section">
          <summary>Sanctioned vessels · historical registry</summary>
          <SanctionsCatalog apiBase={apiBase} />
        </details>
        <div className="live-feed-panel__body play-cases__list">
          {archiveGroups.map((group) => (
            <section className="play-archive-month" key={group.key}>
              <header><strong>{group.label}</strong><span>{group.incidents.length} cases</span></header>
              {group.incidents.map((incident) => {
                const counts = incident.evidence_counts || {};
                return (
                  <button
                    key={incident.incident_id}
                    type="button"
                    className={`play-case ${selectedId === incident.incident_id ? 'is-active' : ''}`}
                    onClick={() => { setSelectedId(incident.incident_id); setCasesOpen(false); }}
                  >
                    <span className="play-case__time">{itemTime(incident.reported_at)}</span>
                    <strong>{incident.title || 'SeaCommons incident'}</strong>
                    <span>{evidenceLabel(incident)}</span>
                    <span>{(incident.incident_type || 'context').replace(/_/g, ' ')} · {incident.main_category || incident.domain || 'humanitarian'} · {statusLabel(incidentStatusAtCutoff(incident, globalState.cutoff))}</span>
                    {(Number(counts.drift) > 0 || Number(counts.satellite) > 0) ? (
                      <span className="play-case__evidence">
                        {Number(counts.drift) > 0 ? <b>DRIFT {counts.drift}</b> : null}
                        {Number(counts.satellite) > 0 ? <b>SAT {counts.satellite}</b> : null}
                      </span>
                    ) : null}
                  </button>
                );
              })}
            </section>
          ))}
          {filteredIncidents.length > displayedCases.length ? <button type="button" className="play-case-load-more" onClick={() => setVisibleCaseLimit((limit) => limit + 80)}>Show 80 more cases · {displayedCases.length} of {filteredIncidents.length} loaded</button> : null}
          {!filteredIncidents.length && !loading ? <div className="play-empty">{archiveFilter === 'attacks' ? 'No explicitly classified attacks in the public archive for this selection. An AIS gap or an unverified report is not evidence of an attack.' : 'No incidents at this time.'}</div> : null}
        </div>
      </aside>

      <section className="map-stage play-map-stage">
        <div className="map-frame play-map" ref={mapNodeRef} />
        <div className="play-cartographic-legend" aria-label="Map symbols and evidence legend">
          <strong>MAP KEY</strong>
          <span><i className="play-key-vessel" /> Vessel · heading observed</span>
          <span><i className="play-key-point" /> Incident / unknown heading</span>
          <span><i className="play-key-humanitarian" /> Humanitarian</span>
          <span><i className="play-key-maritime" /> Maritime context</span>
          <span><i className="play-key-integrity" /> Position integrity</span>
          <span><i className="play-key-ais-gap" /> AIS reporting gap</span>
          <span><i className="play-key-attack" /> Attack · crosshair overlay</span>
          <span><i className="play-key-track" /> Observed AIS track</span>
          <span><i className="play-key-drift" /> AIS gap: dashed, unobserved; orange last fix, green reappearance</span>
          <span><i className="play-key-model" /> Drift / estimated area (modelled)</span>
          <small>Triangles show reported course only. Circles do not imply direction. Color indicates category, not verification.</small>
        </div>
        <div className="play-all-badge"><strong>{modeLabel}</strong><span>{mappedIncidentCount} mapped / {filteredIncidents.length} filtered · {incidents.length} loaded{archiveTotal != null ? ` / ${archiveTotal} archive` : ''}</span></div>
        {loading ? <div className="play-map-message" role="status" aria-live="polite">Loading archive and case evidence…</div> : null}
        {error ? <div className="play-map-message is-error">{error}</div> : null}
        {mapError ? <div className="play-map-message is-error">{mapError}</div> : null}
        {selectedId ? (
          <div className="play-map-status">
            <span>{selectedIncident?.source || 'incident'}</span>
            <strong>{statusLabel(status)}</strong>
            {satellite ? <span>{satelliteProps.mission || satellite.source} · {satelliteProps.temporal_relation || 'snapshot'}</span> : null}
          </div>
        ) : null}
      </section>

      {overlapIncidents.length > 1 ? (
        <div className="play-overlap-picker" role="dialog" aria-label="Overlapping archive records">
          <div className="play-overlap-picker__header"><strong>Multiple records at this position</strong><button type="button" onClick={() => setOverlapIds([])} aria-label="Close overlapping records">&times;</button></div>
          <p>Choose the archive dossier to open. Co-location does not imply duplicate evidence.</p>
          <div className="play-overlap-picker__records">
            {overlapIncidents.map((incident) => (
              <button
                key={incident.incident_id}
                type="button"
                onClick={() => { setSelectedId(incident.incident_id); setOverlapIds([]); setCasesOpen(false); }}
              >
                <strong>{incident.title || 'SeaCommons incident'}</strong>
                <span>{itemTime(incident.reported_at)} &middot; {incident.source || 'source unavailable'}</span>
              </button>
            ))}
          </div>
        </div>
      ) : null}

      <aside className={`cone-panel cone-panel--intel play-evidence ${selectedId ? 'is-open' : ''}`}>
        <div className="play-sheet-handle" />
        <div className="cone-panel-header play-section-head">
          <span>Case dossier</span>
          <button type="button" className="play-report-trigger" disabled={!selectedIncident || loading} onClick={() => setReportOpen(true)}>Report ↗</button>
          <button className="cone-close-btn" type="button" onClick={() => setSelectedId('')}>×</button>
        </div>
        <div className="play-evidence__scroll">
          <section className="play-card">
            <p>{(selectedIncident?.incident_type || caseData?.incident_type || 'incident').replace(/_/g, ' ')} · {selectedIncident?.main_category || selectedIncident?.domain || caseData?.main_category || caseData?.domain || 'maritime'}</p>
            <h2>{selectedIncident?.title || 'SeaCommons incident'}</h2>
            <time>{itemTime(selectedIncident?.reported_at)}</time>
            <button type="button" disabled={!selectedIncident?.geometry} onClick={() => { const geometry = selectedIncident?.geometry; if (geometry?.type !== 'Point') return; mapRef.current?.easeTo({ center: geometry.coordinates, zoom: Math.max(9, mapRef.current.getZoom()), duration: 600 }); fallbackMapRef.current?.flyTo({ center: geometry.coordinates, zoom: 9 }); }}>Locate on map +</button>
            <span>{selectedIncident?.source || '—'}</span>
          </section>
          <section className="play-card play-card--forensic-summary">
            <p>Forensic assessment</p>
            <h3>{evidenceLabel(caseData || selectedIncident)}</h3>
            <p>{caseData?.assessment?.observation || selectedIncident?.assessment?.observation || 'The archive contains a reported incident. Its underlying evidence must be assessed separately from the reported claim.'}</p>
            <p>{caseData?.assessment?.interpretation || selectedIncident?.assessment?.interpretation || 'This dossier distinguishes the original report, supporting observations, independent confirmation and any unresolved questions.'}</p>
            <small>Assessment reflects only records available at the selected historical time. It is not an official incident determination.</small>
          </section>
          <section className="play-card play-report-section">
            <p>Forensic report · reconstructed at selected cutoff</p>
            <h3>Executive summary</h3>
            <p className="play-report-prose">{selectedIncident?.title || 'Maritime incident recorded in the SeaCommons archive.'} Reported {itemTime(selectedIncident?.reported_at)} UTC. The archive records {visibleTimeline.length} dated evidence item(s) at this cutoff. {caseData?.corroborated === true ? 'Independent corroboration is recorded.' : 'Independent corroboration is not established from the available record.'}</p>
            <h3>Trajectory and geographical evidence</h3>
            {reportTrack.positions.length > 0 ? <>
              <p className="play-report-prose">{reportTrack.positions.length} mapped observation point(s) or geometry vertices are preserved in the selected evidence. These are not necessarily successive AIS fixes; a line may represent a modelled path rather than observed travel.</p>
              <div className="play-report-locations">
                <span>First mapped point: {reportTrack.positions[0].coordinates[1]?.toFixed?.(4) ?? reportTrack.positions[0].coordinates[1]}, {reportTrack.positions[0].coordinates[0]?.toFixed?.(4) ?? reportTrack.positions[0].coordinates[0]}</span>
                <span>Last mapped point: {reportTrack.positions.at(-1).coordinates[1]?.toFixed?.(4) ?? reportTrack.positions.at(-1).coordinates[1]}, {reportTrack.positions.at(-1).coordinates[0]?.toFixed?.(4) ?? reportTrack.positions.at(-1).coordinates[0]}</span>
              </div>
            </> : <p className="play-report-prose">No observed trajectory is documented in this case at the selected cutoff. SeaCommons will not reconstruct a route from missing positions.</p>}
            {voyageVessels.length > 0 && <>
              <h3>Verified AIS records and voyage reconstruction</h3>
              {voyageVessels.map((v) => <div className="play-voyage-card" key={v.mmsi}>
                <strong>MMSI {v.mmsi} · {v.track_points.length} stored AIS fixes at this cutoff</strong>
                {v.track_points.length >= 2 && <p className="play-report-prose">First received position: {itemTime(v.track_points[0].at)} UTC, {v.track_points[0].lat.toFixed(4)}, {v.track_points[0].lon.toFixed(4)}. Latest received position: {itemTime(v.track_points.at(-1).at)} UTC, {v.track_points.at(-1).lat.toFixed(4)}, {v.track_points.at(-1).lon.toFixed(4)}.</p>}
                {aisReconstruction.gaps.filter((g) => g.mmsi === v.mmsi).map((g, i) => <div key={i} className="play-ais-gap-card">
                  <strong>AIS observation gap · {Math.round(g.durationMin)} min</strong>
                  <span><i className="play-ais-gap-dot is-lost" />Last observed: {g.from.at} · {Number(g.from.lat).toFixed(4)}, {Number(g.from.lon).toFixed(4)}</span>
                  <span><i className="play-ais-gap-dot is-returned" />First reappearance: {g.to.at} · {Number(g.to.lat).toFixed(4)}, {Number(g.to.lon).toFixed(4)}</span>
                  <span>Endpoint separation: {g.distanceKm.toFixed(1)} km · not distance travelled</span>
                  <small>Dashed map line is an unobserved interval, not a verified route. Cause unknown; AIS reception/provider coverage may be incomplete.</small>
                </div>)}
                {v.ais_derived_port_calls?.filter((call) => !globalState.cutoff || Date.parse(call.arrived_at) <= Date.parse(globalState.cutoff)).map((call, i) => <p key={i} className="play-report-prose">AIS-derived port approach: {call.port}, first observed {itemTime(call.arrived_at)} UTC. Not an official port authority confirmation.</p>)}
                <p className="play-report-prose">{v.limits}</p>
              </div>)}
            </>}
            <h3>Chronology</h3>
            {reportEvidence.length ? <ol className="play-report-chronology">{reportEvidence.map((item, index) => <li key={item.id || `${item.at}-${index}`}><time>{itemTime(item.at)} UTC</time><strong>{String(item.type || 'Observation').replaceAll('_', ' ')}</strong><span>{humanizeDetectorText(item.title || item.properties?.description || 'Recorded evidence')}</span>{(item.properties?.source_url || item.properties?.url) && <a href={item.properties.source_url || item.properties.url} target="_blank" rel="noreferrer">Original source ↗</a>}</li>)}</ol> : <p className="play-report-prose">No detailed sequence of observations is available yet.</p>}
            <h3>Evidence and assessment</h3>
            <p className="play-report-prose">Verification: {statusLabel(caseData?.verification_status || 'unknown')}. {caseData?.independence_groups?.length ? `${caseData.independence_groups.length} recorded source lineage(s).` : 'Independent source lineages have not been documented.'} {dossierReasonCodes.length ? `Recorded detector grounds: ${dossierReasonCodes.map((code) => code.toLowerCase().replaceAll('_', ' ')).join('; ')}.` : ''}</p>
            {caseData?.evidence_audit && <>
              <h3>Source provenance and verification gaps</h3>
              <p className="play-report-prose">{caseData.evidence_audit.counts?.direct_observation || 0} direct timeline item(s), {caseData.evidence_audit.counts?.modelled || 0} modelled item(s), {caseData.evidence_audit.counts?.context_only || 0} context-only item(s). Source links: {caseData.evidence_audit.counts?.linked_source || 0}. These counts measure documentation, not confidence.</p>
              <ul className="play-report-chronology">{(caseData.evidence_audit.next_checks || []).map((check, i) => <li key={`${i}-${check}`}>{check}</li>)}</ul>
              {(caseData.evidence_audit.counter_indicators || []).length > 0 && <p className="play-report-prose">Recorded counter-indicators: {caseData.evidence_audit.counter_indicators.join('; ')}</p>}
            </>}
            <h3>Limitations and next checks</h3>
            <p className="play-report-prose">This reconstruction contains only information available at the selected historical cutoff. Missing AIS, satellite, radio or other records must not be interpreted as evidence that an activity did not occur. A modelled drift is not an observed vessel track. Reported circumstances, assessed hypotheses and verified outcomes remain separate.</p>
          </section>
          <section className="play-card play-card--rows">
            <div><span>Status</span><strong>{statusLabel(status)}</strong></div>
            <div><span>Evidence confidence</span><strong>{evidenceLabel(caseData || selectedIncident)}</strong></div>
            <div><span>View</span><strong>{modeLabel}</strong></div>
            <div><span>Archive decision</span><strong>{statusLabel(caseData?.archive_decision || selectedIncident?.archive_decision || '—')}</strong></div>
            <div><span>Evidence known</span><strong>{caseData?.evidence_count ?? visibleTimeline.length}</strong></div>
            {caseData?.verification_status ? <div><span>Verification</span><strong>{statusLabel(caseData.verification_status)}</strong></div> : null}
            {typeof caseData?.corroborated === 'boolean' ? <div><span>Independent sources</span><strong>{caseData.corroborated ? 'Confirmed' : 'Not yet confirmed'}</strong></div> : null}
            {caseData?.independence_groups?.length ? <div><span>Evidence lineages</span><strong>{caseData.independence_groups.join(' · ')}</strong></div> : null}
            {selectedIncident?.evidence_stage || caseData?.evidence_stage ? <div><span>Evidence stage</span><strong>{statusLabel(selectedIncident?.evidence_stage || caseData?.evidence_stage)}</strong></div> : null}
            <div><span>Satellite</span><strong>{caseData?.satellite_count ?? 0}</strong></div>
            <div><span>Radio</span><strong>{caseData?.radio_count ?? 0}</strong></div>
            <div><span>Drift</span><strong>{caseData?.drift_count ?? 0}</strong></div>
            <div><span>SAR assessments</span><strong>{caseData?.sar_mission_count ?? 0}</strong></div>
            {dossierReasonCodes.length > 0 ? <div><span>Why flagged</span><strong>{dossierReasonCodes.join(' · ')}</strong></div> : null}
            {caseData?.counter_indicators?.length ? <div><span>Counter-indicators</span><strong>{caseData.counter_indicators.join(' · ')}</strong></div> : null}
            {frame.item ? <div><span>Latest at cutoff</span><strong>{frame.item.type}</strong></div> : null}
            {frameProps.model ? <div><span>Model</span><strong>{frameProps.model}</strong></div> : null}
            {frameProps.reason_code ? <div><span>Reason</span><strong>{frameProps.reason_code}</strong></div> : null}
          </section>
          {caseData?.search_area ? (
            <section className="play-card play-card--search-area">
              <p>Search area · source-derived</p>
              <h3>Possible area, not an observed position</h3>
              <span>{statusLabel(caseData.search_area.location_evidence || 'spatial prior')}</span>
              {caseData.search_area.departure_places?.length ? <span>Departure · {caseData.search_area.departure_places.join(' · ')}</span> : null}
              {caseData.search_area.destination_places?.length ? <span>Destination · {caseData.search_area.destination_places.join(' · ')}</span> : null}
              {caseData.search_area.mentioned_places?.length ? <span>Places · {caseData.search_area.mentioned_places.join(' · ')}</span> : null}
              {caseData.search_area.departure_time_window?.start_utc ? (
                <span>
                  Departure window · {String(caseData.search_area.departure_time_window.start_utc).slice(0, 10)}
                  {caseData.search_area.departure_time_window.precision === 'date_only' ? ' · date only' : ''}
                </span>
              ) : null}
              <span>Physical drift · {caseData.search_area.physical_drift_computed ? 'computed' : 'not computed'}</span>
              <span>Probability · {caseData.search_area.probability_calibrated ? 'calibrated' : 'not calibrated'}</span>
            </section>
          ) : null}
          <section className="play-card">
            <p>Evidence and source review</p>
            <h3>What supports this case</h3>
            {(caseData?.assessment?.supporting_evidence || selectedIncident?.assessment?.supporting_evidence || []).length
              ? (caseData?.assessment?.supporting_evidence || selectedIncident?.assessment?.supporting_evidence || []).map((item, index) => <span key={index}>• {String(item)}</span>)
              : <span>No supporting evidence summary has been recorded.</span>}
            <h3>Contradictions and limitations</h3>
            {(caseData?.assessment?.contradicting_evidence || selectedIncident?.assessment?.contradicting_evidence || []).length
              ? (caseData?.assessment?.contradicting_evidence || selectedIncident?.assessment?.contradicting_evidence || []).map((item, index) => <span key={index}>• {String(item)}</span>)
              : <span>No contradicting evidence has been recorded. This does not establish that the claim is true.</span>}
            {(caseData?.assessment?.caveats || selectedIncident?.assessment?.caveats || []).map((item, index) => <span key={index}>Caution: {String(item)}</span>)}
            <h3>Independent source groups</h3>
            <span>{caseData?.independence_groups?.length ? caseData.independence_groups.join(' · ') : 'Independent source lineages not documented.'}</span>
          </section>
          <section className="play-card">
            <p>Evidence chronology · {visibleTimeline.length} records</p>
            {visibleTimeline.length ? visibleTimeline.map((item, index) => (
              <div key={item.id || index} className="play-dossier-evidence">
                <time>{itemTime(item.at)}</time>
                <h3>{item.title || statusLabel(item.type || 'Observation')}</h3>
                <span>{item.source || 'Source not recorded'} · {statusLabel(item.type || 'evidence')}</span>
                {(item.properties?.source_url || item.properties?.url) && /^https?:\/\//i.test(item.properties.source_url || item.properties.url) ? <a href={item.properties.source_url || item.properties.url} target="_blank" rel="noreferrer">View original source ↗</a> : null}
              </div>
            )) : <span>No dated evidence available at this historical cutoff.</span>}
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
            <label className="play-satellite-selector">
              <span>Map imagery</span>
              <select aria-label="Map imagery" value={satelliteVisible ? 'dated' : 'high-resolution'} onChange={(event) => setSatelliteVisible(event.target.value === 'dated')}>
                <option value="high-resolution">High-resolution imagery · Esri composite</option>
                <option value="dated">Dated imagery · NASA VIIRS (clouds visible)</option>
              </select>
            </label>
            {satelliteProps.asset_ref ? (
              <figure className="play-satellite-preview">
                <img
                  src={satelliteProps.asset_ref}
                  alt={`Satellite quicklook ${satelliteProps.mission || ''}`.trim()}
                  loading="lazy"
                  referrerPolicy="no-referrer"
                />
                <figcaption>Satellite quicklook · {satelliteProps.mission || satellite?.source || 'acquisition'}</figcaption>
              </figure>
            ) : null}
            <label className="play-satellite-selector">
              <span>Global imagery</span>
              <select value={satelliteContextMission} onChange={(event) => setSatelliteContextMission(event.target.value)}>
                <option value="VIIRS NOAA-21">NOAA-21 · dated true color</option>
                <option value="VIIRS NOAA-20">NOAA-20 · dated true color</option>
                <option value="VIIRS Suomi-NPP">Suomi-NPP · dated true color</option>
              </select>
            </label>
            <span>Context date {contextDay} · NASA EOSDIS GIBS</span>
            <label className="play-satellite-selector">
              <span>Case acquisition</span>
              <select value={satelliteMission} onChange={(event) => setSatelliteMission(event.target.value)}>
                <option value="auto">Auto · Sentinel first</option>
                {satelliteMissions.map((mission) => <option key={mission} value={mission}>{mission}</option>)}
              </select>
            </label>
            <h3>{satelliteProps.mission || 'No acquisition before this time'}</h3>
            {satellite ? <time>{itemTime(satellite.at)}</time> : null}
            <span>{satelliteProps.sensor_type || satellite?.source || '—'}</span>
            {Number.isFinite(Number(satelliteProps.temporal_delta_s)) ? <span>Δt {Math.round(Number(satelliteProps.temporal_delta_s) / 3600)} h from report</span> : null}
            {satelliteProps.product_id ? <span>Product {satelliteProps.product_id}</span> : null}
            {satelliteProps.temporal_relation ? <span>{satelliteProps.temporal_relation}</span> : null}
            {satelliteProps.polarisation?.length ? <span>Polarisation {satelliteProps.polarisation.join(' / ')}</span> : null}
            {satelliteProps.cloud_cover != null && Number.isFinite(Number(satelliteProps.cloud_cover)) ? <span>Cloud {Math.round(Number(satelliteProps.cloud_cover))}%</span> : null}
            {satelliteProps.evidence_status ? <span>Evidence {satelliteProps.evidence_status}</span> : null}
            {satelliteProps.source_url ? <a href={satelliteProps.source_url} target="_blank" rel="noreferrer">Acquisition record ↗</a> : null}
          </section>
        </div>
      </aside>

      {reportOpen && report && <div className="play-report-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setReportOpen(false); }}>
        <section className="play-report-dialog" role="dialog" aria-modal="true" aria-label="Case report">
          <header className="play-report-actions"><strong>SeaCommons / PLAY / Report</strong><div>
            <button type="button" onClick={downloadReport}>Download JSON ↓</button>
            <button type="button" onClick={() => window.print()}>Print / Save PDF ↓</button>
            <button type="button" onClick={() => setReportOpen(false)}>Close ×</button>
          </div></header>
          <article className="play-report-document">
            <small>SEACOMMONS · EVIDENCE REPORT · {report.case_id}</small>
            <h1>{report.title}</h1>
            <p className="play-report-disclaimer">Historical evidence report generated {report.generated_at.slice(0, 16).replace('T', ' ')} UTC. This is not an official incident determination.</p>
            <dl><div><dt>Reported</dt><dd>{report.reported_at || 'Unknown'}</dd></div><div><dt>Source</dt><dd>{report.source || 'Not recorded'}</dd></div><div><dt>Status at selected time</dt><dd>{statusLabel(report.status_at_cutoff)}</dd></div><div><dt>Historical cutoff</dt><dd>{report.cutoff || 'Complete archive'}</dd></div><div><dt>Archive decision</dt><dd>{statusLabel(report.archive_decision || 'unknown')}</dd></div><div><dt>Verification</dt><dd>{statusLabel(report.verification_status || 'not recorded')}</dd></div><div><dt>Independent corroboration</dt><dd>{report.corroborated === null ? 'Not assessed' : report.corroborated ? 'Yes' : 'No'}</dd></div><div><dt>Evidence records</dt><dd>{report.evidence_count_at_cutoff}</dd></div></dl>
            <section aria-label="Report at a glance">
              <h2>What we know</h2>
              <p><strong>Reported event:</strong> {report.assessment?.observation || 'An incident was reported, but the available records do not describe a verified observation.'}</p>
              <p><strong>What the evidence suggests:</strong> {report.assessment?.interpretation || 'There is not enough independently verified evidence to establish what happened.'}</p>
              <p><strong>Verification:</strong> {report.corroborated === true ? 'Independent corroboration is recorded.' : report.corroborated === false ? 'Independent corroboration has not been established.' : 'Independent corroboration has not been assessed.'} {report.evidence_count_at_cutoff} evidence record(s) available at this point in the archive.</p>
              <p><strong>What remains uncertain:</strong> {report.limitations || 'Location, outcome and attribution may remain unverified.'}</p>
            </section>
            <h2>Evidence assessment · detailed record</h2>
            <p>{report.assessment?.observation || 'Reported incident. Original evidence and interpretation are distinct.'}</p>
            <p>{report.assessment?.interpretation || 'Independent confirmation and outcomes may remain unknown.'}</p>
            {(report.assessment?.supporting_evidence || []).map((item, index) => <p key={`support-${index}`}><strong>Supporting:</strong> {String(item)}</p>)}
            {(report.assessment?.contradicting_evidence || []).map((item, index) => <p key={`against-${index}`}><strong>Contradicting:</strong> {String(item)}</p>)}
            {(report.assessment?.caveats || []).map((item, index) => <p key={`caveat-${index}`}><strong>Limitation:</strong> {String(item)}</p>)}
            <p>{report.limitations}</p>
            {report.reason_codes.length > 0 && <p><strong>Reason codes:</strong> {report.reason_codes.join(' · ')}</p>}
            {report.counter_indicators.length > 0 && <p><strong>Counter-indicators:</strong> {report.counter_indicators.join(' · ')}</p>}
            {report.independent_lineages.length > 0 && <p><strong>Evidence lineages:</strong> {report.independent_lineages.join(' · ')}</p>}
            <h2>Timeline · what was documented and when</h2>
            {report.evidence.length === 0 ? <p>No dated evidence is available at this cutoff.</p> : <ol>{report.evidence.map((entry, index) => <li key={`${entry.id || index}-${index}`}><time>{entry.at || 'Undated'}</time><h3>{entry.title || entry.type || 'Observation'}</h3><p>{entry.type || 'evidence'} · {entry.source || 'Source not recorded'}</p>{entry.url && /^https?:\/\//i.test(entry.url) && <a href={entry.url} target="_blank" rel="noreferrer">Original source ↗</a>}</li>)}</ol>}
            <footer>SeaCommons / PLAY · Report ID {report.case_id} · Generated {report.generated_at}</footer>
          </article>
        </section>
      </div>}
      <nav className="play-mobile-dock" aria-label="Play navigation">
        <button className={mobileTab === 'map' && !guideOpen ? 'is-active' : ''} onClick={() => { setMobileTab('map'); setCasesOpen(false); setGuideOpen(false); }} type="button"><span>◎</span>Map</button>
        <button className={casesOpen && !guideOpen ? 'is-active' : ''} onClick={() => { setCasesOpen(true); setMobileTab('archive'); setGuideOpen(false); }} type="button"><span>≡</span>Archive</button>
        <button className={mobileTab === 'timeline' && !guideOpen ? 'is-active' : ''} onClick={() => { setCasesOpen(false); setMobileTab('timeline'); setGuideOpen(false); }} type="button"><span>◷</span>Timeline</button>
        <button className={guideOpen ? 'is-active' : ''} onClick={() => { setCasesOpen(false); setGuideOpen((v) => !v); setMobileTab('guide'); }} type="button"><span>?</span>Guide</button>
      </nav>
      {guideOpen && <aside className="play-mobile-guide" role="dialog" aria-label="Guide to Play">
        <header><strong>Reading PLAY</strong><button type="button" aria-label="Close guide" onClick={() => { setGuideOpen(false); setMobileTab('map'); }}>×</button></header>
        <section><h3>Map symbols</h3><p><b>▲ Ship</b> — A vessel position, when available.</p><p><b>● Point</b> — A location connected to a report.</p><p><b>— Route</b> — Recorded movement; missing parts are not known positions.</p><p><b>◌ Search area</b> — A possible location calculated from available information, not a sighting.</p></section>
        <section><h3>Timeline</h3><p><b>ALL</b> shows every available case. Choose a date to see only events reported on that day (UTC). Moving to another day replaces the previous day's cases.</p></section>
        <section><h3>Understanding reports</h3><p><b>Recorded</b> means a source contains a signal or position. <b>Reported</b> means an event was described. <b>Estimated</b> means a possible location was calculated. Always check the date and source.</p></section>
        <section><h3>Coming soon</h3><p><b>Incidents</b> — Better ways to explore possible attacks, collisions and other events, with supporting sources and independent checks. In development, not automatically verified.</p></section>
      </aside>}
      <footer className={`play-timeline-bar ${mobileTab === 'timeline' ? 'is-mobile-active' : ''}`}>
        <span className="play-timeline-end">{coverage.start ? coverage.start.slice(0, 10) : 'PAST'}</span>
        <button type="button" onClick={() => { const base = selectedDay || globalState.cutoff?.slice(0,10) || coverage.end?.slice(0,10); if (base) { setSelectedDay(new Date(Date.parse(`${base}T00:00:00Z`) - 86400000).toISOString().slice(0,10)); setGlobalPosition(TIMELINE_MAX - 1); } }}>←</button>
        <input
          aria-label="Global archive timeline"
          type="range"
          min="0"
          max={TIMELINE_MAX}
          value={globalPosition}
          onChange={(event) => { setSelectedDay(''); setGlobalPosition(Number(event.target.value)); }}
        />
        <button type="button" onClick={() => { const base = selectedDay || globalState.cutoff?.slice(0,10) || coverage.end?.slice(0,10); if (base) { const next = new Date(Date.parse(`${base}T00:00:00Z`) + 86400000).toISOString().slice(0,10); if (next > (coverage.end?.slice(0,10) || next)) { setSelectedDay(''); setGlobalPosition(TIMELINE_MAX); } else { setSelectedDay(next); setGlobalPosition(TIMELINE_MAX - 1); } } }}>→</button>
        <div className="play-timeline-bar__label"><strong>{modeLabel}</strong><span>{globalState.mode === 'all' ? `through ${coverage.end?.slice(0, 10) || 'latest'}` : `imagery ${contextDay}`}</span></div>
        <input className="play-day-picker" type="date" aria-label="Show events on date" min={coverage.start?.slice(0,10)} max={coverage.end?.slice(0,10)} value={selectedDay || (globalState.mode === 'all' ? '' : globalState.cutoff?.slice(0,10) || '')} onChange={(event) => { const day = event.target.value; if (!day) { setSelectedDay(''); setGlobalPosition(TIMELINE_MAX); return; } setSelectedDay(day); const first = Date.parse(coverage.start); const last = Date.parse(coverage.end); const target = Date.parse(`${day}T12:00:00Z`); if (Number.isFinite(first) && Number.isFinite(last) && last > first && Number.isFinite(target)) setGlobalPosition(Math.max(0, Math.min(TIMELINE_MAX - 1, Math.round((target-first)/(last-first)*TIMELINE_MAX)))); }} />
        <button className="play-all-reset" type="button" disabled={globalState.mode === 'all' && !selectedDay} onClick={() => { setSelectedDay(''); setGlobalPosition(TIMELINE_MAX); }}>ALL</button>
      </footer>
    </main>
  );
}
