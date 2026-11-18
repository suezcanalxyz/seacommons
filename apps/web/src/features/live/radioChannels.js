/** Public GMDSS channel inventory. Never infer RF monitoring from SDR tuning range. */
export const MARITIME_RADIO_CHANNELS = Object.freeze([
  { id: 'dsc-mf-2187', label: 'MF DSC', frequency_hz: 2187500, family: 'dsc', decoder: 'ready' },
  { id: 'dsc-hf-4207', label: 'HF DSC 4 MHz', frequency_hz: 4207500, family: 'dsc', decoder: 'ready' },
  { id: 'dsc-hf-6312', label: 'HF DSC 6 MHz', frequency_hz: 6312000, family: 'dsc', decoder: 'ready' },
  { id: 'dsc-hf-8414', label: 'HF DSC 8 MHz', frequency_hz: 8414500, family: 'dsc', decoder: 'ready' },
  { id: 'dsc-hf-12577', label: 'HF DSC 12 MHz', frequency_hz: 12577000, family: 'dsc', decoder: 'ready' },
  { id: 'dsc-hf-16804', label: 'HF DSC 16 MHz', frequency_hz: 16804500, family: 'dsc', decoder: 'ready' },
  { id: 'navtex-490', label: 'NAVTEX national', frequency_hz: 490000, family: 'navtex', decoder: 'ready' },
  { id: 'navtex-518', label: 'NAVTEX international', frequency_hz: 518000, family: 'navtex', decoder: 'ready' },
  { id: 'navtex-4209', label: 'HF NAVTEX', frequency_hz: 4209500, family: 'navtex', decoder: 'not_configured' },
  { id: 'vhf-dsc-70', label: 'VHF DSC Ch70', frequency_hz: 156525000, family: 'vhf_dsc', decoder: 'not_supported' },
  { id: 'vhf-voice-16', label: 'VHF voice Ch16', frequency_hz: 156800000, family: 'vhf_voice', decoder: 'not_supported' },
]);

/** Receiver metadata is a nominal frequency profile, never actual off-air coverage. */
export function receiverNominalChannels(row) {
  const capabilities = Array.isArray(row?.capabilities) ? row.capabilities : [];
  return MARITIME_RADIO_CHANNELS
    .filter((channel) => capabilities.some((capability) =>
      Number.isFinite(Number(capability.min_hz)) &&
      Number.isFinite(Number(capability.max_hz)) &&
      Number(capability.min_hz) <= channel.frequency_hz &&
      channel.frequency_hz <= Number(capability.max_hz)))
    .map((channel) => channel.id);
}

export function monitoredRadioChannels(mesh) {
  const live = mesh?.fresh === true && Array.isArray(mesh.receivers)
    ? mesh.receivers.filter((row) => row?.active === true) : [];
  return MARITIME_RADIO_CHANNELS.map((channel) => {
    const receivers = live.filter((row) => row.frequency_hz === channel.frequency_hz);
    return { ...channel, active_receivers: receivers.length,
      state: receivers.length ? 'receiving' : 'not_monitored' };
  });
}
