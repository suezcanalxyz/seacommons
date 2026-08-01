function isoUtc(value) {
  const text = String(value || '');
  if (text.endsWith('Z') || /[+-]\d\d:\d\d$/.test(text)) return text;
  return `${text}${text.length === 16 ? ':00' : ''}Z`;
}

function speedInMetersPerSecond(value, unit) {
  const speed = Number(value);
  return unit === 'km/h' ? speed / 3.6 : speed;
}

export function normalizeEnvironment(weatherPayload, marinePayload) {
  const current = weatherPayload.current || {};
  const marine = marinePayload.current || {};
  const marineUnits = marinePayload.current_units || {};
  const weatherHourly = weatherPayload.hourly || {};
  const marineHourly = marinePayload.hourly || {};
  const marineHourlyUnits = marinePayload.hourly_units || {};
  const marineIndexByTime = new Map(
    (marineHourly.time || []).map((time, index) => [time, index]),
  );
  const forecastFrames = (weatherHourly.time || []).map((time, weatherIndex) => {
    const marineIndex = marineIndexByTime.get(time);
    if (marineIndex === undefined) return null;
    const values = [
      weatherHourly.wind_speed_10m?.[weatherIndex],
      weatherHourly.wind_direction_10m?.[weatherIndex],
      speedInMetersPerSecond(
        marineHourly.ocean_current_velocity?.[marineIndex],
        marineHourlyUnits.ocean_current_velocity,
      ),
      marineHourly.ocean_current_direction?.[marineIndex],
      marineHourly.wave_height?.[marineIndex],
      marineHourly.wave_period?.[marineIndex],
      marineHourly.wave_direction?.[marineIndex],
    ].map(Number);
    if (!values.every(Number.isFinite)) return null;
    return {
      time_utc: isoUtc(time),
      wind: { speed_m_s: values[0], direction_deg: values[1] },
      current: { speed_m_s: values[2], direction_deg: values[3] },
      waves: {
        significant_height_m: values[4], period_s: values[5], direction_deg: values[6],
      },
    };
  }).filter(Boolean);
  const currentSpeedMs = speedInMetersPerSecond(
    marine.ocean_current_velocity,
    marineUnits.ocean_current_velocity,
  );
  const timestamp = current.time || marine.time || new Date().toISOString();
  return {
    timestamp_utc: isoUtc(timestamp),
    source: 'SeaCommons Edge · Open-Meteo weather + marine best match',
    wind: {
      speed_ms: Number(current.wind_speed_10m),
      speed_kn: Number(current.wind_speed_10m) * 1.94384,
      direction_deg: Number(current.wind_direction_10m),
      gust_speed_ms: Number(current.wind_gusts_10m),
    },
    waves: {
      significant_height_m: Number(marine.wave_height),
      period_s: Number(marine.wave_period),
      direction_deg: Number(marine.wave_direction),
      direction_source: 'Open-Meteo marine model',
    },
    ocean: {
      water_temp_c: Number(marine.sea_surface_temperature),
      current_speed_ms: currentSpeedMs,
      current_dir_deg: Number(marine.ocean_current_direction),
    },
    air: {
      temp_c: Number(current.temperature_2m),
      apparent_temp_c: Number(current.apparent_temperature),
      humidity_pct: Number(current.relative_humidity_2m),
      pressure_hpa: Number(current.surface_pressure),
      visibility_km: Number(current.visibility) / 1000,
      cloud_cover_pct: Number(current.cloud_cover),
      precipitation_mm: Number(current.precipitation),
      weather_code: Number(current.weather_code),
      is_day: Number(current.is_day) === 1,
    },
    environmental_model: {
      kind: 'modelled-current-conditions',
      weather_resolution: 'best-match',
      marine_resolution: '5–9 km nominal',
      navigation_use: false,
    },
    forecast_frames: forecastFrames,
  };
}

export function upstreamUrls(lat, lon) {
  const weather = new URL('https://api.open-meteo.com/v1/forecast');
  weather.searchParams.set('latitude', lat.toFixed(4));
  weather.searchParams.set('longitude', lon.toFixed(4));
  weather.searchParams.set('current', 'temperature_2m,relative_humidity_2m,apparent_temperature,is_day,precipitation,weather_code,cloud_cover,visibility,surface_pressure,wind_speed_10m,wind_direction_10m,wind_gusts_10m');
  weather.searchParams.set('hourly', 'wind_speed_10m,wind_direction_10m,wind_gusts_10m');
  weather.searchParams.set('wind_speed_unit', 'ms');
  weather.searchParams.set('timezone', 'UTC');
  weather.searchParams.set('past_days', '2');
  weather.searchParams.set('forecast_days', '3');

  const marine = new URL('https://marine-api.open-meteo.com/v1/marine');
  marine.searchParams.set('latitude', lat.toFixed(4));
  marine.searchParams.set('longitude', lon.toFixed(4));
  marine.searchParams.set('current', 'wave_height,wave_direction,wave_period,sea_surface_temperature,ocean_current_velocity,ocean_current_direction');
  marine.searchParams.set('hourly', 'wave_height,wave_direction,wave_period,sea_surface_temperature,ocean_current_velocity,ocean_current_direction');
  marine.searchParams.set('timezone', 'UTC');
  marine.searchParams.set('past_days', '2');
  marine.searchParams.set('forecast_days', '3');
  return { weather, marine };
}
