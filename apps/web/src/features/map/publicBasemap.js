// Official EMODnet WMTS, globally covered (data detail varies by survey region).
// No API key. Native 0–15 Web Mercator tiles; do not imply daily seafloor updates.
export const PUBLIC_BASEMAP_TILE_URL = 'https://tiles.emodnet-bathymetry.eu/latest/mean_atlas_land/web_mercator/{z}/{x}/{y}.png';
export const PUBLIC_BASEMAP_NATIVE_MAX_ZOOM = 15;
export const PUBLIC_BASEMAP_ATTRIBUTION = '© EMODnet Bathymetry (European Marine Observation and Data Network)';
// CARTO raster tiles require an API key as of September 2026.
// VITE_* is embedded in the public client bundle: configure domain restrictions
// on the CARTO dashboard. Never commit account keys into source control.
// Only load label tiles when the key is configured; preserve free EMODnet raster.
const cartoKey = String(import.meta.env?.VITE_CARTO_BASEMAP_KEY || '').trim();
const cartoLabelUrl = (style) => cartoKey
  ? `https://basemaps.cartocdn.com/${style}/{z}/{x}/{y}.png?key=${encodeURIComponent(cartoKey)}`
  : '';
export const PUBLIC_BASEMAP_LABEL_URL = cartoLabelUrl('dark_only_labels');
export const SATELLITE_BASEMAP_LABEL_URL = cartoLabelUrl('light_only_labels');
export const CARTO_LABEL_NATIVE_MAX_ZOOM = 16;
export const CARTO_LABEL_MIN_ZOOM = 4;
export const PUBLIC_SEAMARK_TILE_URL = 'https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png';

export function publicBasemapSource() {
  return {
    type: 'raster',
    tiles: [PUBLIC_BASEMAP_TILE_URL],
    tileSize: 256,
    maxzoom: PUBLIC_BASEMAP_NATIVE_MAX_ZOOM,
    attribution: PUBLIC_BASEMAP_ATTRIBUTION,
  };
}

export const SATELLITE_BASEMAP_TILE_URL = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
