export const FEDERATED_EVENT_SCHEMA = 'seacommons-event-v1';

export const INCIDENT_LIFECYCLES = Object.freeze([
  'active',
  'resolved',
  'needs_review',
  'archived',
]);

export const LOCATION_PRECISIONS = Object.freeze([
  'unpositioned',
  'approximate',
  'regional_centroid',
  'reported_or_derived',
  'area',
  'area_low_confidence',
]);

export const PUBLIC_GEOMETRY_TYPES = Object.freeze(['Point', 'Polygon', 'MultiPolygon']);
