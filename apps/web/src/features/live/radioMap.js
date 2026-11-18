export function radioCoordinates(row) {
  const values = [row.longitude, row.latitude];
  if (!values.every((value) => typeof value === 'number'
    || (typeof value === 'string' && value.trim()))) return null;
  const [lon, lat] = values.map(Number);
  return Number.isFinite(lon) && Number.isFinite(lat) && Math.abs(lon) <= 180 && Math.abs(lat) <= 90
    && (lon !== 0 || lat !== 0) ? [lon, lat] : null;
}

export function radioFeature(row, type) {
  const coordinates = radioCoordinates(row);
  return {
    type: 'Feature',
    geometry: coordinates ? { type: 'Point', coordinates } : null,
    properties: type === 'radio_receiver' ? {
      ...row, radio_type: type, visual_color: '#a78bfa',
      capabilities_json: JSON.stringify(row.capabilities || []),
    } : {
      ...row, radio_type: type, visual_color: row.category === 'distress' ? '#ff3b3b'
        : row.category === 'urgency' ? '#f59e0b' : row.category === 'safety' ? '#38bdf8' : '#a78bfa',
      ais_association_json: JSON.stringify(row.ais_association || null),
    },
  };
}
