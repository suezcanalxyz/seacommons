// Official EMODnet WMTS, globally covered (data detail varies by survey region).
// No API key. Native 0–15 Web Mercator tiles; do not imply daily seafloor updates.
export const PUBLIC_BASEMAP_TILE_URL = 'https://tiles.emodnet-bathymetry.eu/latest/mean_atlas_land/web_mercator/{z}/{x}/{y}.png';
export const PUBLIC_BASEMAP_NATIVE_MAX_ZOOM = 15;
export const PUBLIC_BASEMAP_ATTRIBUTION = '© EMODnet Bathymetry (European Marine Observation and Data Network)';
export const PUBLIC_BASEMAP_LABEL_URL = 'https://basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}.png';
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
