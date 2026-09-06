const STATES = new Set(['live', 'degraded', 'offline', 'disabled']);
const RECEIVER_FIELDS = [
  'receiver_id', 'station_label', 'provider', 'state', 'channel_kind',
  'frequency_hz', 'mode', 'last_observation_at', 'observations_received',
];

export function normalizePipelineSources(payload = {}) {
  const sources = Array.isArray(payload?.sources) ? payload.sources : [];
  return sources
    .filter((source) => source && typeof source.family === 'string')
    .map((source) => {
      const state = STATES.has(source.state) ? source.state : 'degraded';
      const normalized = {
        family: source.family,
        label: source.label || source.family,
        state,
      };
      for (const key of ['mode', 'configured', 'started', 'failed', 'last_observation_at']) {
        if (source[key] !== undefined) normalized[key] = source[key];
      }
      if (Array.isArray(source.receivers)) {
        normalized.receivers = source.receivers.map((receiver) => {
          const row = {};
          for (const key of RECEIVER_FIELDS) {
            if (receiver?.[key] !== undefined) row[key] = receiver[key];
          }
          return row;
        });
      }
      return normalized;
    });
}

export function receiverChannelLabel(receiver = {}) {
  const kind = String(receiver.channel_kind || 'monitor').toUpperCase();
  const pieces = [kind === 'MONITOR' ? 'Monitor' : kind];
  const hz = Number(receiver.frequency_hz);
  if (Number.isFinite(hz) && hz > 0) {
    pieces.push(hz >= 1_000_000 ? `${(hz / 1000).toFixed(1)} kHz` : `${(hz / 1000).toFixed(hz % 1000 ? 1 : 0)} kHz`);
  }
  if (receiver.mode) pieces.push(String(receiver.mode).toUpperCase());
  return pieces.join(' · ');
}
