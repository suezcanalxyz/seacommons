// Maritime zone estimation using Haversine distance to known coastal reference points.
// This is an approximation for operational context — verify against official MRGID boundaries.

const COAST_REFS = [
  [41.5, 12.2,  'Italy (Lazio)'],
  [37.5, 13.5,  'Sicily'],
  [38.1, 15.6,  'Strait of Messina'],
  [35.9, 14.5,  'Malta'],
  [36.8, 10.2,  'Tunisia (Tunis)'],
  [32.9, 13.2,  'Libya (Tripoli)'],
  [32.5, 23.5,  'Libya (Benghazi)'],
  [37.9, 23.7,  'Greece (Athens)'],
  [35.3, 24.9,  'Crete'],
  [36.5, 35.2,  'Turkey (Mersin)'],
  [39.5, 0.1,   'Spain (Valencia)'],
  [41.4, 2.2,   'Spain (Barcelona)'],
  [35.7, -5.8,  'Morocco (Gibraltar)'],
  [31.2, 30.0,  'Egypt (Alexandria)'],
  [43.7, 7.4,   'France (Nice)'],
  [44.4, 8.9,   'Italy (Genoa)'],
  [45.6, 13.8,  'Slovenia (Trieste)'],
  [38.1, 13.3,  'Sicily (Palermo)'],
  [37.1, 15.1,  'Sicily (Catania)'],
  [36.9, 11.0,  'Tunisia (Sfax)'],
];

function haversineNm(lat1, lon1, lat2, lon2) {
  const R = 3440.065;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

export function estimateMaritimeZone(lat, lon) {
  let minDist = Infinity;
  let nearestCoast = '';
  for (const [rlat, rlon, label] of COAST_REFS) {
    const d = haversineNm(lat, lon, rlat, rlon);
    if (d < minDist) { minDist = d; nearestCoast = label; }
  }
  minDist = Math.round(minDist * 10) / 10;

  if (minDist < 12) return {
    zone: 'Territorial Sea', code: 'TERRITORIAL', distNm: minDist, nearestCoast,
    authority: 'Coastal State jurisdiction (UNCLOS Art. 2)',
    sarAuthority: 'National MRCC',
    color: '#ef4444',
  };
  if (minDist < 24) return {
    zone: 'Contiguous Zone', code: 'CONTIGUOUS', distNm: minDist, nearestCoast,
    authority: 'Limited coastal state control (UNCLOS Art. 33)',
    sarAuthority: 'National MRCC / Regional agreement',
    color: '#f97316',
  };
  if (minDist < 200) return {
    zone: 'Exclusive Economic Zone (EEZ)', code: 'EEZ', distNm: minDist, nearestCoast,
    authority: 'Flag state jurisdiction, coastal resource rights (UNCLOS Art. 55)',
    sarAuthority: 'MRCC Rome / Flag state MRCC',
    color: '#eab308',
  };
  return {
    zone: 'High Seas (International Waters)', code: 'HIGH_SEAS', distNm: minDist, nearestCoast,
    authority: 'Freedom of navigation (UNCLOS Art. 87) — no single state jurisdiction',
    sarAuthority: 'MRCC Rome (Mediterranean SAR region) / IMO GMDSS',
    color: '#22c55e',
  };
}

// Approximate polygon area in km² using the shoelace formula on lat/lon coords.
export function polygonAreaKm2(coordinates) {
  const pts = coordinates[0]; // outer ring
  if (!pts || pts.length < 3) return 0;
  const R = 6371; // km
  let area = 0;
  for (let i = 0; i < pts.length - 1; i++) {
    const [lon1, lat1] = pts[i];
    const [lon2, lat2] = pts[i + 1];
    area +=
      (lon2 - lon1) * Math.PI / 180 *
      (2 + Math.sin(lat1 * Math.PI / 180) + Math.sin(lat2 * Math.PI / 180));
  }
  return Math.abs((area * R * R) / 2);
}
