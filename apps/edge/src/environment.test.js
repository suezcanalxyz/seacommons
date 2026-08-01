import assert from 'node:assert/strict';
import test from 'node:test';

import { normalizeEnvironment, upstreamUrls } from './environment.js';

test('normalizes current velocity to metres per second and aligns hourly frames', () => {
  const weather = {
    current: { time: '2026-08-01T10:00', wind_speed_10m: 5, wind_direction_10m: 270, wind_gusts_10m: 7 },
    hourly: { time: ['2026-08-01T10:00'], wind_speed_10m: [5], wind_direction_10m: [270] },
  };
  const marine = {
    current_units: { ocean_current_velocity: 'km/h' },
    hourly_units: { ocean_current_velocity: 'km/h' },
    current: { time: '2026-08-01T10:00', wave_height: 1, wave_direction: 260, wave_period: 6, sea_surface_temperature: 24, ocean_current_velocity: 3.6, ocean_current_direction: 90 },
    hourly: { time: ['2026-08-01T10:00'], wave_height: [1], wave_direction: [260], wave_period: [6], ocean_current_velocity: [3.6], ocean_current_direction: [90] },
  };
  const result = normalizeEnvironment(weather, marine);
  assert.equal(result.ocean.current_speed_ms, 1);
  assert.equal(result.forecast_frames[0].current.speed_m_s, 1);
  assert.equal(result.forecast_frames[0].time_utc, '2026-08-01T10:00:00Z');
});

test('upstream request always uses UTC, metric wind and three forecast days', () => {
  const urls = upstreamUrls(37.5, 15.1);
  assert.equal(urls.weather.searchParams.get('timezone'), 'UTC');
  assert.equal(urls.weather.searchParams.get('wind_speed_unit'), 'ms');
  assert.equal(urls.weather.searchParams.get('past_days'), '2');
  assert.equal(urls.marine.searchParams.get('forecast_days'), '3');
});
