// Attack is a semantic overlay, never a colour category. Only explicit
// attack/strike classifications qualify; severity and arbitrary news text do not.
export function isAttackIncident(properties = {}) {
  const tokens = [properties.incident_type, properties.attack_type, properties.event_type,
    properties.visual_category, properties.maritime_domain, properties.type]
    .filter((value) => typeof value === 'string')
    .join(' ').toLowerCase();
  return /(?:^|[\s_/-])(attack|attacks|strike|strikes|missile_attack|drone_attack|armed_attack)(?:$|[\s_/-])/.test(tokens);
}

// Small 32px crosshair, independent of base category colour. No external fonts.
export function createAttackMarkerImage(size = 32) {
  const data = new Uint8Array(size * size * 4);
  const mid = (size - 1) / 2;
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
    const dx = x - mid;
    const dy = y - mid;
    const r = Math.hypot(dx, dy);
    const ring = r > size * .29 && r < size * .38;
    const cross = (Math.abs(dx) < size * .055 && Math.abs(dy) < size * .43)
      || (Math.abs(dy) < size * .055 && Math.abs(dx) < size * .43);
    if (!ring && !cross) continue;
    const index = (y * size + x) * 4;
    data[index] = 255; data[index + 1] = 255; data[index + 2] = 255; data[index + 3] = 255;
  }
  return { width: size, height: size, data };
}
