import type { GeoFeature, PointGeometry } from './geo';
import type { IsoDateTime } from './json';

export interface VesselPosition {
  mmsi: string;
  ship_name: string;
  type: string;
  lat: number;
  lon: number;
  speed: number | null;
  course: number | null;
  last_seen: IsoDateTime | null;
  distance_km?: number;
  distance_nm?: number;
}

export interface VesselFeatureProperties {
  vessel_id: string;
  mmsi: string;
  ship_name: string;
  imo: string | null;
  ship_type: string | null;
  ais_class: string;
  destination: string;
  course: number | null;
  speed: number | null;
  heading: number | null;
  last_seen: IsoDateTime | null;
  sources: string[];
}

export type VesselFeature = GeoFeature<PointGeometry, VesselFeatureProperties>;

export interface NearestVesselsResponse {
  query: { lat: number; lon: number; limit: number };
  count: number;
  vessels: VesselPosition[];
}
