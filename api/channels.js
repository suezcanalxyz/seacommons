// Read-only multi-channel projection based on actual connected Oracle RF mesh.
// This endpoint can deploy independently from the older Oracle application.
// No new receiver socket, decoder or hardware channel is activated.
const MESH_URL = 'https://live.seacommons.org/api/v1/live/receivers/mesh?limit=64';
export const CHANNELS = Object.freeze([
  ['MF DSC', 'dsc', 2187500, true],
  ['HF DSC 4 MHz', 'dsc', 4207500, true],
  ['HF DSC 6 MHz', 'dsc', 6312000, true],
  ['HF DSC 8 MHz', 'dsc', 8414500, true],
  ['HF DSC 12 MHz', 'dsc', 12577000, true],
  ['HF DSC 16 MHz', 'dsc', 16804500, true],
  ['NAVTEX national', 'navtex', 490000, true],
  ['NAVTEX international', 'navtex', 518000, true],
  ['HF NAVTEX', 'navtex', 4209500, false],
  ['VHF DSC Ch70', 'vhf_dsc', 156525000, false],
  ['VHF voice Ch16', 'vhf_voice', 156800000, false],
]);

export function projectConnectedChannels(mesh) {
  if (!mesh || !Array.isArray(mesh.receivers) || !Number.isInteger(mesh.active)) {
    throw new Error('invalid RF receiver mesh');
  }
  const connected = mesh.receivers.filter((row) =>
    row && row.active === true && typeof row.receiver_id === 'string' &&
    row.receiver_id && Number.isInteger(row.frequency_hz));
  return {
    source: 'seacommons_rf_mesh',
    count_scope: 'currently_connected_receivers',
    generated_at: new Date().toISOString(),
    upstream_active_total: mesh.active,
    receivers_in_page: connected.length,
    warning: 'Numbers reflect connected tuning only; not signal coverage or successful message decoding.',
    channels: CHANNELS.map(([label, family, frequency_hz, decoder_ready]) => {
      const ids = new Set(connected.filter((row) => row.frequency_hz === frequency_hz)
        .map((row) => row.receiver_id));
      return { label, family, frequency_hz, decoder_ready,
        active_receivers: ids.size, state: ids.size ? 'receiving' : 'not_monitored' };
    }),
  };
}

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    res.setHeader('Allow', 'GET');
    return res.status(405).json({ detail: 'Method not allowed' });
  }
  try {
    const upstream = await fetch(MESH_URL, {
      headers: { accept: 'application/json' },
      signal: AbortSignal.timeout(7500),
    });
    if (!upstream.ok) throw new Error('RF mesh upstream unavailable');
    const result = projectConnectedChannels(await upstream.json());
    res.setHeader('cache-control', 'public, s-maxage=15, stale-while-revalidate=15');
    return res.status(200).json(result);
  } catch {
    res.setHeader('cache-control', 'no-store');
    return res.status(503).json({
      source: 'seacommons_rf_mesh', state: 'unavailable',
      channels: [], warning: 'No current RF state verified; unavailable is not zero.',
    });
  }
}
