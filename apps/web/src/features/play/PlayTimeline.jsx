import { CaseReportOverview, ReportPanelHeader, ReportRow } from '../../components/ReportPanel.jsx';
import { startTransition } from 'react';
import { reviewedArchiveCase, archiveGeographicClues, geographicClueFeatures } from './humanitarianReview.js';
import { isPublicCaseEligible } from '../live/publicCaseEligibility.js';
import { addMovementLabels } from '../map/movementLabels.js';
import VesselCaseSearch from '../../components/VesselCaseSearch.jsx';
import MapBasemapSwitch from '../../components/MapBasemapSwitch.jsx';
import MapReferenceBar from '../../components/MapReferenceBar.jsx';
import IntelligencePanelTabs from '../../components/IntelligencePanelTabs.jsx';
import { liveMovementEndpoints, liveMovementMapFeatures } from '../live/movementEndpoints.js';
import { playIncidentColor } from './incidentPalette.js';
import React, { useEffect, useMemo, useRef, useState } from 'react';

import { fetchJson } from '../../services/api/client.js';
import { timelineReport, humanizeDetectorText } from '../live/reportNarrative.js';
import SanctionsCatalog from '../../components/SanctionsCatalog.jsx';
import { historicalDriftFeatures } from './driftGeometry.js';
import { reconstructAisGaps, aisGapMapFeatures, normalizeAisFixes } from './aisGapGeometry.js';
import { configureMaplibreWorker } from '../map/maplibreWorker.js';
import { createVesselArrowImage, VESSEL_COLOR } from '../map/vesselMarker.js';
import { createAttackMarkerImage, isAttackIncident } from '../map/attackMarker.js';
import { SATELLITE_BASEMAP_TILE_URL } from '../map/publicBasemap.js';
import { createFallbackMap, PLAY_CLUSTER_BANDS } from '../map/fallbackRenderer.js';
import {
  incidentCollection,
  mergeIncidentPages,
  playMapStyle,
  incidentStatusAtCutoff,
  incidentsAtCutoff,
  normalizeTimeline,
  resolveGlobalTimelinePosition,
  casesForArchiveView,
  satelliteReviewScenes,
  sarObservationPoint,
  satelliteFootprintCollection,
  selectFrame,
  statusLabel,
  ongoingCaseClock,
  timelineAtCutoff,
  archiveCoverage,
  groupArchiveByMonth,
  satelliteContextTileUrl,
} from './timeline.js';

function clusterPaint(property) {
  const [first, ...remaining] = PLAY_CLUSTER_BANDS;
  return ['step', ['get', 'point_count'], first[property],
    ...remaining.flatMap((band) => [band.minimum, band[property]])];
}

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
  const [apiIncidents, setIncidents] = useState([]);
  const [reviewedIncidents, setReviewedIncidents] = useState([]);
  const archiveRecords = useMemo(() => mergeIncidentPages(apiIncidents, reviewedIncidents), [apiIncidents, reviewedIncidents]);
  const incidents = useMemo(() => archiveRecords.filter(isPublicCaseEligible).map(reviewedArchiveCase).filter(Boolean), [archiveRecords]);
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
  const [apiArchiveTotal, setArchiveTotal] = useState(null);
  const archiveTotal = apiArchiveTotal == null ? null : apiArchiveTotal + reviewedIncidents.length - (archiveRecords.length - incidents.length);
  const [selectedId, setSelectedId] = useState('');
  const [focusRequest, setFocusRequest] = useState(0);
  const [overlapIds, setOverlapIds] = useState([]);
  const [caseResponse, setCaseResponse] = useState(null);

  const [reportOpen, setReportOpen] = useState(false);
  const [globalPosition, setGlobalPosition] = useState(TIMELINE_MAX);
  const [casesOpen, setCasesOpen] = useState(false);
  const [archiveCollapsed, setArchiveCollapsed] = useState(false);
  const [mobileTab, setMobileTab] = useState('map');
  const [selectedDay, setSelectedDay] = useState('');
  const [guideOpen, setGuideOpen] = useState(false);
  const [playToolTab, setPlayToolTab] = useState('archive');
  const [archiveLoading, setArchiveLoading] = useState(true);
  const [timelineRequest, setTimelineRequest] = useState(null);
  const timelineLoading = timelineRequest?.id === selectedId && timelineRequest?.pending;
  const timelineError = timelineRequest?.id === selectedId ? timelineRequest.error : '';
  const [startupDismissed, setStartupDismissed] = useState(false);
  const [startupGraceExpired, setStartupGraceExpired] = useState(false);
  useEffect(() => {
    const timeout = window.setTimeout(() => setStartupGraceExpired(true), 25_000);
    return () => window.clearTimeout(timeout);
  }, []);
  useEffect(() => {
    if (startupGraceExpired || (!archiveLoading && (mapContentReady || mapError))) {
      setStartupDismissed(true);
    }
  }, [archiveLoading, mapContentReady, mapError, startupGraceExpired]);
  const [error, setError] = useState('');
  const [satelliteMission, setSatelliteMission] = useState('');
  const [archiveFiltersExpanded, setArchiveFiltersExpanded] = useState(false);
  const [archiveFilter, setArchiveFilter] = useState('all');
  const [archiveSearch, setArchiveSearch] = useState('');
  const [visibleCaseLimit, setVisibleCaseLimit] = useState(80);
  const [incidentTypeFilter, setIncidentTypeFilter] = useState('all');
  const [evidenceFilter, setEvidenceFilter] = useState('all');
  const [satelliteOnly, setSatelliteOnly] = useState(false);
  const [sanctionsOnly, setSanctionsOnly] = useState(false);
  const [sanctionsOpen, setSanctionsOpen] = useState(false);
  const [investigationsOnly, setInvestigationsOnly] = useState(false);
  const [imageryMode, setImageryMode] = useState('composite');
  const [imageryDate, setImageryDate] = useState('');
  const satelliteVisible = imageryMode !== 'composite';
  const [satelliteContextMission, setSatelliteContextMission] = useState('VIIRS NOAA-21');

  const globalState = useMemo(
    () => selectedDay
      ? { mode: 'temporal', cutoff: `${selectedDay}T23:59:59.999Z` }
      : resolveGlobalTimelinePosition(historicalIncidents, globalPosition, TIMELINE_MAX),
    [historicalIncidents, globalPosition, selectedDay],
  );
  const caseData = useMemo(() => {
    if (caseResponse?.id !== selectedId) return null;
    let data = caseResponse?.payload;
    if (!data) return data;
    if (incidents.find((item) => item.incident_id === selectedId)?.suppress_inferred_map_evidence) {
      const { search_area, satellite_review_candidates, ...reportedCase } = data;
      data = { ...reportedCase, timeline: (data.timeline || []).filter((item) => item.type !== 'satellite' && item.type !== 'drift')
        .map((item) => ({ ...item, geometry: null })), satellite_count: 0, drift_count: 0 };
    }
    if (!globalState.cutoff) return data;
    // The API returns the current dossier, including undated assessments and counts.
    return {
      timeline: data.timeline,
      voyage_evidence: data.voyage_evidence,
      satellite_review_candidates: data.satellite_review_candidates,
    };
  }, [incidents, caseResponse, selectedId, globalState.cutoff]);
  const visibleIncidents = useMemo(
    () => casesForArchiveView(historicalIncidents, globalState.cutoff, selectedDay),
    [historicalIncidents, globalState.cutoff, selectedDay],
  );
  const archiveCounts = useMemo(() => visibleIncidents.reduce((counts, incident) => {
    const domain = incident.main_category || incident.domain;
    if (domain === 'humanitarian' || domain === 'maritime') counts[domain] += 1;
    return counts;
  }, { humanitarian: 0, maritime: 0 }), [visibleIncidents]);
  const categoryIncidents = useMemo(() => visibleIncidents.filter((incident) => {
    const mainCategory = incident.main_category || incident.domain;
    if (archiveFilter === 'humanitarian') return mainCategory === 'humanitarian';
    if (archiveFilter === 'maritime') return mainCategory === 'maritime';
    if (archiveFilter === 'attacks') return isAttackIncident(incident);
    if (archiveFilter === 'ais-gaps') return incident.incident_type === 'ais_gap' || incident.episode_family === 'gap_episode';
    return true;
  }), [visibleIncidents, archiveFilter]);
  const incidentTypes = useMemo(
    () => [...new Set(categoryIncidents.map((incident) => incident.incident_type).filter(Boolean))].sort(),
    [categoryIncidents],
  );
  const filteredIncidents = useMemo(() => categoryIncidents.filter((incident) => {
    const query = archiveSearch.trim().toLowerCase().replaceAll('_', ' ');
    if (query && ![incident.title, incident.source, incident.incident_type, incident.incident_id]
      .some((field) => String(field || '').toLowerCase().replaceAll('_', ' ').includes(query))) return false;
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
    archiveSearch,
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
  useEffect(() => { setVisibleCaseLimit(80); }, [archiveFilter, archiveSearch, incidentTypeFilter, evidenceFilter, satelliteOnly, sanctionsOnly, investigationsOnly, globalState.mode, globalState.cutoff, selectedDay]);
  const selectedIncident = useMemo(
    () => {
      const incident = visibleIncidents.find((item) => item.incident_id === selectedId);
      if (!incident || !globalState.cutoff) return incident || null;
      const { assessment, reason_codes, corroborated, verification_status, evidence_state, evidence_stage, archive_decision, ...datedIncident } = incident;
      return datedIncident;
    },
    [visibleIncidents, selectedId, globalState.cutoff],
  );
  const reviewedCase = useMemo(
    () => reviewedIncidents.find(({ incident_id }) => incident_id === selectedId),
    [reviewedIncidents, selectedId],
  );
  const overlapIncidents = useMemo(
    () => overlapIds.map((id) => filteredIncidents.find((item) => item.incident_id === id)).filter(Boolean),
    [overlapIds, filteredIncidents],
  );
  // Derived voyage evidence must exist before the map effect depends on it.
  const voyageVessels = useMemo(() => (caseData?.voyage_evidence?.vessels || []).map((v) => ({
    ...v, track_points: normalizeAisFixes(v.track_points).filter((p) =>
      !globalState.cutoff || Date.parse(p.at) <= Date.parse(globalState.cutoff)),
  })), [caseData?.voyage_evidence, globalState.cutoff]);
  const aisReconstruction = useMemo(() => reconstructAisGaps(voyageVessels), [voyageVessels]);
  const caseContextDay = useMemo(() => {
    const value = selectedDay || globalState.cutoff || selectedIncident?.reported_at || coverage.end;
    return value ? String(value).slice(0, 10) : new Date(Date.now() - 24 * 3600 * 1000).toISOString().slice(0, 10);
  }, [selectedDay, globalState.cutoff, selectedIncident?.reported_at, coverage.end]);
  const todayUtc = new Date().toISOString().slice(0, 10);
  const contextDay = imageryMode === 'recent'
    ? (imageryDate || todayUtc)
    : caseContextDay;
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
  const geographicClues = archiveGeographicClues(selectedIncident);
  const gapFeatures = useMemo(() => {
    const reconstructed = aisGapMapFeatures(aisReconstruction.gaps);
    if (geographicClues.length) return { ...reconstructed, features: geographicClueFeatures(geographicClues) };
    if (reconstructed.features.length || !selectedIncident) return reconstructed;
    const feature = { geometry: selectedIncident.geometry, properties: selectedIncident };
    const endpoints = liveMovementEndpoints(feature);
    if (globalState.cutoff) {
      const cutoff = Date.parse(globalState.cutoff);
      if (endpoints.from?.at && Date.parse(endpoints.from.at) > cutoff) endpoints.from = null;
      if (endpoints.to?.at && Date.parse(endpoints.to.at) > cutoff) endpoints.to = null;
    }
    const features = liveMovementMapFeatures(feature, endpoints);
    if (features.length) return { ...reconstructed, features };
    const forecast = historicalDriftFeatures(visibleTimeline).features
      .filter((feature) => feature.properties.geometry_semantics === 'simulated_trajectory').at(-1);
    if (!forecast) return reconstructed;
    const track = forecast.geometry.coordinates;
    return { ...reconstructed, features: [
      { type: 'Feature', geometry: { type: 'Point', coordinates: track[0] },
        properties: { kind: 'model_start', label: 'Model start' } },
      { type: 'Feature', geometry: { type: 'Point', coordinates: track.at(-1) },
        properties: { kind: 'model_end', label: 'Model endpoint' } },
    ] };
  }, [aisReconstruction, geographicClues, globalState.cutoff, selectedIncident, visibleTimeline]);
  const frame = useMemo(
    () => selectFrame(visibleTimeline, Math.max(0, visibleTimeline.length - 1)),
    [visibleTimeline],
  );
  const satelliteScenes = useMemo(
    () => satelliteReviewScenes(visibleTimeline, caseData?.satellite_review_candidates, globalState.cutoff),
    [visibleTimeline, caseData?.satellite_review_candidates, globalState.cutoff],
  );
  const satellite = satelliteScenes.find((item) => String(item.id) === satelliteMission) || null;
  const sarPoint = sarObservationPoint(satellite);
  const sarFeature = useMemo(() => sarPoint ? {
    type: 'Feature',
    geometry: { type: 'Point', coordinates: sarPoint },
    properties: { kind: 'sar_observation', label: 'SAR reporting cell' },
  } : null, [sarPoint]);

  useEffect(() => {
    let cancelled = false;
    fetchJson('', '/archive/reviewed-cases.json')
      .then((payload) => {
        if (!cancelled && Array.isArray(payload?.incidents)) setReviewedIncidents(payload.incidents);
      })
      .catch(() => { /* The API archive remains available. */ });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    let running = false;
    let complete = false;
    async function loadIncidents({ full = true } = {}) {
      if (running) return;
      running = true;
      try {
        let offset = 0;
        let remaining = [];
        while (!cancelled) {
          const limit = offset === 0 ? 100 : 500;
          const payload = await fetchJson(apiBase, `/api/v1/play/incidents?limit=${limit}&offset=${offset}`, undefined, 30_000);
          if (cancelled) return;
          const page = Array.isArray(payload?.incidents) ? payload.incidents : [];
          if (offset === 0) {
            setIncidents((previous) => mergeIncidentPages(previous, page));
            setArchiveLoading(false);
          } else {
            remaining.push(...page);
          }
          if (payload?.next_offset == null || !full) break;
          const nextOffset = Number(payload.next_offset);
          if (!Number.isSafeInteger(nextOffset) || nextOffset <= offset) {
            throw new Error('Play archive pagination returned an invalid next_offset');
          }
          offset = nextOffset;
        }
        if (!cancelled) {
          if (remaining.length) startTransition(() => setIncidents((previous) => mergeIncidentPages(previous, remaining)));
          if (full) complete = true;
          setError('');
        }
      } catch (exc) {
        if (!cancelled) setError(exc?.message || 'Play archive unavailable');
      } finally {
        running = false;
        if (!cancelled) setArchiveLoading(false);
      }
    }
    loadIncidents();
    const timer = window.setInterval(() => {
      if (document.visibilityState !== 'hidden') loadIncidents({ full: !complete });
    }, 60_000);
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
    setSatelliteMission('');
  }, [selectedId]);

  useEffect(() => {
    if (incidentTypeFilter !== 'all' && !incidentTypes.includes(incidentTypeFilter)) {
      setIncidentTypeFilter('all');
    }
  }, [incidentTypeFilter, incidentTypes]);

  useEffect(() => {
    if (satelliteMission && !satelliteScenes.some((item) => String(item.id) === satelliteMission)) {
      setSatelliteMission('');
    }
  }, [satelliteMission, satelliteScenes]);

  useEffect(() => {
    if (selectedId && !visibleIncidents.some((item) => item.incident_id === selectedId)) {
      setSelectedId('');
      setCaseResponse(null);
    }
  }, [selectedId, visibleIncidents]);

  useEffect(() => {
    let cancelled = false;
    if (!selectedId) {
      setCaseResponse(null);
      return () => { cancelled = true; };
    }
    if (reviewedCase) {
      setCaseResponse({ id: selectedId, payload: {
        timeline: reviewedCase.timeline,
        archive_decision: 'reviewed_public_sources',
        assessment: {
          caveats: ['The sources describe the area of the incident. An exact position and an AIS link are unavailable in this record. Attribution has not been established for this case.'],
        },
      } });
      setTimelineRequest(null);
      return () => { cancelled = true; };
    }
    let timer;
    let loaded = false;
    setTimelineRequest({ id: selectedId, pending: true });
    const refresh = async () => {
      try {
        const payload = await fetchJson(apiBase, `/api/v1/play/incidents/${encodeURIComponent(selectedId)}/timeline`, { cache: 'no-store' });
        if (cancelled) return;
        setCaseResponse({ id: selectedId, payload });
        setTimelineRequest({ id: selectedId, pending: false });
        loaded = true;
      } catch (exc) {
        if (!cancelled && !loaded) setTimelineRequest({ id: selectedId, pending: false, error: exc?.message || 'Timeline unavailable' });
      } finally {
        if (!cancelled) timer = window.setTimeout(refresh, 60_000);
      }
    };
    refresh();
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [apiBase, selectedId, reviewedCase]);

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
        map.addLayer({
          id: 'play-density', type: 'heatmap', source: 'play-incidents', maxzoom: 9,
          filter: ['==', ['geometry-type'], 'Point'],
          paint: {
            'heatmap-weight': ['interpolate', ['linear'], ['coalesce', ['get', 'point_count'], 1],
              1, 0.2, 10, 0.5, 50, 0.85, 200, 1],
            'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 3, 21, 7, 38],
            'heatmap-opacity': ['interpolate', ['linear'], ['zoom'], 6, 0.82, 9, 0],
            'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'],
              0, 'rgba(33,106,179,0)', 0.15, 'rgba(53,144,205,0.24)',
              0.4, '#33c2cc', 0.66, '#76d8a0', 0.85, '#f0da72', 1, '#ff9c65'],
          },
        });
        // A cluster represents a viewport grouping, never a deduplicated archive record.
        map.addLayer({
          id: 'play-clusters', type: 'circle', source: 'play-incidents',
          filter: ['has', 'point_count'],
          paint: {
            'circle-radius': clusterPaint('radius'),
            'circle-color': clusterPaint('color'), 'circle-opacity': 0.13, 'circle-blur': 0.85,
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
          filter: ['all', ['!', ['has', 'point_count']], ['!=', ['get', 'marker_kind'], 'vessel']],
          paint: {
            'circle-radius': ['case', ['==', ['get', 'incident_id'], selectedId], 8, 5],
            'circle-color': ['coalesce', ['get', 'visual_color'], '#c6a6ff'],
            'circle-opacity': ['interpolate', ['linear'], ['zoom'], 4, 0.24, 8, 0.85],
            'circle-blur': ['interpolate', ['linear'], ['zoom'], 4, 0.65, 8, 0.1],
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
            'icon-allow-overlap': false,
          },
          paint: { 'icon-color': ['coalesce', ['get', 'visual_color'], '#c6a6ff'], 'icon-opacity': 0.94 },
        });
        map.addLayer({
          id: 'play-vessels-unknown-course', type: 'circle', source: 'play-incidents',
          filter: ['all', ['==', ['get', 'marker_kind'], 'vessel'], ['!=', ['get', 'has_course'], true]],
          paint: { 'circle-radius': 3.5, 'circle-color': ['coalesce', ['get', 'visual_color'], VESSEL_COLOR],
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
            'ais_last_observed', '#ff8859', 'ais_first_reappearance', '#55e0c0', 'clue_departure', '#53d1f5', 'clue_destination', '#b2d7e2', '#bb8cff'],
            'circle-stroke-color': '#071014', 'circle-stroke-width': 2 } });
        // Tap/click either observed endpoint to inspect the same bounded gap.
        addMovementLabels(map, 'play-ais-gap-labels', 'play-ais-gaps');
        map.on('click', 'play-ais-gap-endpoints', (event) => {
          const feature = event.features?.[0];
          if (!feature || feature.geometry?.type !== 'Point' || !feature.properties?.from_utc) return;
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
        map.addSource('play-sar-observation', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        map.addLayer({
          id: 'play-sar-observation', type: 'circle', source: 'play-sar-observation',
          paint: { 'circle-color': '#75a7ff', 'circle-radius': 9, 'circle-stroke-color': '#e4f0ff', 'circle-stroke-width': 2 },
        });
        const selectArchiveFeature = (event) => {
          const rendered = map.queryRenderedFeatures(event.point, { layers: ['play-incidents', 'play-vessels', 'play-vessels-unknown-course'] });
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
        cluster: true,
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
    const points = mappedIncidents.features.filter((feature) => feature.geometry.type === 'Point');
    const selectedArea = mappedIncidents.features.find((feature) => feature.properties.incident_id === selectedId && feature.properties.marker_kind === 'search_area');
    fallback.setFeatures(selectedArea ? [...points, selectedArea] : points);
    if (!selectedId && points.length) fallback.fitFeatures(points);
  }, [fallbackReady, mappedIncidents, selectedId]);

  useEffect(() => {
    if (!fallbackReady || !selectedIncident?.geometry) return;
    fallbackMapRef.current?.focusReport(selectedIncident, [], window.matchMedia('(max-width: 680px)').matches);
  }, [fallbackReady, selectedId, selectedIncident?.geometry]);

  useEffect(() => {
    const map = mapRef.current;
    if (!mapReady || !map) return;
    map.getSource('play-incidents')?.setData(mappedIncidents);
    map.getSource('play-attacks')?.setData({ type: 'FeatureCollection', features: mappedIncidents.features.filter((f) => f.geometry?.type === 'Point' && isAttackIncident(f.properties)) });
    if (map.getLayer('play-attack-markers')) map.moveLayer('play-attack-markers');
  }, [mapReady, mappedIncidents]);

  useEffect(() => {
    const map = mapRef.current;
    if (!mapReady || !map) return;
    const datedEvidence = evidenceCollection(visibleTimeline);
    datedEvidence.features.push(...aisReconstruction.observed.features);
    map.getSource('play-evidence')?.setData(datedEvidence);
    map.getSource('play-ais-gaps')?.setData(gapFeatures);
    map.getSource('play-historical-drifts')?.setData(historicalDriftFeatures(visibleTimeline));
  }, [mapReady, visibleTimeline, aisReconstruction, gapFeatures]);

  useEffect(() => {
    if (!mapReady) return;
    mapRef.current?.getSource('play-satellite-footprints')?.setData(satelliteFootprintCollection(satellite ? [satellite] : []));
  }, [mapReady, satellite]);

  useEffect(() => {
    if (!mapReady) return;
    mapRef.current?.getSource('play-sar-observation')?.setData({
      type: 'FeatureCollection', features: sarFeature ? [sarFeature] : [],
    });
  }, [mapReady, sarFeature]);

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
    // Always render evidence markers above footprints, routes and satellite rasters.
    for (const layerId of ['play-incidents', 'play-vessels']) {
      if (map.getLayer(layerId)) map.moveLayer(layerId);
    }
  }, [mapReady, selectedId]);

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
    if (map.getLayer('base-map')) map.setLayoutProperty('base-map', 'visibility', satelliteVisible ? 'none' : 'visible');
    if (map.getLayer('bathymetry-labels')) map.setLayoutProperty('bathymetry-labels', 'visibility', satelliteVisible ? 'none' : 'visible');
    if (map.getLayer('satellite-context')) map.setLayoutProperty('satellite-context', 'visibility', satelliteVisible ? 'visible' : 'none');
  }, [mapReady, satelliteVisible, contextDay, satelliteContextMission]);

  useEffect(() => {
    if (!fallbackReady) return;
    const imageryUrl = satelliteVisible
      ? satelliteContextTileUrl(contextDay, satelliteContextMission)
      : SATELLITE_BASEMAP_TILE_URL;
    fallbackMapRef.current?.setBasemap(satelliteVisible ? 'satellite' : 'standard', imageryUrl);
  }, [fallbackReady, satelliteVisible, contextDay, satelliteContextMission]);

  useEffect(() => {
    if (!fallbackReady) return;
    fallbackMapRef.current?.setMovement(sarFeature ? [...gapFeatures.features, sarFeature] : gapFeatures.features);
    fallbackMapRef.current?.setDrifts(historicalDriftFeatures(visibleTimeline));
  }, [fallbackReady, gapFeatures, sarFeature, visibleTimeline]);

  const gapHasOnlyAnchor = selectedIncident
    && (selectedIncident.incident_type === 'ais_gap' || selectedIncident.episode_family === 'gap_episode')
    && !gapFeatures.features.some(({ geometry }) => geometry.type === 'LineString');
  const movementBounds = geometryBounds({
    coordinates: gapFeatures.features.filter(({ geometry }) => geometry.type === 'Point').map(({ geometry }) => geometry.coordinates),
  });
  const movementExtent = movementBounds && gapFeatures.features.filter(({ geometry }) => geometry.type === 'Point').length >= 2
    ? [movementBounds.west, movementBounds.south, movementBounds.east, movementBounds.north].join(',') : '';
  useEffect(() => {
    if (!selectedId || !movementExtent) return;
    const mobile = window.matchMedia('(max-width: 680px)').matches;
    const [west, south, east, north] = movementExtent.split(',').map(Number);
    if (fallbackReady) {
      fallbackMapRef.current?.focusMovement([
        { geometry: { type: 'Point', coordinates: [west, south] } },
        { geometry: { type: 'Point', coordinates: [east, north] } },
      ], mobile);
    }
    if (mapReady) {
      mapRef.current?.fitBounds([[west, south], [east, north]], {
        padding: mobile ? { top: 60, bottom: Math.round(window.innerHeight * .60), left: 24, right: 24 }
          : { top: 80, bottom: 85, left: 410, right: 340 },
        maxZoom: 9, duration: 450,
      });
    }
  }, [fallbackReady, focusRequest, mapReady, movementExtent, selectedId]);

  const status = selectedIncident ? incidentStatusAtCutoff(selectedIncident, globalState.cutoff) : 'outcome_unknown';
  const reportTrack = useMemo(() => timelineReport(visibleTimeline), [visibleTimeline]);
  const reportEvidence = visibleTimeline.filter((item) => item?.type !== 'satellite');
  const frameProps = frame.item?.properties || {};
  const satelliteProps = satellite?.properties || {};
  const locateSarPoint = () => {
    const map = mapRef.current;
    map?.easeTo({ center: sarPoint, zoom: Math.max(9, map.getZoom()), duration: 500 });
    fallbackMapRef.current?.flyTo({ center: sarPoint, zoom: 9 });
  };
  const sceneBounds = satellite?.source === 'copernicus_dataspace'
    && ['Polygon', 'MultiPolygon'].includes(satellite.geometry?.type)
    ? geometryBounds(satellite.geometry) : null;
  const locateScene = () => {
    const { west, south, east, north } = sceneBounds;
    mapRef.current?.fitBounds([[west, south], [east, north]], {
      padding: 75, maxZoom: 11, duration: 500,
    });
    fallbackMapRef.current?.fitFeatures([satellite]);
  };
  const sceneResolution = Number(satelliteProps.resolution_m);
  const caseBounds = geometryBounds(selectedIncident?.geometry);
  const recentOpticalUrl = caseBounds && `https://browser.dataspace.copernicus.eu/?${new URLSearchParams({
    zoom: '11', lat: ((caseBounds.south + caseBounds.north) / 2).toFixed(4),
    lng: ((caseBounds.west + caseBounds.east) / 2).toFixed(4),
    datasetId: 'S2_L2A_CDAS', layerId: '1_TRUE_COLOR', date: 'latest',
  })}`;
  const quicklook = /^https:\/\//i.test(satelliteProps.asset_ref || '')
    && /(?:\.(?:png|jpe?g|webp)|Assets\([^)]*\)\/\$value)(?:\?|$)/i.test(satelliteProps.asset_ref);
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

  const startupPending = !startupDismissed && !startupGraceExpired && (archiveLoading || (!mapContentReady && !mapError));

  return (
    <main className={`cop-shell is-live-mode play-public-shell play-shell ${selectedId ? 'has-selection' : ''} ${archiveCollapsed ? 'is-archive-collapsed' : ''}`}>
      {startupPending ? (
        <div className="play-startup-overlay" role="status" aria-live="polite" aria-label="Loading SeaCommons PLAY">
          <div className="play-startup-overlay__inner">
            <span className="play-startup-overlay__eyebrow">SEACOMMONS / TEMPORAL INTELLIGENCE</span>
            <strong>Preparing PLAY</strong>
            <span className="play-startup-overlay__spinner" aria-hidden="true" />
            <p>{archiveLoading ? 'Loading historical evidence…' : 'Initializing the interactive map…'}</p>
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

      {archiveCollapsed && <button className="live-feed-toggle play-desktop-cases-toggle" type="button" onClick={() => setArchiveCollapsed(false)}>Open archive</button>}
      <button className="live-feed-toggle play-mobile-cases-toggle" type="button" onClick={() => setCasesOpen((value) => !value)}>
        Archive · {globalState.mode === 'all' && !selectedDay && archiveTotal != null ? archiveTotal : visibleIncidents.length}
      </button>

      {gapHasOnlyAnchor && <div className="play-gap-map-note" role="status">
        {gapFeatures.features.length ? 'Reported gap position · two recorded fixes unavailable' : 'This report has no published gap coordinates'}
      </div>}
      <aside className={`live-feed-panel is-open play-archive-panel play-cases ${archiveCollapsed ? 'is-desktop-collapsed' : ''} ${casesOpen ? 'is-mobile-open' : ''}`}>
        <header className="live-feed-panel__header">
          <div className="live-feed-panel__eyebrow">
            <span className="live-feed-panel__mark">SC</span>
            <span>SEACOMMONS / MEDITERRANEAN</span>
            <b><i /> ARCHIVE</b>
          </div>
          <div className="live-feed-panel__title">
            <div><p>HISTORICAL SIGNAL FIELD</p><h1>Play</h1></div>
            <button type="button" onClick={() => { setCasesOpen(false); setArchiveCollapsed(true); setMobileTab('map'); }} aria-label="Close archive">−</button>
          </div>
          <IntelligencePanelTabs label="Historical intelligence sections" value={playToolTab} onChange={setPlayToolTab}
            options={[{ id: 'archive', label: 'Archive', count: visibleIncidents.length }, { id: 'timeline', label: 'Timeline' }, { id: 'sources', label: 'Sources' }, { id: 'layers', label: 'Layers' }]} />
          {playToolTab === 'archive' && <>
          <div className="live-feed-panel__search">
          <VesselCaseSearch cases={visibleIncidents} onSelect={(record) => {
        setArchiveSearch(''); setArchiveFilter('all'); setIncidentTypeFilter('all');
        setEvidenceFilter('all'); setSatelliteOnly(false); setSanctionsOnly(false); setInvestigationsOnly(false);
        setSelectedId(record.incident_id); setCasesOpen(false);
      }} />
          </div>
          <div className="osint-stats-row">
            <div className="osint-stat"><strong>{visibleIncidents.length}</strong><span>archive loaded</span></div>
            <div className="osint-stat osint-stat--critical"><strong>{archiveCounts.humanitarian}</strong><span>humanitarian</span></div>
            <div className="osint-stat"><strong>{archiveCounts.maritime}</strong><span>maritime</span></div>
          </div>
          <input type="search" className="play-archive-search" aria-label="Search archive" placeholder="Search cases or sources…" value={archiveSearch} onChange={(event) => setArchiveSearch(event.target.value)} />
          <div className="signals-selector play-filter-selector" role="group" aria-label="Play archive filters">
            <div className="signals-selector__row">
              <span className="signals-selector__label">Investigations</span>
              <button type="button" className={`signals-selector__link ${archiveFilter === 'all' ? 'is-active' : ''}`}
                onClick={() => setArchiveFilter('all')}>All <span className="signals-selector__count">{visibleIncidents.length}</span></button>
              <button type="button" className={`signals-selector__chevron ${archiveFiltersExpanded ? 'is-open' : ''}`}
                aria-expanded={archiveFiltersExpanded} aria-label="Archive investigation categories"
                onClick={() => setArchiveFiltersExpanded((expanded) => !expanded)}><i /></button>
            </div>
            <div className="signals-selector__macros" hidden={!archiveFiltersExpanded}>
            <div className="signals-selector__list">
              <button type="button" className={`signals-selector__link ${archiveFilter === 'all' ? 'is-active' : ''}`} onClick={() => setArchiveFilter('all')}><span className="signals-selector__box" aria-hidden="true" />ALL</button>
              <button type="button" className={`signals-selector__link ${archiveFilter === 'humanitarian' ? 'is-active' : ''}`} onClick={() => setArchiveFilter('humanitarian')}><span className="signals-selector__box" aria-hidden="true" />HUMANITARIAN</button>
              <button type="button" className={`signals-selector__link ${archiveFilter === 'maritime' ? 'is-active' : ''}`} onClick={() => setArchiveFilter('maritime')}><span className="signals-selector__box" aria-hidden="true" />MARITIME</button>
              <button type="button" className={`signals-selector__link ${archiveFilter === 'attacks' ? 'is-active' : ''}`} onClick={() => { setArchiveFilter('attacks'); setIncidentTypeFilter('all'); }}><span className="signals-selector__box" aria-hidden="true" />ATTACKS</button>
              <button type="button" className={`signals-selector__link ${archiveFilter === 'ais-gaps' ? 'is-active' : ''}`}
                aria-pressed={archiveFilter === 'ais-gaps'} onClick={() => { setArchiveFilter('ais-gaps'); setIncidentTypeFilter('all'); }}>
                <span className="signals-selector__box" aria-hidden="true" />AIS GAPS
              </button>
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
          </div>
          <div className="play-archive-continuity">
            <p className="live-feed-panel__continuity"><span />Evidence is bounded to what was knowable at the selected cutoff.</p>
            {coverage.start && coverage.end ? (
              <p>{coverage.start.slice(0, 10)} → {coverage.end.slice(0, 10)} · {coverage.coveredMonths.length} months with public cases · {coverage.missingMonths.length} continuity gaps</p>
            ) : null}
          </div>
          </>}
        </header>
        {playToolTab === 'archive' && <>
        <details className="play-sanctions-section" onToggle={(event) => setSanctionsOpen(event.currentTarget.open)}>
          <summary>Sanctioned vessels · historical registry</summary>
          {sanctionsOpen && <SanctionsCatalog apiBase={apiBase} />}
        </details>
        <div className="live-feed-panel__body play-cases__list">
          {archiveGroups.map((group) => (
            <section className="play-archive-month" key={group.key}>
              <header><strong>{group.label}</strong><span>{group.incidents.length} cases</span></header>
              <ul className="play-archive-log">
                {group.incidents.map((incident) => {
                  const selected = selectedId === incident.incident_id;
                  const color = playIncidentColor(incident);
                  const counts = globalState.cutoff ? {} : incident.evidence_counts || {};
                  return (
                    <li key={incident.incident_id} className={`intel-log-row${selected ? ' is-selected' : ''}`}>
                      <button type="button" className={`play-case${selected ? ' is-active' : ''}`}
                        aria-current={selected ? 'true' : undefined}
                        onClick={() => { setSelectedId(incident.incident_id); setCasesOpen(false); }}>
                        <i className="intel-log-dot" aria-hidden="true" style={{ background: color, color }} />
                        <strong>{incident.title || 'SeaCommons incident'}</strong>
                        <span>{(incident.incident_type || 'context').replace(/_/g, ' ')} · {statusLabel(incidentStatusAtCutoff(incident, globalState.cutoff))}</span>
                        <span className="intel-log-time">{itemTime(incident.reported_at)}</span>
                        <code className="intel-log-loc">{globalState.cutoff ? 'Historical snapshot' : evidenceLabel(incident)}
                          {Number(counts.drift) > 0 ? ` · DRIFT ${counts.drift}` : ''}
                          {Number(counts.satellite) > 0 ? ` · SAT ${counts.satellite}` : ''}
                          {ongoingCaseClock(incident, archiveNow) ? ` · ${ongoingCaseClock(incident, archiveNow)}` : ''}
                        </code>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
          {filteredIncidents.length > displayedCases.length ? <button type="button" className="play-case-load-more" onClick={() => setVisibleCaseLimit((limit) => limit + 80)}>Show 80 more cases · {displayedCases.length} of {filteredIncidents.length} loaded</button> : null}
          {!filteredIncidents.length && !archiveLoading ? <div className="play-empty">{archiveFilter === 'attacks' ? 'No explicitly classified attacks in the public archive for this selection. An AIS gap or an unverified report is not evidence of an attack.' : 'No incidents at this time.'}</div> : null}
        </div>
        </>}
        {playToolTab === 'timeline' && <section className="sc-panel-tab-content" aria-label="Archive timeline controls">
          <h2>Historical timeline</h2>
          <p>Use the timeline below the map to choose a historical cutoff. Reports only include evidence knowable at that point.</p>
          <div className="sc-panel-status-row"><span>Archive mode</span><strong>{globalState.mode === 'all' && !selectedDay ? 'All records' : 'Historical cutoff'}</strong></div>
          <div className="sc-panel-status-row"><span>Visible cases</span><strong>{visibleIncidents.length}</strong></div>
          <button type="button" onClick={() => { setSelectedDay(''); setGlobalPosition(TIMELINE_MAX); }}>Show full archive</button>
          <small>Missing observations do not establish a vessel's location. Predicted movement is always distinguished from recorded positions.</small>
        </section>}
        {playToolTab === 'sources' && <section className="sc-panel-tab-content" aria-label="Archive sources">
          <h2>Sources and verification</h2>
          <p>The archive combines recorded observations and published reports. Being listed here is not independent confirmation.</p>
          <div className="sc-panel-status-row"><span>Loaded cases</span><strong>{incidents.length}</strong></div>
          <div className="sc-panel-status-row"><span>Months with records</span><strong>{coverage.coveredMonths.length}</strong></div>
          <div className="sc-panel-status-row"><span>Continuity gaps</span><strong>{coverage.missingMonths.length}</strong></div>
          <p>Open a case from Archive to inspect its cited sources, evidence classification and limitations in the right-hand dossier.</p>
        </section>}
        {playToolTab === 'layers' && <section className="sc-panel-tab-content" aria-label="Archive map layers">
          <h2>Map and evidence layers</h2>
          <p>Bathymetry is the default. Use Map / Satellite in the bottom-left corner to change the background.</p>
          <label className="sc-panel-layer-option"><input type="checkbox" checked={satelliteOnly} onChange={() => setSatelliteOnly((v) => !v)} /><span>Cases with satellite evidence</span></label>
          <label className="sc-panel-layer-option"><input type="checkbox" checked={sanctionsOnly} onChange={() => setSanctionsOnly((v) => !v)} /><span>Sanctions-related cases</span></label>
          <label className="sc-panel-layer-option"><input type="checkbox" checked={investigationsOnly} onChange={() => setInvestigationsOnly((v) => !v)} /><span>Investigations only</span></label>
          <small>Visibility filters do not alter the underlying archive.</small>
        </section>}
        <MapReferenceBar context="play" />
      </aside>

      <section className="map-stage play-map-stage">
        <div className="map-frame play-map" ref={mapNodeRef} />
        <MapBasemapSwitch mode={satelliteVisible ? 'satellite' : 'standard'} panelOpen={!archiveCollapsed}
          onChange={(mode) => setImageryMode(mode === 'satellite' ? 'recent' : 'composite')} />
        <div className="play-all-badge"><strong>{modeLabel}</strong><span>{mappedIncidentCount} mapped / {filteredIncidents.length} filtered · {incidents.length} loaded{archiveTotal != null ? ` / ${archiveTotal} archive` : ''}</span></div>
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
                <strong><i className="play-case__category" aria-hidden="true" style={{ backgroundColor: playIncidentColor(incident) }} />{incident.title || 'SeaCommons incident'}</strong>
                <span>{itemTime(incident.reported_at)} &middot; {incident.source || 'source unavailable'}</span>
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {selectedId && <aside className="cone-panel cone-panel--intel play-evidence is-open">
        <div className="play-sheet-handle" />
        <ReportPanelHeader kicker="Historical report" title="Case dossier" onClose={() => setSelectedId('')}>

        </ReportPanelHeader>
        <div className="play-evidence__scroll" aria-busy={Boolean(timelineLoading)}>
          {timelineLoading && <p className="play-dossier-progress" role="status">Loading case evidence…</p>}
          {timelineError && <p className="play-dossier-progress" role="alert">{timelineError}</p>}
          <section className="cone-section sc-play-human-summary" aria-label="Case overview in plain language">
            <p className="sc-play-human-summary__eyebrow">AT A GLANCE</p>
            <h2>{selectedIncident?.title || 'Historical maritime case'}</h2>
            <div className="sc-play-human-summary__grid">
              <div><h3>What was reported?</h3><p>{humanizeDetectorText(caseData?.assessment?.observation || selectedIncident?.assessment?.observation || selectedIncident?.location_summary || 'This case appears in the historical archive. The original report and its date are documented in the sections below.')}</p></div>
              <div><h3>What can be checked?</h3><p>{caseData?.corroborated === true ? 'The archive records independent corroboration. Check the cited evidence and when it was recorded.' : 'Independent confirmation has not been established in this archive. Check the original sources before drawing a conclusion.'}</p></div>
              <div><h3>What remains unknown?</h3><p>{humanizeDetectorText(caseData?.assessment?.limitations || selectedIncident?.assessment?.limitations || 'A missing AIS record is not proof a vessel switched off its transmitter. Predicted locations are not observations; the record may be incomplete.')}</p></div>
            </div>
            <small>Historical view: observations are limited to the selected time. An archived report is not an official determination.</small>
          </section>
          <section className="cone-section play-case-summary">
            <CaseReportOverview
              title={selectedIncident?.title || 'SeaCommons incident'}
              summary={humanizeDetectorText(caseData?.assessment?.observation || selectedIncident?.assessment?.observation)}
              category={statusLabel(selectedIncident?.main_category || selectedIncident?.domain || 'maritime')}
              color={playIncidentColor(selectedIncident || {})}
              event={statusLabel(selectedIncident?.incident_type || caseData?.incident_type || 'incident')}
              status={statusLabel(status)} evidence={globalState.cutoff ? undefined : { ...selectedIncident, ...caseData }}
            >
              <ReportRow label="Case" value={caseData?.incident_id || selectedId} mono />
              {selectedIncident?.source && <ReportRow label="Original source" value={selectedIncident.source} />}
              <ReportRow label="Reported (UTC)" value={itemTime(selectedIncident?.reported_at)} />
              {!globalState.cutoff && selectedIncident?.last_update_at && (
                <ReportRow label="Last updated (UTC)" value={itemTime(selectedIncident.last_update_at)} />
              )}
              {globalState.cutoff && <ReportRow label="Evidence cutoff (UTC)" value={itemTime(globalState.cutoff)} />}
            </CaseReportOverview>
            {reviewedCase?.event_date && <span>Incident date · {reviewedCase.event_date}</span>}
            {selectedIncident?.location_summary && <span>{selectedIncident.suppress_inferred_map_evidence ? '' : 'Reported area · '}{selectedIncident.location_summary}</span>}
            {geographicClues.length > 0 && <div className="play-report-locations">
              <strong>Geographic clues from the report</strong>
              {geographicClues.map((clue) => <span key={clue.role}>
                {clue.role === 'departure' ? 'Reported departure' : 'Reported destination'} · {clue.name}
                {' · '}<a href={clue.reference} target="_blank" rel="noreferrer">Place reference ↗</a>
              </span>)}
              <small>Markers identify the named places. The exact departure point, the boat’s route and whether it arrived are unknown.</small>
            </div>}
            <button type="button" disabled={!selectedIncident?.geometry && !geographicClues.length} onClick={() => { if (geographicClues.length) { setFocusRequest((request) => request + 1); return; } const geometry = selectedIncident?.geometry; if (geometry?.type !== 'Point') return; mapRef.current?.easeTo({ center: geometry.coordinates, zoom: Math.max(9, mapRef.current.getZoom()), duration: 600 }); fallbackMapRef.current?.flyTo({ center: geometry.coordinates, zoom: 9 }); }}>Locate on map +</button>
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
            {reportEvidence.length ? <ol className="play-report-chronology">{reportEvidence.map((item, index) => <li key={item.id || `${item.at}-${index}`}><time>{item.properties?.time_precision === 'date_only' ? item.at.slice(0, 10) : itemTime(item.at) + ' UTC'}</time><strong>{String(item.type || 'Observation').replaceAll('_', ' ')}</strong><span>{humanizeDetectorText(item.title || item.properties?.description || 'Recorded evidence')}</span>{(item.properties?.source_url || item.properties?.url) && <a href={item.properties.source_url || item.properties.url} target="_blank" rel="noreferrer">Original source ↗</a>}</li>)}</ol> : <p className="play-report-prose">No detailed sequence of observations is available yet.</p>}
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
            {status === 'resolved' && !selectedIncident?.resolved_at && <span>Resolution date unavailable in the archive.</span>}
            {ongoingCaseClock(selectedIncident, archiveNow) ? <div><span>Latest case clock</span><strong title="Time since first report is not evidence of continued activity or an updated AIS position">{ongoingCaseClock(selectedIncident, archiveNow)}</strong></div> : null}
            <div><span>Evidence confidence</span><strong>{evidenceLabel(caseData || selectedIncident)}</strong></div>
            <div><span>View</span><strong>{modeLabel}</strong></div>
            <div><span>Archive decision</span><strong>{statusLabel(caseData?.archive_decision || selectedIncident?.archive_decision || '—')}</strong></div>
            <div><span>Evidence known</span><strong>{visibleTimeline.length}</strong></div>
            {selectedIncident?.evidence_stage || caseData?.evidence_stage ? <div><span>Evidence stage</span><strong>{statusLabel(selectedIncident?.evidence_stage || caseData?.evidence_stage)}</strong></div> : null}
            <div><span>Satellite</span><strong>{caseData?.satellite_count ?? visibleTimeline.filter((item) => item.type === 'satellite').length}</strong></div>
            <div><span>Radio</span><strong>{caseData?.radio_count ?? visibleTimeline.filter((item) => item.type === 'radio_observation' || item.type === 'radio').length}</strong></div>
            <div><span>Drift</span><strong>{caseData?.drift_count ?? visibleTimeline.filter((item) => item.type === 'drift').length}</strong></div>
            <div><span>SAR assessments</span><strong>{caseData?.sar_mission_count ?? visibleTimeline.filter((item) => item.type === 'sar_mission_assessment').length}</strong></div>
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
            <h3>Satellite review</h3>
            <p>Inspect dated scenes and their source records. Coverage alone cannot establish what happened.</p>
            <label className="play-satellite-selector">
              <span>Map background</span>
              <select aria-label="Map imagery" value={imageryMode} onChange={(event) => setImageryMode(event.target.value)}>
                <option value="composite">Esri imagery · detailed composite</option>
                <option value="dated">NASA VIIRS · case date</option>
                <option value="recent">NASA VIIRS · recent context</option>
              </select>
            </label>
            {imageryMode === 'recent' && <label className="play-satellite-selector">
              <span>Imagery date (UTC)</span>
              <input type="date" value={contextDay} max={todayUtc}
                onChange={(event) => setImageryDate(event.target.value)} />
              <small>Today is requested first. Select an earlier date if tiles are unavailable. This background is independent of the case timeline.</small>
            </label>}
            {satelliteVisible && <label className="play-satellite-selector">
              <span>NASA context · {contextDay} UTC · regional detail</span>
              <select value={satelliteContextMission} onChange={(event) => setSatelliteContextMission(event.target.value)}>
                <option value="VIIRS NOAA-21">NOAA-21 · true color</option>
                <option value="VIIRS NOAA-20">NOAA-20 · true color</option>
                <option value="VIIRS Suomi-NPP">Suomi-NPP · true color</option>
              </select>
            </label>}
            {recentOpticalUrl && <a href={recentOpticalUrl} target="_blank" rel="noreferrer">Latest Sentinel-2 optical imagery near the case ↗</a>}
            <label className="play-satellite-selector">
              <span>Case acquisitions and radar observations</span>
              <select value={satelliteMission} onChange={(event) => setSatelliteMission(event.target.value)} disabled={!satelliteScenes.length}>
                <option value="">{satelliteScenes.length ? 'Choose an acquisition or radar observation' : 'No satellite record at this cutoff'}</option>
                {satelliteScenes.map((item) => <option key={item.id} value={item.id}>{sarObservationPoint(item) ? 'GFW Sentinel-1 SAR return' : item.properties?.mission || item.source || 'Satellite'} · {itemTime(item.at)} UTC{item.properties?.evidence_role === 'context_only_pending_review' ? ' · review candidate' : ''}</option>)}
              </select>
            </label>
            {sarPoint ? (
              <>
                <span>Radar return in a GFW reporting cell · {sarPoint[1].toFixed(4)}, {sarPoint[0].toFixed(4)}</span>
                <span>{satelliteProps.association_status === 'strong' && satelliteProps.evidence_role === 'corroboration'
                  ? 'Provider AIS identity matches the archived episode'
                  : satelliteProps.association_status === 'conflict'
                    ? 'Provider matched this return to a different vessel'
                    : 'Vessel identity unconfirmed for this case'}</span>
                <button type="button" onClick={locateSarPoint}>Locate radar return on map</button>
              </>
            ) : satellite && <span>Acquisition coverage or imagery for manual review</span>}
            {sceneBounds && <button type="button" onClick={locateScene}>Locate scene coverage on map</button>}
            {satellite && sceneResolution > 0 && Number.isFinite(sceneResolution)
              && <span>Product pixel spacing · {sceneResolution} m</span>}
            {quicklook && <figure className="play-satellite-preview">
              <img key={satelliteProps.asset_ref} src={satelliteProps.asset_ref} alt="Satellite quicklook from provider" loading="lazy" referrerPolicy="no-referrer" />
              <figcaption>Provider quicklook · imagery is shown in its original framing</figcaption>
            </figure>}
            {/^https:\/\//i.test(satelliteProps.asset_ref || '') && !satelliteProps.asset_ref.includes('{') && <a href={satelliteProps.asset_ref} target="_blank" rel="noreferrer">Open provider quicklook ↗</a>}
            {satelliteProps.temporal_delta_s != null && Number.isFinite(Number(satelliteProps.temporal_delta_s)) ? <span>Δt {Math.round(Number(satelliteProps.temporal_delta_s) / 3600)} h from report</span> : null}
            {Number.isFinite(satelliteProps.review_delta_hours) && <span>{satelliteProps.review_delta_hours.toFixed(1)} h from the episode window · coverage candidate</span>}
            {satelliteProps.product_id ? <span>Product {satelliteProps.product_id}</span> : null}
            {satelliteProps.temporal_relation ? <span>{satelliteProps.temporal_relation}</span> : null}
            {satelliteProps.polarisation?.length ? <span>Polarisation {satelliteProps.polarisation.join(' / ')}</span> : null}
            {satelliteProps.cloud_cover != null && Number.isFinite(Number(satelliteProps.cloud_cover)) ? <span>Cloud {Math.round(Number(satelliteProps.cloud_cover))}%</span> : null}
            {satelliteProps.evidence_status ? <span>Evidence {satelliteProps.evidence_status}</span> : null}
            {satelliteProps.source_url ? <a href={satelliteProps.source_url} target="_blank" rel="noreferrer">Acquisition record ↗</a> : null}
          </section>
        </div>
      </aside>}

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
              <p><strong>Reported event:</strong> {humanizeDetectorText(report.assessment?.observation) || report.title}</p>
              <p><strong>What the evidence suggests:</strong> {humanizeDetectorText(report.assessment?.interpretation) || 'The sources below show what was available at the selected time.'}</p>
              <p><strong>Verification:</strong> {report.corroborated === true ? 'Independent corroboration is recorded.' : report.corroborated === false ? 'Independent corroboration has not been established.' : 'Independent corroboration has not been assessed.'} {report.evidence_count_at_cutoff} evidence record(s) available at this point in the archive.</p>
              <p><strong>What remains uncertain:</strong> {report.limitations || 'Location, outcome and attribution may remain unverified.'}</p>
            </section>
            <details><summary>Detailed assessment and detector notes</summary>
            <p>{report.assessment?.observation || 'Reported incident. Original evidence and interpretation are distinct.'}</p>
            <p>{report.assessment?.interpretation || 'Independent confirmation and outcomes may remain unknown.'}</p>
            {(report.assessment?.supporting_evidence || []).map((item, index) => <p key={`support-${index}`}><strong>Supporting:</strong> {String(item)}</p>)}
            {(report.assessment?.contradicting_evidence || []).map((item, index) => <p key={`against-${index}`}><strong>Contradicting:</strong> {String(item)}</p>)}
            {(report.assessment?.caveats || []).map((item, index) => <p key={`caveat-${index}`}><strong>Limitation:</strong> {String(item)}</p>)}
            <p>{report.limitations}</p>
            {report.reason_codes.length > 0 && <p><strong>Reason codes:</strong> {report.reason_codes.join(' · ')}</p>}
            {report.counter_indicators.length > 0 && <p><strong>Counter-indicators:</strong> {report.counter_indicators.join(' · ')}</p>}
            {report.independent_lineages.length > 0 && <p><strong>Evidence lineages:</strong> {report.independent_lineages.join(' · ')}</p>}
            </details>
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
        <input className="play-day-picker" title="Choose an archive date in UTC" type="date" aria-label="Show events on date" min={coverage.start?.slice(0,10)} max={coverage.end?.slice(0,10)} value={selectedDay || (globalState.mode === 'all' ? '' : globalState.cutoff?.slice(0,10) || '')} onChange={(event) => { const day = event.target.value; if (!day) { setSelectedDay(''); setGlobalPosition(TIMELINE_MAX); return; } setSelectedDay(day); const first = Date.parse(coverage.start); const last = Date.parse(coverage.end); const target = Date.parse(`${day}T12:00:00Z`); if (Number.isFinite(first) && Number.isFinite(last) && last > first && Number.isFinite(target)) setGlobalPosition(Math.max(0, Math.min(TIMELINE_MAX - 1, Math.round((target-first)/(last-first)*TIMELINE_MAX)))); }} />
        <button className="play-all-reset" type="button" disabled={globalState.mode === 'all' && !selectedDay} onClick={() => { setSelectedDay(''); setGlobalPosition(TIMELINE_MAX); }}>ALL</button>
      </footer>
    </main>
  );
}
