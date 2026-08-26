export const DEFAULT_SCENE_LAT = 35.52;
export const DEFAULT_SCENE_LON = 14.08;
export const MAX_PERSON_MARKERS = 24;

function clamp(value, minimum, maximum) {
  return Math.min(maximum, Math.max(minimum, value));
}

export function trajectoryFromGeoJson(geojson, fallbackLon, fallbackLat) {
  const feature = geojson?.features?.find((item) => item.geometry?.type === 'LineString');
  const coordinates = feature?.geometry?.coordinates
    ?.filter((point) => Array.isArray(point)
      && Number.isFinite(Number(point[0]))
      && Number.isFinite(Number(point[1])))
    .map((point) => [Number(point[0]), Number(point[1])]);
  const safeCoordinates = coordinates?.length >= 2
    ? coordinates
    : [[fallbackLon, fallbackLat]];
  const rawTimes = feature?.properties?.timestamps_utc || [];
  const parsedTimes = rawTimes.map((value) => Date.parse(value));
  const validTimes = parsedTimes.length === safeCoordinates.length
    && parsedTimes.every(Number.isFinite)
    && parsedTimes.every((value, index) => index === 0 || value > parsedTimes[index - 1]);
  const startTime = validTimes ? parsedTimes[0] : 0;
  const timeOffsets = validTimes
    ? parsedTimes.map((value) => (value - startTime) / 1000)
    : safeCoordinates.map((_, index) => index * 3600);
  const rawSpeeds = feature?.properties?.speed_ms || [];
  const speeds = rawSpeeds.length === safeCoordinates.length
    ? rawSpeeds.map((value) => Math.max(0, Number(value) || 0))
    : safeCoordinates.map(() => 0);
  return { coordinates: safeCoordinates, timeOffsets, speeds };
}

export function environmentalState(weather, now = new Date()) {
  const height = Math.max(.08, Number(weather?.waves?.significant_height_m) || .65);
  const period = Math.max(2.5, Number(weather?.waves?.period_s) || 5.5);
  const waveDirection = Number(weather?.waves?.direction_deg);
  const windDirection = Number(weather?.wind?.direction_deg);
  const driftDirection = Number(weather?.sar_conditions?.drift_dir_deg);
  const cloudCover = Number(weather?.air?.cloud_cover_pct);
  const visibility = Number(weather?.air?.visibility_km);
  const weatherCode = Number(weather?.air?.weather_code);
  const isDay = weather?.air?.is_day;
  return {
    waveHeight: height,
    wavePeriod: period,
    directionDeg: Number.isFinite(waveDirection)
      ? waveDirection
      : Number.isFinite(windDirection)
        ? windDirection
        : Number.isFinite(driftDirection)
          ? driftDirection
          : 285,
    directionSource: Number.isFinite(waveDirection)
      ? weather?.waves?.direction_source || 'marine model'
      : 'wind proxy',
    windSpeed: Math.max(0, Number(weather?.wind?.speed_ms) || 3.8),
    windGust: Math.max(
      0,
      Number(weather?.wind?.gust_speed_ms) || Number(weather?.wind?.speed_ms) || 3.8,
    ),
    currentSpeed: Math.max(0, Number(weather?.ocean?.current_speed_ms) || .18),
    currentDirection: Number(weather?.ocean?.current_dir_deg) || 315,
    cloudCover: Number.isFinite(cloudCover) ? clamp(cloudCover, 0, 100) : 35,
    visibilityKm: Number.isFinite(visibility) ? Math.max(.2, visibility) : 15,
    precipitationMm: Math.max(0, Number(weather?.air?.precipitation_mm) || 0),
    weatherCode: Number.isFinite(weatherCode) ? weatherCode : 1,
    isDay: typeof isDay === 'boolean' ? isDay : true,
    humidity: clamp(Number(weather?.air?.humidity_pct) || 65, 0, 100),
    pressure: Number(weather?.air?.pressure_hpa) || 1013,
    timestamp: weather?.timestamp_utc || now.toISOString(),
    source: weather?.source || 'awaiting environmental feed',
  };
}

export function weatherDescription(code) {
  if (code === 0) return 'clear';
  if ([1, 2].includes(code)) return 'partly cloudy';
  if (code === 3) return 'overcast';
  if ([45, 48].includes(code)) return 'fog';
  if ([51, 53, 55, 56, 57].includes(code)) return 'drizzle';
  if ([61, 63, 65, 66, 67, 80, 81, 82].includes(code)) return 'rain';
  if ([71, 73, 75, 77, 85, 86].includes(code)) return 'snow';
  if ([95, 96, 99].includes(code)) return 'thunderstorm';
  return 'modelled conditions';
}

/** Superposed wave trains shared by the mesh and vessel pose calculation. */
export function sampleWaveField(worldEast, worldNorth, environment) {
  const waveHeight = clamp(environment.waveHeight, .08, 5);
  const primaryLength = clamp(1.56 * environment.wavePeriod * environment.wavePeriod, 22, 190);
  const secondaryLength = Math.max(13, primaryLength * .46);
  const tertiaryLength = Math.max(8, primaryLength * .23);
  const bearing = environment.directionDeg * Math.PI / 180;
  const primaryEast = Math.sin(bearing);
  const primaryNorth = Math.cos(bearing);
  const crossEast = Math.cos(bearing);
  const crossNorth = -Math.sin(bearing);
  const k1 = Math.PI * 2 / primaryLength;
  const k2 = Math.PI * 2 / secondaryLength;
  const k3 = Math.PI * 2 / tertiaryLength;
  const amplitude1 = waveHeight * .42;
  const amplitude2 = waveHeight * .17;
  const amplitude3 = Math.min(.18, waveHeight * .07);
  const phase1 = (worldEast * primaryEast + worldNorth * primaryNorth) * k1;
  const phase2 = (worldEast * crossEast + worldNorth * crossNorth) * k2 + 1.7;
  const phase3 = ((worldEast + worldNorth) * .7071) * k3 - .8;
  return {
    sum: amplitude1 * Math.sin(phase1)
      + amplitude2 * Math.sin(phase2)
      + amplitude3 * Math.sin(phase3),
    slopeEast: amplitude1 * Math.cos(phase1) * k1 * primaryEast
      + amplitude2 * Math.cos(phase2) * k2 * crossEast
      + amplitude3 * Math.cos(phase3) * k3 * .7071,
    slopeNorth: amplitude1 * Math.cos(phase1) * k1 * primaryNorth
      + amplitude2 * Math.cos(phase2) * k2 * crossNorth
      + amplitude3 * Math.cos(phase3) * k3 * .7071,
  };
}

export function trajectoryDisplayMode(features) {
  if (!Array.isArray(features) || features.length === 0) return 'awaiting trajectory';
  if (features.some((feature) => feature.properties?.engine === 'seacommons-browser')) {
    return 'live browser engine';
  }
  if (features.some((feature) => feature.properties?.degraded)) return 'degraded estimate';
  return 'OpenDrift result';
}
