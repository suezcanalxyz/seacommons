import type {
  GeoFeature,
  GeoFeatureCollection,
  LineStringGeometry,
  PointGeometry,
  PolygonGeometry,
} from './geo';
import type { IsoDateTime, JsonObject } from './json';

export type DriftDomain = 'atmosphere' | 'ballistic' | 'ocean_oil' | 'ocean_sar';

export interface DriftRequest {
  lat: number;
  lon: number;
  timestamp?: IsoDateTime;
  duration_h?: number;
  domain?: DriftDomain;
  config?: JsonObject;
}

export interface DriftJobAccepted {
  drift_id: string;
  job_id: string | null;
  status: 'computing';
}

export interface DriftFeatureProperties {
  type?: string;
  radius_m?: number;
  hours?: number;
  degraded?: boolean;
  // Probability-of-containment search ellipse (server cones, Phase 15e).
  method?: string;
  particles?: number;
  radius_p50_m?: number;
  radius_p90_m?: number;
  semi_axes_p90_m?: [number, number];
  area_km2?: number;
}

export interface DriftResult {
  trajectory: GeoFeature<LineStringGeometry, DriftFeatureProperties>;
  cone_6h: GeoFeature<PointGeometry | PolygonGeometry, DriftFeatureProperties>;
  cone_12h: GeoFeature<PointGeometry | PolygonGeometry, DriftFeatureProperties>;
  cone_24h: GeoFeature<PointGeometry | PolygonGeometry, DriftFeatureProperties>;
  impact_point: GeoFeatureCollection<PointGeometry, DriftFeatureProperties> | null;
  metadata: JsonObject;
}

export type DriftGeoJsonResponse = GeoFeatureCollection<
  LineStringGeometry | PointGeometry | PolygonGeometry,
  DriftFeatureProperties
> & { metadata: JsonObject };
