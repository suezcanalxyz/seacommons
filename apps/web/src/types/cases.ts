import type { IsoDateTime, JsonObject } from './json';

export type CaseStatus = 'active' | 'closed' | 'monitoring' | 'open' | 'resolved' | 'triage';
export type CasePriority = 'critical' | 'high' | 'low' | 'medium';
export type CaseType =
  | 'distress_sar'
  | 'pushback'
  | 'shipwreck'
  | 'missing_persons'
  | 'interception'
  | 'vessel_incident'
  | 'monitoring'
  | 'unspecified';

export interface Case {
  case_id: string;
  organization_id: string | null;
  title: string;
  status: CaseStatus;
  case_type: CaseType;
  priority: CasePriority;
  sensitivity: string;
  summary: string;
  lat: number | null;
  lon: number | null;
  persons: number | null;
  assigned_to: string | null;
  retention_until: IsoDateTime | null;
  legal_hold: number;
  created_by: string;
  created_at: IsoDateTime;
  updated_at: IsoDateTime;
}

export interface CaseTimelineEntry {
  entry_id: string;
  case_id: string;
  event_type: string;
  actor: string;
  body: string;
  data: JsonObject;
  created_at: IsoDateTime;
}

export interface CaseAttachment {
  attachment_id: string;
  case_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  uploaded_by: string;
  created_at: IsoDateTime;
}

export interface CaseDetail extends Case {
  signals: JsonObject[];
  timeline: CaseTimelineEntry[];
  attachments: CaseAttachment[];
}

export interface InboxSignal {
  signal_id: string;
  source_channel: string;
  received_at: IsoDateTime;
  raw_text?: string;
  requires_human_review?: boolean;
  lat?: number;
  lon?: number;
  persons?: number;
}
