import type { GeoFeature, GeoGeometry } from './geo';
import type { IsoDateTime } from './json';

export type IncidentLifecycle = 'active' | 'archived' | 'needs_review' | 'resolved';

export type LocationPrecision =
  | 'approximate'
  | 'area'
  | 'area_low_confidence'
  | 'regional_centroid'
  | 'reported_or_derived'
  | 'unpositioned';

export type VerificationStatus =
  | 'derived'
  | 'machine_extracted_unverified'
  | 'modelled'
  | 'modelled_live_fields'
  | 'modelled_spatiotemporal'
  | 'multi_source_corroborated'
  | 'operator_asserted'
  | 'partner_reported'
  | 'unverified_public_source'
  | 'user_reported';

export type EventSeverity = 'critical' | 'high' | 'low' | 'medium';
export type IntelTier = 'news' | 'operational' | 'signal';
export type SourceHealthStatus = 'active' | 'degraded' | 'offline' | 'pending';

/** Maritime-awareness compartment an event belongs to. `sar` is the primary lane. */
export type MaritimeDomain =
  | 'environmental'
  | 'grey_zone'
  | 'iuu_fishing'
  | 'piracy'
  | 'safety'
  | 'sanctions'
  | 'sar'
  | 'smuggling';

export interface PublicThreadUpdate {
  tweet_id?: string | null;
  posted_at?: IsoDateTime | null;
  url?: string | null;
  kind?: string | null;
  note?: string | null;
}

export interface LiveIncidentProperties {
  schema: 'org.seacommons.live-signal/v1';
  id: string;
  type: string;
  kind: 'archived' | 'context' | 'distress' | 'needs_review' | 'resolved';
  severity: EventSeverity;
  tier: IntelTier;
  priority?: number;
  verification_status: VerificationStatus;
  publication_status?: 'published';
  source_policy?: string;
  title: string;
  text: string;
  url: string;
  source: string;
  timestamp_utc: IsoDateTime;
  source_timestamp_utc?: IsoDateTime;
  received_at?: IsoDateTime;
  incident_lifecycle?: IncidentLifecycle;
  location_precision: LocationPrecision;
  location_uncertainty_m?: number;
  coordinate_source?: string;
  persons?: number;
  linked_mmsi?: string;
  repost_count?: number;
  thread_reposts?: PublicThreadUpdate[];
  area_weather_narrowed?: boolean;
}

export type LiveIncident = GeoFeature<GeoGeometry | null, LiveIncidentProperties>;

export interface LiveEventProperties {
  incident_id: string;
  incident_lifecycle?: IncidentLifecycle;
  expired?: boolean;
  severity?: EventSeverity;
  title?: string;
  text?: string;
  verification_status?: VerificationStatus;
  coordinate_source?: string;
  radius_m?: number;
  persons?: number;
  linked_mmsi?: string;
  repost_count?: number;
  thread_reposts?: PublicThreadUpdate[];
  location_precision?: LocationPrecision;
  area_weather_narrowed?: boolean;
}

export interface LiveEvent {
  schema: 'seacommons-event-v1';
  id: string;
  hash: string;
  type: string;
  source: string;
  node: string;
  observed_at: IsoDateTime;
  received_at: IsoDateTime;
  expires_at_ms: number;
  visibility: 'public';
  confidence: number | null;
  geometry: GeoGeometry | null;
  properties: LiveEventProperties;
  source_url: string | null;
  previous_hash: string | null;
}

export interface EdgeSourceHealth {
  source: string;
  node: string;
  status: Exclude<SourceHealthStatus, 'pending'>;
  observed_at: IsoDateTime;
  received_at: IsoDateTime;
  age_seconds: number | null;
}

export interface MonitorSourceHealth {
  name: string;
  type: string;
  status: SourceHealthStatus;
  last_poll_at: IsoDateTime | null;
  events_last_hour: number;
  total_events: number;
  consecutive_errors: number;
  last_error: string | null;
  registered_at: IsoDateTime;
}

export type SourceHealth = EdgeSourceHealth | MonitorSourceHealth;

export interface LiveSnapshot {
  schema: 'seacommons-live-snapshot-v1';
  mode: 'ephemeral-live';
  generated_at: IsoDateTime;
  updated_at: IsoDateTime | null;
  head_hash: string | null;
  last_heartbeat_at: IsoDateTime | null;
  source_health: EdgeSourceHealth[];
  counts: { total: number } & Partial<Record<IncidentLifecycle, number>>;
  ttl_seconds: number;
  events: LiveEvent[];
}

export type LiveStreamMessage =
  | ({ type: 'snapshot' } & LiveSnapshot)
  | { type: 'event' | 'remove'; event: LiveEvent; incident_id: string }
  | { type: 'source_health'; source: EdgeSourceHealth }
  | { type: 'reset'; at: IsoDateTime };
