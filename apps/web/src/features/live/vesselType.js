/**
 * AIS ship-type code -> display label (docs/fixes.md M0.4).
 *
 * Vessel type is context, never an inferred analytical category
 * (docs/fixes.md invariant). An unrecognised code returns "Unknown", not a
 * fabricated "Other vessel" class the code never actually established.
 */
export function shipTypeLabel(value) {
  if (value == null || value === '' || String(value).toLowerCase() === 'unknown') return 'Unknown';
  const code = Number(value);
  if (!Number.isFinite(code)) return String(value).replace(/_/g, ' ');
  let label = 'Unknown';
  if (code >= 20 && code <= 29) label = 'Wing in ground';
  else if (code === 30) label = 'Fishing';
  else if (code === 31) label = 'Towing';
  else if (code === 32) label = 'Towing (large tow)';
  else if (code === 33) label = 'Dredging / underwater operations';
  else if (code === 34) label = 'Diving operations';
  else if (code === 35) label = 'Military operations';
  else if (code === 36) label = 'Sailing vessel';
  else if (code === 37) label = 'Pleasure craft';
  else if (code >= 40 && code <= 49) label = 'High-speed craft';
  else if (code === 50) label = 'Pilot vessel';
  else if (code === 51) label = 'Search and rescue vessel';
  else if (code === 52) label = 'Tug';
  else if (code === 53) label = 'Port tender';
  else if (code === 54) label = 'Anti-pollution vessel';
  else if (code === 55) label = 'Law-enforcement vessel';
  else if (code === 58) label = 'Medical transport';
  else if (code === 59) label = 'Non-combatant ship';
  else if (code >= 60 && code <= 69) label = 'Passenger ship';
  else if (code >= 70 && code <= 79) label = 'Cargo ship';
  else if (code >= 80 && code <= 89) label = 'Tanker';
  return `${label} (${code})`;
}
