export const DEFAULT_LAYER_STORAGE_KEY = 'seacommons_layer_vis';
export const PUBLIC_LIVE_LAYER_STORAGE_KEY = 'seacommons_live_layer_vis_v2';

const BASE_DEFAULTS = Object.freeze({
  vessels: true,
  ais_moving: true,
  ais_stationary: true,
  ais_trails: true,
  radio_receivers: true,
  radio_dsc: true,
  ngo_vessels: true,
  weather: true,
  sar: true,
  fused: true,
  spikes: true,
  platforms: true,
  alerts: true,
});

export function layerVisibilityStorageKey(publicLive = false) {
  return publicLive ? PUBLIC_LIVE_LAYER_STORAGE_KEY : DEFAULT_LAYER_STORAGE_KEY;
}
export function initialLayerVisibility({ publicLive = false, storage = globalThis.localStorage } = {}) {
  const defaults = {
    ...BASE_DEFAULTS,
    ...(publicLive ? {
      ais_moving: false,
      ais_stationary: false,
      ais_trails: false,
    } : {}),
  };
  try {
    const key = layerVisibilityStorageKey(publicLive);
    const saved = JSON.parse(storage?.getItem?.(key) || '{}');
    const merged = { ...defaults, ...saved };
    if (publicLive) merged.ngo_vessels = true;
    return merged;
  } catch {
    return defaults;
  }
}
