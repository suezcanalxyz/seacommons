import React, { useEffect, useMemo, useState } from 'react';

const EMPTY_FORM = {
  organization_id: '',
  display_name: '',
  external_account_id: '',
  external_channel_id: '',
  display_address: '',
  secret_ref: '',
};

function shortDate(value) {
  if (!value) return 'never';
  return new Date(value).toLocaleString('en-GB', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function errorMessage(error) {
  const raw = error?.message || 'Connector request failed';
  try {
    const parsed = JSON.parse(raw);
    return parsed.detail || raw;
  } catch {
    return raw;
  }
}

export default function ConnectorWorkspace({ apiBase, fetchJson }) {
  const [connectors, setConnectors] = useState([]);
  const [organizations, setOrganizations] = useState([]);
  const [onboarding, setOnboarding] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');

  async function refresh() {
    try {
      const [items, setup, orgs] = await Promise.all([
        fetchJson(apiBase, '/api/v1/connectors'),
        fetchJson(apiBase, '/api/v1/connectors/onboarding'),
        fetchJson(apiBase, '/api/v1/connectors/organizations'),
      ]);
      setConnectors(items);
      setOnboarding(setup);
      setOrganizations(orgs);
      setForm((current) => ({
        ...current,
        organization_id: current.organization_id || orgs[0]?.organization_id || '',
      }));
      setError('');
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  useEffect(() => { refresh(); }, [apiBase]);

  const counts = useMemo(() => connectors.reduce((result, item) => ({
    ...result,
    [item.status]: (result[item.status] || 0) + 1,
  }), {}), [connectors]);

  async function create(event) {
    event.preventDefault();
    setBusy('create');
    setError('');
    try {
      await fetchJson(apiBase, '/api/v1/connectors', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...form,
          external_account_id: form.external_account_id || null,
          display_address: form.display_address || null,
          secret_ref: form.secret_ref || null,
        }),
      });
      setForm((current) => ({ ...EMPTY_FORM, organization_id: current.organization_id }));
      await refresh();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy('');
    }
  }

  async function setStatus(connector, status) {
    setBusy(connector.connector_id);
    setError('');
    try {
      await fetchJson(apiBase, `/api/v1/connectors/${connector.connector_id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status }),
      });
      await refresh();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy('');
    }
  }

  return (
    <section className="panel-block connector-workspace">
      <div className="connector-heading">
        <div>
          <p className="section-kicker">Partner channels</p>
          <h3>WhatsApp Cloud connectors</h3>
        </div>
        <button type="button" className="link-button" onClick={refresh}>Refresh</button>
      </div>

      <p className="panel-copy">
        Connect numbers owned by participating organisations. SeaCommons does not pair a personal
        WhatsApp account and never stores access tokens in this interface.
      </p>

      <div className="connector-readiness">
        <div>
          <span>Meta application</span>
          <strong className={onboarding?.app_configured ? 'is-ready' : ''}>
            {onboarding?.app_configured ? 'READY' : 'KEYS REQUIRED'}
          </strong>
        </div>
        <div>
          <span>Embedded Signup</span>
          <strong className={onboarding?.embedded_signup_configured ? 'is-ready' : ''}>
            {onboarding?.embedded_signup_configured ? 'READY' : 'NOT CONFIGURED'}
          </strong>
        </div>
        <div>
          <span>Active / pending</span>
          <strong>{counts.active || 0} / {counts.pending || 0}</strong>
        </div>
      </div>

      {onboarding?.callback_url ? (
        <div className="connector-callback">
          <span>Meta callback URL</span>
          <code>{onboarding.callback_url}</code>
        </div>
      ) : null}
      {error ? <div className="demo-note connector-error" role="alert">{error}</div> : null}

      <form onSubmit={create} className="connector-form">
        <label className="field-block">
          Organisation
          <select
            required
            value={form.organization_id}
            onChange={(event) => setForm({ ...form, organization_id: event.target.value })}
          >
            <option value="">Select organisation</option>
            {organizations.map((org) => (
              <option key={org.organization_id} value={org.organization_id}>{org.name}</option>
            ))}
          </select>
        </label>
        <label className="field-block">
          Connector name
          <input
            required
            value={form.display_name}
            onChange={(event) => setForm({ ...form, display_name: event.target.value })}
            placeholder="Alarm Phone Italy"
          />
        </label>
        <label className="field-block">
          WhatsApp Business Account ID
          <input
            value={form.external_account_id}
            onChange={(event) => setForm({ ...form, external_account_id: event.target.value })}
            placeholder="WABA ID"
          />
        </label>
        <label className="field-block">
          Phone number ID
          <input
            required
            value={form.external_channel_id}
            onChange={(event) => setForm({ ...form, external_channel_id: event.target.value })}
            placeholder="Meta phone_number_id"
          />
        </label>
        <label className="field-block">
          Display number
          <input
            value={form.display_address}
            onChange={(event) => setForm({ ...form, display_address: event.target.value })}
            placeholder="+39 …"
          />
        </label>
        <label className="field-block">
          Secret reference
          <input
            value={form.secret_ref}
            onChange={(event) => setForm({ ...form, secret_ref: event.target.value })}
            placeholder="oracle/seacommons/connectors/partner"
          />
        </label>
        <div className="action-row connector-submit">
          <button disabled={busy === 'create' || !organizations.length}>
            {busy === 'create' ? 'Creating…' : 'Create pending connector'}
          </button>
        </div>
      </form>

      <ul className="connector-list">
        {connectors.map((connector) => (
          <li key={connector.connector_id}>
            <div className="connector-state">
              <i className={`is-${connector.status}`} />
              <span>{connector.status}</span>
            </div>
            <div className="connector-identity">
              <strong>{connector.display_name}</strong>
              <span>{connector.display_address || connector.external_channel_id}</span>
              <small>Last inbound: {shortDate(connector.last_seen_at)}</small>
            </div>
            <div className="connector-meta">
              <span>{connector.credentials_configured ? 'Secret linked' : 'Secret missing'}</span>
              <code>{connector.external_channel_id}</code>
            </div>
            <div className="action-row">
              {connector.status === 'active' ? (
                <button type="button" disabled={busy === connector.connector_id} onClick={() => setStatus(connector, 'paused')}>Pause</button>
              ) : (
                <button type="button" disabled={busy === connector.connector_id} onClick={() => setStatus(connector, 'active')}>Activate</button>
              )}
            </div>
          </li>
        ))}
        {!connectors.length ? (
          <li className="connector-empty">No partner number is connected yet.</li>
        ) : null}
      </ul>
    </section>
  );
}
