import { playIncidentColor } from './incidentPalette.js';
import { publicBasemapSource } from '../map/publicBasemap.js';

import { isVesselArchiveIncident } from '../map/vesselMarker.js';

function parseTime(value) {
  const ms = Date.parse(String(value || ''));
  return Number.isFinite(ms) ? ms : Number.POSITIVE_INFINITY;
}

export function normalizeTimeline(items = []) {
  return [...items]
    .filter((item) => item && Number.isFinite(parseTime(item.at)))
    .sort((a, b) => parseTime(a.at) - parseTime(b.at))
    .map((item, frameIndex) => ({ ...item, frameIndex }));
}

export function selectFrame(timeline = [], index = 0) {
  if (!timeline.length) return { index: -1, item: null, geometry: null };
  const clamped = Math.max(0, Math.min(timeline.length - 1, Number(index) || 0));
  const item = timeline[clamped];
  let geometry = item.geometry || null;
  if (!geometry) {
    for (let i = clamped - 1; i >= 0; i -= 1) {
      if (timeline[i]?.geometry) {
        geometry = timeline[i].geometry;
        break;
      }
    }
  }
  return { index: clamped, item, geometry };
}

export function selectSatelliteObservation(timeline = [], at) {
  const target = parseTime(at);
  const candidates = timeline.filter((item) => item?.type === 'satellite');
  if (!candidates.length) return null;
  const before = candidates
    .filter((item) => parseTime(item.at) <= target)
    .sort((a, b) => parseTime(b.at) - parseTime(a.at));
  if (before.length) return before[0];
  return [...candidates].sort((a, b) => parseTime(a.at) - parseTime(b.at))[0];
}


export function selectPreferredSatelliteObservation(timeline = [], at = null, preferredMission = 'auto') {
  const target = parseTime(at);
  const candidates = timeline
    .filter((item) => item?.type === 'satellite')
    .filter((item) => !Number.isFinite(target) || parseTime(item?.at) <= target);
  if (!candidates.length) return null;

  const newest = (items) => [...items].sort((a, b) => parseTime(b?.at) - parseTime(a?.at))[0] || null;
  if (preferredMission && preferredMission !== 'auto') {
    return newest(candidates.filter((item) => item?.properties?.mission === preferredMission));
  }

  const priorities = [
    (mission) => mission === 'Sentinel-1',
    (mission) => mission === 'Sentinel-2',
    (mission) => mission === 'Sentinel-3',
    (mission) => String(mission || '').startsWith('VIIRS'),
  ];
  for (const matches of priorities) {
    const selected = newest(candidates.filter((item) => matches(item?.properties?.mission)));
    if (selected) return selected;
  }
  return newest(candidates);
}

/** A running case clock measures time since first report, never new AIS fixes. */
export function ongoingCaseClock(incident, nowMs = Date.now()) {
  if (incident?.ongoing !== true) return null;
  const first = Date.parse(String(incident.reported_at || ''));
  if (!Number.isFinite(first) || first > nowMs) return null;
  const elapsedMinutes = Math.floor((nowMs - first) / 60_000);
  const days = Math.floor(elapsedMinutes / (24 * 60));
  const hours = Math.floor((elapsedMinutes % (24 * 60)) / 60);
  const minutes = elapsedMinutes % 60;
  const duration = `${days > 0 ? `${days}d ` : ''}${hours}h ${minutes}m`;
  const latest = Date.parse(String(incident.last_update_at || ''));
  const updateAge = Number.isFinite(latest) && latest <= nowMs
    ? Math.max(0, Math.floor((nowMs - latest) / 60_000))
    : null;
  const freshness = updateAge == null ? 'last update not recorded'
    : updateAge < 60 ? `record updated ${updateAge}m ago`
      : `record updated ${Math.floor(updateAge / 60)}h ago`;
  return `CASE OPEN · ${duration} since first report · ${freshness}`;
}

export function statusLabel(status) {
  const value = String(status || '').toLowerCase();
  if (value === 'needs_review') return 'NEEDS REVIEW';
  if (value === 'outcome_unknown' || value === 'archived') return 'OUTCOME UNKNOWN';
  if (value === 'resolved') return 'RESOLVED';
  if (value === 'active') return 'ACTIVE';
  return value ? value.replaceAll('_', ' ').toUpperCase() : 'UNKNOWN';
}

export function satelliteRasterDescriptor(observation) {
  const props = observation?.properties || {};
  const asset = String(props.asset_ref || '');
  if (!asset || (!asset.startsWith('https://') && !asset.startsWith('http://'))) return null;
  if (asset.includes('{z}') && asset.includes('{x}') && asset.includes('{y}')) {
    return { type: 'raster', tiles: [asset], tileSize: 256 };
  }
  const bbox = Array.isArray(props.bbox) ? props.bbox.map(Number) : null;
  const looksLikeImage = /\.(?:png|jpe?g|webp)(?:\?|$)/i.test(asset);
  const copernicusThumbnail = observation?.source === 'copernicus_dataspace'
    && /\/odata\/v1\/Assets\([^)]*\)\/\$value(?:\?|$)/i.test(asset);
  if ((!looksLikeImage && !copernicusThumbnail) || bbox?.length !== 4 || bbox.some((value) => !Number.isFinite(value))) return null;
  const [west, south, east, north] = bbox;
  return {
    type: 'image',
    url: asset,
    coordinates: [[west, north], [east, north], [east, south], [west, south]],
  };
}

export function casesForArchiveView(incidents, cutoff, selectedDay) {
  const day = selectedDay || cutoff?.slice(0, 10);
  if (!day) return incidents;
  const end = selectedDay ? `${day}T23:59:59.999Z` : cutoff;
  return incidentsAtCutoff(incidents, end).filter((item) => {
    const reported = parseTime(item.reported_at);
    return Number.isFinite(reported) && new Date(reported).toISOString().startsWith(day);
  });
}

export function satelliteReviewScenes(timeline, candidates = [], cutoff) {
  const byId = new Map();
  for (const item of timeline) {
    if (item.type === 'satellite' && item.id
        && (item.properties?.asset_ref || item.properties?.source_url || ['Polygon', 'MultiPolygon'].includes(item.geometry?.type))) {
      byId.set(item.id, item);
    }
  }
  for (const candidate of candidates) {
    const at = candidate?.acquisition_time;
    if (!candidate?.observation_id || !Number.isFinite(parseTime(at)) || parseTime(at) > parseTime(cutoff)) continue;
    if (byId.has(candidate.observation_id)) continue;
    byId.set(candidate.observation_id, {
      id: candidate.observation_id, at, source: candidate.provider, type: 'satellite',
      properties: { mission: candidate.mission, source_url: candidate.source_url,
        asset_ref: candidate.asset_ref, review_delta_hours: candidate.delta_hours, evidence_role: 'context_only_pending_review' },
    });
  }
  return [...byId.values()].sort((a, b) => parseTime(b.at) - parseTime(a.at));
}

export function incidentsAtCutoff(incidents = [], cutoff = null) {
  if (!cutoff) return [...incidents];
  const cutoffMs = parseTime(cutoff);
  return incidents.filter((incident) => parseTime(incident?.reported_at) <= cutoffMs);
}

export function timelineAtCutoff(timeline = [], cutoff = null) {
  if (!cutoff) return [...timeline];
  const cutoffMs = parseTime(cutoff);
  return timeline.filter((item) => parseTime(item?.at) <= cutoffMs);
}

export function resolveGlobalTimelinePosition(incidents = [], position = 1000, max = 1000) {
  const times = incidents.map((incident) => parseTime(incident?.reported_at)).filter(Number.isFinite);
  if (!times.length || Number(position) >= Number(max)) return { mode: 'all', cutoff: null };
  const min = Math.min(...times);
  const latest = Math.max(...times);
  const ratio = Math.max(0, Math.min(1, Number(position) / Number(max || 1)));
  return { mode: 'temporal', cutoff: new Date(min + ((latest - min) * ratio)).toISOString() };
}

export function historicalVesselCourse(incident = {}) {
  const fields = [
    incident.heading_deg, incident.latest_heading, incident.heading,
    incident.course_over_ground, incident.cog, incident.latest_course, incident.course,
    incident.properties?.heading_deg, incident.properties?.cog, incident.properties?.course,
  ];
  for (const raw of fields) {
    if (raw === null || raw === undefined || raw === '') continue;
    const value = Number(raw);
    if (Number.isFinite(value) && value >= 0 && value < 360) return value;
  }
  return null;
}

export function incidentCollection(incidents = [], cutoff = null) {
  return {
    type: 'FeatureCollection',
    features: incidentsAtCutoff(incidents, cutoff)
      .filter((incident) => ['Point', 'Polygon', 'MultiPolygon'].includes(incident?.geometry?.type))
      .map((incident) => {
        const geometryType = incident.geometry.type;
        const isArea = geometryType === 'Polygon' || geometryType === 'MultiPolygon';
        return {
          type: 'Feature',
          geometry: incident.geometry,
          properties: {
            incident_id: incident.incident_id,
            visual_color: playIncidentColor(incident),
            incident_status: incidentStatusAtCutoff(incident, cutoff),
            case_type: incident.case_type || 'incident',
            source: incident.source || '',
            domain: incident.main_category || incident.domain || 'humanitarian',
            incident_type: incident.incident_type || '',
            attack_type: incident.attack_type || '',
            event_type: incident.event_type || '',
            maritime_domain: incident.maritime_domain || '',
            has_course: !isArea && historicalVesselCourse(incident) !== null,
            reported_at: incident.reported_at || '',
            title: incident.title || '',
            marker_kind: isArea ? 'search_area' : (isVesselArchiveIncident(incident) ? 'vessel' : 'incident'),
            geometry_semantics: isArea ? 'search_prior' : 'reported_position',
            location_evidence: incident.search_area?.location_evidence || '',
            probability_calibrated: incident.search_area?.probability_calibrated === true,
            physical_drift_computed: incident.search_area?.physical_drift_computed === true,
            // Historical bearings must come from an actual observation, never a default northward arrow.
            course: isArea ? null : historicalVesselCourse(incident),
          },
        };
      }),
  };
}


export function incidentStatusAtCutoff(incident, cutoff = null) {
  const current = incident?.incident_status || 'outcome_unknown';
  if (!cutoff) return current;
  const cutoffMs = parseTime(cutoff);
  const history = [...(incident?.status_history || [])]
    .filter((item) => Number.isFinite(parseTime(item?.at)))
    .sort((a, b) => parseTime(a.at) - parseTime(b.at));
  let effective = null;
  for (const transition of history) {
    const at = parseTime(transition.at);
    if (at <= cutoffMs) effective = transition.to_state || effective;
    else if (effective == null && transition.from_state) return transition.from_state;
    else break;
  }
  if (effective) return effective;
  if (current === 'resolved') {
    const resolved = parseTime(incident.resolved_at);
    return Number.isFinite(resolved) && resolved <= cutoffMs ? 'resolved' : 'outcome_unknown';
  }
  return parseTime(incident?.state_changed_at) > cutoffMs && incident?.state_changed_at
    ? 'outcome_unknown' : current;
}



export function satelliteContextTileUrl(day, mission = 'VIIRS NOAA-21') {
  const layers = {
    'VIIRS NOAA-21': 'VIIRS_NOAA21_CorrectedReflectance_TrueColor',
    'VIIRS NOAA-20': 'VIIRS_NOAA20_CorrectedReflectance_TrueColor',
    'VIIRS Suomi-NPP': 'VIIRS_SNPP_CorrectedReflectance_TrueColor',
  };
  const layer = layers[mission] || layers['VIIRS NOAA-21'];
  return `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/${layer}/default/${day}/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg`;
}

export function archiveCoverage(incidents = []) {
  const times = incidents
    .map((incident) => Date.parse(String(incident?.reported_at || '')))
    .filter(Number.isFinite)
    .sort((a, b) => a - b);
  if (!times.length) return { start: null, end: null, coveredMonths: [], missingMonths: [] };
  const coveredMonths = [...new Set(times.map((time) => new Date(time).toISOString().slice(0, 7)))].sort();
  const present = new Set(coveredMonths);
  const missingMonths = [];
  const startDate = new Date(times[0]);
  const endDate = new Date(times[times.length - 1]);
  let year = startDate.getUTCFullYear();
  let month = startDate.getUTCMonth();
  const endYear = endDate.getUTCFullYear();
  const endMonth = endDate.getUTCMonth();
  while (year < endYear || (year === endYear && month <= endMonth)) {
    const key = `${year}-${String(month + 1).padStart(2, '0')}`;
    if (!present.has(key)) missingMonths.push(key);
    month += 1;
    if (month > 11) { month = 0; year += 1; }
  }
  return {
    start: new Date(times[0]).toISOString(),
    end: new Date(times[times.length - 1]).toISOString(),
    coveredMonths,
    missingMonths,
  };
}

export function groupArchiveByMonth(incidents = []) {
  const groups = new Map();
  const sorted = [...incidents].sort((a, b) => parseTime(b?.reported_at) - parseTime(a?.reported_at));
  for (const incident of sorted) {
    const time = parseTime(incident?.reported_at);
    if (!Number.isFinite(time)) continue;
    const date = new Date(time);
    const key = date.toISOString().slice(0, 7);
    if (!groups.has(key)) {
      groups.set(key, {
        key,
        label: new Intl.DateTimeFormat('en-GB', { month: 'long', year: 'numeric', timeZone: 'UTC' }).format(date),
        incidents: [],
      });
    }
    groups.get(key).incidents.push(incident);
  }
  return [...groups.values()];
}

export function playMapStyle(day = new Date(Date.now() - 24 * 3600 * 1000).toISOString().slice(0, 10), mission = 'VIIRS NOAA-21') {
  return {
    version: 8,
    sources: {
      baseMap: {
        type: 'raster',
        tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
        tileSize: 256,
        maxzoom: 19,
        attribution: 'Esri, Maxar, Earthstar Geographics, and the GIS User Community',
      },
      satelliteContext: {
        type: 'raster',
        tiles: [satelliteContextTileUrl(day, mission)],
        tileSize: 256,
        attribution: 'NASA EOSDIS GIBS / VIIRS',
      },
    },
    layers: [
      { id: 'base-map', type: 'raster', source: 'baseMap', paint: { 'raster-opacity': 1 } },
      { id: 'satellite-context', type: 'raster', source: 'satelliteContext', layout: { visibility: 'none' }, paint: { 'raster-opacity': 1, 'raster-fade-duration': 120 } },
    ],
  };
}


export function mergeIncidentPages(previous = [], incoming = []) {
  const byId = new Map((previous || []).map((item) => [item.incident_id, item]));
  for (const item of incoming || []) {
    if (item?.incident_id) byId.set(item.incident_id, item);
  }
  return [...byId.values()].sort((a, b) => {
    const sortTime = (record) => {
      const reported = parseTime(record?.reported_at);
      const updated = parseTime(record?.last_update_at);
      return Number.isFinite(updated) && updated >= reported ? updated : reported;
    };
    const aAt = sortTime(a);
    const bAt = sortTime(b);
    return (Number.isFinite(bAt) ? bAt : 0) - (Number.isFinite(aAt) ? aAt : 0);
  });
}


export function satelliteFootprintCollection(timeline = []) {
  return {
    type: 'FeatureCollection',
    features: timeline
      .filter((item) => item?.type === 'satellite' && item?.source === 'copernicus_dataspace' && item?.geometry)
      .map((item) => ({
        type: 'Feature',
        geometry: item.geometry,
        properties: {
          observation_id: item.id,
          mission: item.properties?.mission || 'Copernicus',
          sensor_type: item.properties?.sensor_type || 'satellite',
          temporal_relation: item.properties?.temporal_relation || 'nearest',
        },
      })),
  };
}
