import type { IsoDateTime, JsonObject } from './json';

export type ConnectorProvider = 'whatsapp_cloud';
export type ConnectorStatus = 'active' | 'paused' | 'pending';
export type ConnectorPublicationPolicy = 'internal' | 'private';

export interface Connector {
  connector_id: string;
  organization_id: string;
  provider: ConnectorProvider;
  display_name: string;
  status: ConnectorStatus;
  external_account_id: string | null;
  external_channel_id: string;
  display_address: string | null;
  credentials_configured: boolean;
  publication_policy: ConnectorPublicationPolicy;
  configuration: JsonObject;
  created_by: string;
  created_at: IsoDateTime;
  updated_at: IsoDateTime;
  last_seen_at: IsoDateTime | null;
}

export interface ConnectorOrganization {
  organization_id: string;
  name: string;
  slug: string;
}

export interface ConnectorOnboarding {
  provider: ConnectorProvider;
  app_configured: boolean;
  embedded_signup_configured: boolean;
  app_id: string | null;
  configuration_id: string | null;
  callback_url: string | null;
  required_server_secrets: string[];
  credential_storage: 'external_secret_manager';
}
