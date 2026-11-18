import {
  PUBLIC_BASEMAP_LABEL_URL,
  PUBLIC_BASEMAP_TILE_URL,
  PUBLIC_SEAMARK_TILE_URL,
  SATELLITE_BASEMAP_TILE_URL,
} from './publicBasemap.js';
import { classifyEventVisual } from '../intel/categories.js';
import { isAttackIncident } from './attackMarker.js';

export const PLAY_CLUSTER_BANDS = [
  { minimum: 2, label: '2–9', color: '#38bdf8', radius: 14 },
  { minimum: 10, label: '10–24', color: '#2dd4bf', radius: 17 },
  { minimum: 25, label: '25–74', color: '#d4ff3f', radius: 20 },
  { minimum: 75, label: '75–199', color: '#facc15', radius: 24 },
  { minimum: 200, label: '200+', color: '#f472b6', radius: 29 },
];

function pointFeatures(features = []) {
  return (features || []).filter((feature) => {
    const coordinates = feature?.geometry?.type === 'Point' ? feature.geometry.coordinates : null;
    return Array.isArray(coordinates)
      && Number.isFinite(Number(coordinates[0]))
      && Number.isFinite(Number(coordinates[1]));
  });
}

function polygonFeatures(features = []) {
  return (features || []).filter((feature) => (
    ['Polygon', 'MultiPolygon'].includes(feature?.geometry?.type)
    && Array.isArray(feature.geometry.coordinates)
  ));
}

function leafletPolygonCoordinates(geometry) {
  const polygons = geometry.type === 'MultiPolygon' ? geometry.coordinates : [geometry.coordinates];
  return polygons.map((polygon) => polygon.map((ring) => ring.map(([lon, lat]) => [Number(lat), Number(lon)])));
}

function markerClass(feature) {
  const raw = String(feature?.properties?.incident_id || feature?.properties?.id || 'feature');
  const safe = raw.toLowerCase().replace(/[^a-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '');
  return `seacommons-fallback-marker seacommons-fallback-marker--${safe || 'feature'}`;
}

function semanticColor(feature) {
  const p = feature?.properties || {};
  return /^#[0-9a-f]{6}$/i.test(p.visual_color || '')
    ? p.visual_color
    : classifyEventVisual(p).color;
}

function isVesselAssociatedSignal(feature) {
  const p = feature?.properties || {};
  const domain = String(p.domain || p.macro_domain || p.maritime_domain || '').toLowerCase();
  if (p.marker_kind) return p.marker_kind === 'vessel';
  const kind = String(p.type || p.event_type || p.category || p.signal_category || '').toLowerCase();
  const text = String(p.title || p.event || '').toLowerCase();
  if (domain === 'humanitarian' || String(p.source || '').toLowerCase().includes('alarm_phone')) return false;
  return /ais|vessel|ship|navigation|collision|grounding|dark_candidate|reporting_gap/.test(`${kind} ${text}`);
}

function markerStyle(feature) {
  const color = semanticColor(feature);
  return {
    radius: 7,
    weight: 2,
    color: '#06151d',
    fillColor: color,
    fillOpacity: 0.96,
    className: markerClass(feature),
  };
}

function vesselHeading(feature) {
  const p = feature?.properties || {};
  const raw = p.latest_heading ?? p.heading_deg ?? p.heading ?? p.latest_course ?? p.course ?? p.cog;
  if (raw === null || raw === undefined || raw === '') return null;
  const value = Number(raw);
  return Number.isFinite(value) && value >= 0 && value < 360 ? value : null;
}

function vesselIsStationary(feature) {
  const p = feature?.properties || {};
  if (p.motion_state) return p.motion_state !== 'moving';
  const raw = p.latest_sog ?? p.speed ?? p.sog;
  const speed = Number(raw);
  return !Number.isFinite(speed) || speed <= 0.5;
}

function vesselColor(feature) {
  const p = feature?.properties || {};
  const role = `${p.role || ''} ${p.operator_type || ''} ${p.fleet || ''} ${p.group || ''}`.toLowerCase();
  return /ngo|sar|rescue|civil/.test(role) ? '#34d399' : '#60a5fa';
}

function bindSelection(marker, feature, onFeatureSelect) {
  const element = marker.getElement?.();
  const id = String(feature?.properties?.receiver_id || feature?.properties?.incident_id || feature?.properties?.id || feature?.properties?.mmsi || 'feature');
  if (!element) {
    marker.on?.('click', () => onFeatureSelect?.(feature));
    return;
  }
  element.setAttribute('role', 'button');
  element.setAttribute('tabindex', '0');
  const isVessel = feature?.properties?.entity_kind === 'vessel' || feature?.properties?.report_type === 'vessel';
  element.setAttribute('aria-label', `${feature?.properties?.radio_type === 'radio_receiver' ? 'Open active radio station' : isVessel ? 'Open vessel' : 'Open incident'} ${id}`);
  let lastSelectionAt = 0;
  const select = (event) => {
    event?.stopPropagation?.();
    const now = Date.now();
    if (now - lastSelectionAt < 250) return;
    lastSelectionAt = now;
    onFeatureSelect?.(feature);
  };
  element.addEventListener('pointerup', select);
  element.addEventListener('click', select);
  element.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault?.();
      select(event);
    }
  });
}

function normalizePayload(payload) {
  if (Array.isArray(payload)) return { incidents: payload, vessels: [] };
  return { incidents: payload?.incidents || [], vessels: payload?.vessels || [] };
}

export async function createFallbackMap({ container, center, zoom, onFeatureSelect, onBackgroundClick, cluster = false, leaflet }) {
  if (!leaflet) await import('leaflet/dist/leaflet.css');
  const module = leaflet || await import('leaflet');
  const L = module.default || module;
  const map = L.map(container, { zoomControl: false, attributionControl: false, preferCanvas: true });
  map.setView([Number(center[1]), Number(center[0])], zoom);
  map.on?.('click', (event) => { if (!event.originalEvent?.target?.closest?.('.leaflet-interactive, .leaflet-marker-icon')) onBackgroundClick?.(); });
  // Incident geometry must remain a real DOM target for keyboard/pointer
  // interaction and accessibility even when the map prefers Canvas globally.
  const incidentRenderer = typeof L.svg === 'function' ? L.svg({ padding: 0.5 }) : undefined;
  const retinaTiles = { detectRetina: true, maxZoom: 19, maxNativeZoom: 16, crossOrigin: true };
  const standardTiles = L.tileLayer(PUBLIC_BASEMAP_TILE_URL, { ...retinaTiles, maxNativeZoom: 19 }).addTo(map);
  let satelliteTiles;
  let satelliteLabelTiles;
  let satelliteLabelsVisible = false;
  let satelliteUrl;
  let activeTiles = standardTiles;
  if (PUBLIC_BASEMAP_LABEL_URL) {
    L.tileLayer(PUBLIC_BASEMAP_LABEL_URL, { ...retinaTiles, opacity: 0.9 }).addTo(map);
  }
  L.tileLayer(PUBLIC_SEAMARK_TILE_URL, { detectRetina: true, maxZoom: 19, maxNativeZoom: 18, opacity: 0.95, crossOrigin: true }).addTo(map);
  const driftsLayer = L.layerGroup().addTo(map);
  const markers = L.layerGroup().addTo(map);
  const movementLayer = L.layerGroup().addTo(map);

  let currentPayload;
  map.on?.('zoomend', () => {
    if (cluster && currentPayload) renderer.setFeatures(currentPayload);
  });

  const renderer = {
    setBasemap(mode, imageryUrl = SATELLITE_BASEMAP_TILE_URL) {
      if (mode === 'satellite' && !satelliteTiles) {
        satelliteTiles = L.tileLayer(imageryUrl, {
          ...retinaTiles, maxNativeZoom: 19, zIndex: 1, attribution: 'Esri or NASA EOSDIS GIBS',
        });
        satelliteUrl = imageryUrl;
        satelliteLabelTiles = L.tileLayer('https://basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}.png', {
          ...retinaTiles, maxNativeZoom: 19, opacity: .92, zIndex: 3,
          attribution: '© CARTO, © OpenStreetMap contributors',
        });
      }
      const nextTiles = mode === 'satellite' ? satelliteTiles : standardTiles;
      if (mode === 'satellite' && imageryUrl !== satelliteUrl) {
        satelliteTiles.setUrl(imageryUrl, activeTiles !== satelliteTiles);
        satelliteUrl = imageryUrl;
      }
      if (activeTiles !== nextTiles) {
        map.removeLayer(activeTiles);
        activeTiles = nextTiles.addTo(map);
      }
      if (satelliteLabelTiles) {
        if (mode === 'satellite' && !satelliteLabelsVisible) {
          satelliteLabelTiles.addTo(map);
          satelliteLabelsVisible = true;
        }
        if (mode !== 'satellite' && satelliteLabelsVisible) {
          map.removeLayer(satelliteLabelTiles);
          satelliteLabelsVisible = false;
        }
      }
    },
    setMovement(features) {
      movementLayer.clearLayers();
      for (const feature of features) {
        const { type, coordinates } = feature.geometry;
        if (type === 'LineString') {
          L.polyline(coordinates.map(([lon, lat]) => [lat, lon]), {
            color: '#f59e0b', weight: 3, dashArray: '6 5', interactive: false,
          }).addTo(movementLayer);
        } else if (type === 'Point') {
          const [lon, lat] = coordinates;
          const kind = feature.properties.kind;
          const colors = { model_start: '#bb8cff', model_end: '#bb8cff', ais_first_reappearance: '#22c55e', latest_ais_fix: '#38bdf8',
            clue_departure: '#53d1f5', clue_destination: '#b2d7e2', sar_observation: '#75a7ff' };
          const color = colors[kind] || '#f59e0b';
          const marker = L.circleMarker([lat, lon], { radius: 7, color: '#06151d', fillColor: color,
            fillOpacity: 1, weight: 2, renderer: incidentRenderer }).addTo(movementLayer);
          const label = feature.properties.label;
          if (label) {
            const text = container.ownerDocument.createElement('span');
            text.textContent = label;
            marker.bindTooltip(text, { permanent: true, direction: 'top', offset: [0, -8], className: 'map-movement-label' });
          }
          marker.bringToFront();
        }
      }
    },
    setDrifts(collection) {
      driftsLayer.clearLayers();
      for (const feature of collection?.features || []) {
        const geometry = feature?.geometry;
        if (!geometry?.coordinates) continue;
        const color = String(feature.properties?.visual_color || '#ff5a57');
        const coordinates = geometry.coordinates;
        if (geometry.type === 'LineString' && coordinates.length > 1) {
          L.polyline(coordinates.map(([lon, lat]) => [lat, lon]), {
            color, weight: 2.5, opacity: 0.92, dashArray: '7 6', interactive: false,
          }).addTo(driftsLayer);
        } else if (geometry.type === 'Polygon') {
          for (const ring of leafletPolygonCoordinates(geometry)) {
            L.polygon(ring, { color, weight: 1.5, opacity: 0.75, fillColor: color,
              fillOpacity: 0.13, interactive: false }).addTo(driftsLayer);
          }
        } else if (geometry.type === 'Point') {
          const [lon, lat] = coordinates;
          if (Number.isFinite(Number(lon)) && Number.isFinite(Number(lat))) {
            L.circleMarker([lat, lon], { radius: 4, color, weight: 1.5,
              fillColor: color, fillOpacity: 0.9, interactive: false }).addTo(driftsLayer);
          }
        }
      }
    },
    setFeatures(payload) {
      currentPayload = payload;
      const { incidents, vessels } = normalizePayload(payload);
      markers.clearLayers();
      for (const feature of polygonFeatures(incidents)) {
        const polygons = leafletPolygonCoordinates(feature.geometry);
        for (const latlngs of polygons) {
          const color = semanticColor(feature);
          L.polygon(latlngs, {
            color, weight: 2, fillColor: color, fillOpacity: 0.22,
            className: markerClass(feature), renderer: incidentRenderer,
          }).on('click', () => onFeatureSelect?.(feature)).addTo(markers);
        }
      }
      let points = pointFeatures(incidents);
      if (cluster && map.getZoom() <= 7) {
        const cells = new Map();
        for (const feature of points) {
          const [lon, lat] = feature.geometry.coordinates;
          const { x, y } = map.project([Number(lat), Number(lon)]);
          const key = `${Math.floor(x / 55)},${Math.floor(y / 55)}`;
          if (!cells.has(key)) cells.set(key, []);
          cells.get(key).push(feature);
        }
        points = [];
        for (const group of cells.values()) {
          if (group.length === 1) {
            points.push(group[0]);
            continue;
          }
          const count = group.length;
          const { color, radius } = PLAY_CLUSTER_BANDS.findLast(({ minimum }) => count >= minimum);
          const [lat, lon] = group.reduce(([latSum, lonSum], feature) => {
            const [x, y] = feature.geometry.coordinates;
            return [latSum + Number(y), lonSum + Number(x)];
          }, [0, 0]);
          const center = [lat / count, lon / count];
          const icon = L.divIcon({
            className: 'seacommons-fallback-cluster',
            html: `<span style="background:${color}">${count}</span>`,
            iconSize: [radius * 2, radius * 2], iconAnchor: [radius, radius],
          });
          const marker = L.marker(center, { icon, title: `${count} grouped points` }).addTo(markers);
          marker.on('click', () => map.setView(center, Math.min(8, map.getZoom() + 2)));
        }
      }
      for (const feature of points) {
        const [lon, lat] = feature.geometry.coordinates;
        const uncertaintyM = Number(feature.properties?.location_uncertainty_m || 0);
        const source = String(feature.properties?.coordinate_source || '');
        if (uncertaintyM > 20000 && source.startsWith('media_') && L.circle) {
          const color = semanticColor(feature);
          L.circle([Number(lat), Number(lon)], {
            radius: uncertaintyM,
            color,
            weight: 1,
            fillColor: color,
            fillOpacity: 0.12,
            className: `${markerClass(feature)} seacommons-fallback-uncertainty`,
            renderer: incidentRenderer,
          }).on('click', () => onFeatureSelect?.(feature)).addTo(markers);
        }
        // On WebGL-unavailable devices the same active physical receivers
        // retain a recognisable antenna icon and a keyboard-accessible report.
        if (feature.properties?.radio_type === 'radio_receiver' && L.divIcon && L.marker) {
          const icon = L.divIcon({
            className: 'seacommons-fallback-radio-station',
            html: '<span aria-hidden="true" style="display:flex;align-items:center;justify-content:center;width:32px;height:32px;background:#07151b;border:2px solid #a78bfa;border-radius:50%;font-size:17px;box-sizing:border-box">📡</span>',
            iconSize: [32, 32], iconAnchor: [16, 16],
          });
          const marker = L.marker([Number(lat), Number(lon)], { icon, keyboard: true }).addTo(markers);
          bindSelection(marker, feature, onFeatureSelect);
          continue;
        }
        const heading = vesselHeading(feature);
        const attack = isAttackIncident(feature.properties);
        if (((isVesselAssociatedSignal(feature) && heading !== null) || attack) && L.divIcon && L.marker) {
          const icon = L.divIcon({
            className: `${markerClass(feature)} seacommons-fallback-vessel-icon seacommons-fallback-signal-icon${heading === null ? ' is-direction-unknown' : ''}`,
            html: `<span class="seacommons-fallback-vessel-arrow" style="--vessel-heading:${heading ?? 0}deg;--vessel-color:${semanticColor(feature)}"></span>${attack ? '<span class="seacommons-fallback-attack" aria-hidden="true">⊕</span>' : ''}`,
            iconSize: [18, 18], iconAnchor: [9, 9],
          });
          const marker = L.marker([Number(lat), Number(lon)], { icon, keyboard: true }).addTo(markers);
          bindSelection(marker, feature, onFeatureSelect);
        } else {
          const marker = L.circleMarker(
            [Number(lat), Number(lon)],
            { ...markerStyle(feature), renderer: incidentRenderer },
          ).addTo(markers);
          bindSelection(marker, feature, onFeatureSelect);
        }
      }
      for (const feature of pointFeatures(vessels)) {
        const [lon, lat] = feature.geometry.coordinates;
        const stationary = vesselIsStationary(feature);
        if (!L.divIcon || !L.marker) {
          const marker = L.circleMarker([Number(lat), Number(lon)], {
            radius: 5, weight: 1.5, color: '#06151d', fillColor: vesselColor(feature), fillOpacity: 0.98,
            className: `${markerClass(feature)} seacommons-fallback-vessel-emergency`,
          }).addTo(markers);
          bindSelection(marker, feature, onFeatureSelect);
          continue;
        }
        const heading = vesselHeading(feature);
        const color = vesselColor(feature);
        const icon = L.divIcon({
          className: `seacommons-fallback-vessel-icon${stationary ? ' is-stationary' : ''}${heading === null ? ' is-direction-unknown' : ''}`,
          html: `<span class="seacommons-fallback-vessel-arrow" style="--vessel-heading:${heading ?? 0}deg;--vessel-color:${color}"></span>`,
          iconSize: [22, 22],
          iconAnchor: [11, 11],
        });
        const marker = L.marker([Number(lat), Number(lon)], { icon, keyboard: true }).addTo(markers);
        bindSelection(marker, feature, onFeatureSelect);
      }
    },
    focusMovement(features, mobile) {
      const points = pointFeatures(features).map(({ geometry: { coordinates: [lon, lat] } }) => [lat, lon]);
      if (!points.length) return;
      const panelPadding = Math.min(410, Math.round(map.getSize().x * 0.34));
      map.fitBounds(L.latLngBounds(points), {
        paddingTopLeft: mobile ? [24, 55] : [panelPadding, 85],
        paddingBottomRight: mobile ? [24, Math.round(map.getSize().y * 0.69)] : [panelPadding, 65],
        maxZoom: 9,
      });
    },
    focusReport(feature, drifts = [], mobile = true) {
      const p = feature?.properties || {};
      const id = String(p.id || p.intel_event_id || '').replace(/^intel:/, '');
      const related = (drifts?.features || []).filter((item) => id && String(item.properties?.intel_event_id || '').replace(/^intel:/, '') === id);
      const points = [];
      const collect = (coordinates) => {
        if (!Array.isArray(coordinates)) return;
        if (coordinates.length >= 2 && typeof coordinates[0] === 'number' && typeof coordinates[1] === 'number') points.push([coordinates[1], coordinates[0]]);
        else for (const child of coordinates) collect(child);
      };
      for (const item of (related.length ? related : [feature])) collect(item.geometry?.coordinates);
      if (!points.length) return;
      const bounds = L.latLngBounds(points);
      map.invalidateSize();
      const panel = Math.min(404, Math.round(map.getSize().x * 0.30));
      map.fitBounds(bounds, { paddingTopLeft: mobile ? [22, 62] : [panel, 70],
        paddingBottomRight: mobile ? [22, Math.round(map.getSize().y * 0.64)] : [panel, 72],
        maxZoom: related.length ? 9 : 8, animate: true });
    },
    fitFeatures(payload) {
      const { incidents, vessels } = normalizePayload(payload);
      const points = [...pointFeatures(incidents), ...pointFeatures(vessels)].map((feature) => {
        const [lon, lat] = feature.geometry.coordinates;
        return [Number(lat), Number(lon)];
      });
      for (const feature of polygonFeatures(incidents)) {
        const polygons = leafletPolygonCoordinates(feature.geometry);
        for (const polygon of polygons) {
          for (const ring of polygon) points.push(...ring);
        }
      }
      if (points.length) map.fitBounds(L.latLngBounds(points), { padding: [28, 28], maxZoom: 9 });
    },
    flyTo({ center: nextCenter, zoom: nextZoom }) {
      map.flyTo([Number(nextCenter[1]), Number(nextCenter[0])], nextZoom);
    },
    resize() { map.invalidateSize(); },
    destroy() { map.remove(); },
  };
  return renderer;
}
