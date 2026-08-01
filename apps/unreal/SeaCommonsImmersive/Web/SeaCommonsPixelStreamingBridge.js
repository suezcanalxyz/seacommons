/**
 * Install this in the Pixel Streaming frontend that is embedded by Play.
 * `emitUIInteraction` is provided by the matching Epic Pixel Streaming
 * frontend version. Parent origins must be explicit in production.
 */
export function installSeaCommonsPixelStreamingBridge({
  emitUIInteraction,
  allowedParentOrigins,
}) {
  if (typeof emitUIInteraction !== 'function') {
    throw new Error('Pixel Streaming emitUIInteraction callback is required');
  }
  const allowed = new Set(allowedParentOrigins || []);
  const receive = (event) => {
    if (!allowed.has(event.origin)) return;
    if (event.data?.type !== 'seacommons.scene') return;
    if (event.data?.payload?.schema_version !== 'drift-scene/v1') return;
    emitUIInteraction(event.data);
  };
  window.addEventListener('message', receive);
  return () => window.removeEventListener('message', receive);
}
