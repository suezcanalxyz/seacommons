import type { JsonObject } from './json';

export type Position = [longitude: number, latitude: number, ...extra: number[]];

export type GeoBoundingBox =
  | [west: number, south: number, east: number, north: number]
  | [west: number, south: number, minAltitude: number, east: number, north: number, maxAltitude: number];

export interface PointGeometry {
  type: 'Point';
  coordinates: Position;
}

export interface MultiPointGeometry {
  type: 'MultiPoint';
  coordinates: Position[];
}

export interface LineStringGeometry {
  type: 'LineString';
  coordinates: Position[];
}

export interface MultiLineStringGeometry {
  type: 'MultiLineString';
  coordinates: Position[][];
}

export interface PolygonGeometry {
  type: 'Polygon';
  coordinates: Position[][];
}

export interface MultiPolygonGeometry {
  type: 'MultiPolygon';
  coordinates: Position[][][];
}

export interface GeometryCollection {
  type: 'GeometryCollection';
  geometries: GeoGeometry[];
}

export type GeoGeometry =
  | PointGeometry
  | MultiPointGeometry
  | LineStringGeometry
  | MultiLineStringGeometry
  | PolygonGeometry
  | MultiPolygonGeometry
  | GeometryCollection;

export type GeoJsonProperties = JsonObject;

export interface GeoFeature<
  Geometry extends GeoGeometry | null = GeoGeometry | null,
  Properties = GeoJsonProperties,
> {
  type: 'Feature';
  id?: number | string;
  bbox?: GeoBoundingBox;
  geometry: Geometry;
  properties: Properties;
}

export interface GeoFeatureCollection<
  Geometry extends GeoGeometry | null = GeoGeometry | null,
  Properties = GeoJsonProperties,
> {
  type: 'FeatureCollection';
  bbox?: GeoBoundingBox;
  features: Array<GeoFeature<Geometry, Properties>>;
  meta?: JsonObject;
}
