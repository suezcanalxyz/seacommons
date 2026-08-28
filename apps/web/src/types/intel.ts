import type { GeoFeature, GeoGeometry } from './geo';
import type { IsoDateTime, JsonValue } from './json';
import type {
  EventSeverity,
  IncidentLifecycle,
  IntelTier,
  LocationPrecision,
  MaritimeDomain,
  PublicThreadUpdate,
  VerificationStatus,
} from './live';

export interface IntelEventProperties {
  id: string;
  type: string;
  severity: EventSeverity;
  tier: IntelTier;
  priority: number;
  maritime_domain: MaritimeDomain;
  verification_status: VerificationStatus;
  drift_ready: boolean;
  title: string;
  text: string;
  url: string;
  source: string;
  author: string;
  linked_mmsi: string;
  timestamp_utc: IsoDateTime;
  kind?: 'archived' | 'distress' | 'needs_review' | 'resolved';
  incident_lifecycle?: IncidentLifecycle;
  publication_status?: string;
  source_policy?: string;
  location_precision?: LocationPrecision;
  location_uncertainty_m?: number;
  coordinate_source?: string;
  repost_count?: number;
  thread_reposts?: PublicThreadUpdate[];
  metadata?: Record<string, JsonValue>;
}

/** Canonical frontend representation returned by the intel GeoJSON APIs. */
export type IntelEvent = GeoFeature<GeoGeometry | null, IntelEventProperties>;
