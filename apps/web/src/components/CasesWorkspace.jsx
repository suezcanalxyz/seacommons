import React, { useCallback, useEffect, useState } from 'react';

const CASE_TYPES = [
  'distress_sar', 'pushback', 'shipwreck', 'missing_persons',
  'interception', 'vessel_incident', 'monitoring', 'unspecified',
];
const caseTypeLabel = (value) => (value || 'unspecified').replace(/_/g, ' ');

export default function CasesWorkspace({ apiBase, fetchJson, onLocate }) {
  const [cases, setCases] = useState([]);
  const [inbox, setInbox] = useState([]);
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState('');
  const [note, setNote] = useState('');
  const [assignee, setAssignee] = useState('');
  const [busy, setBusy] = useState(false);
  const [typeFilter, setTypeFilter] = useState('');

  const refresh = useCallback(async () => {
    try {
      const casePath = typeFilter
        ? `/api/v1/cases?case_type=${encodeURIComponent(typeFilter)}`
        : '/api/v1/cases';
      const [nextCases, nextInbox] = await Promise.all([
        fetchJson(apiBase, casePath), fetchJson(apiBase, '/api/v1/inbox'),
      ]);
      setCases(nextCases); setInbox(nextInbox); setError('');
    } catch (err) { setError(err.message || 'Case service unavailable'); }
  }, [apiBase, fetchJson, typeFilter]);

  useEffect(() => { refresh(); }, [refresh]);

  async function openCase(caseId) {
    const detail = await fetchJson(apiBase, `/api/v1/cases/${caseId}`);
    setSelected(detail);
    setAssignee(detail.assigned_to || '');
    if (detail.lat != null && detail.lon != null) onLocate(detail.lat, detail.lon);
  }

  async function promote(signal) {
    const title = signal.raw_text?.slice(0, 80) || `Distress signal · ${signal.source_channel}`;
    const created = await fetchJson(apiBase, '/api/v1/cases', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, priority: signal.requires_human_review ? 'high' : 'medium',
        lat: signal.lat, lon: signal.lon, persons: signal.persons, signal_id: signal.signal_id }),
    });
    await refresh(); await openCase(created.case_id);
  }

  async function setStatus(status) {
    const updated = await fetchJson(apiBase, `/api/v1/cases/${selected.case_id}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status }),
    });
    setSelected({ ...selected, ...updated }); await refresh();
  }

  async function setCaseType(caseType) {
    const updated = await fetchJson(apiBase, `/api/v1/cases/${selected.case_id}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ case_type: caseType }),
    });
    setSelected({ ...selected, ...updated }); await refresh();
  }

  async function updateAssignment() {
    const updated = await fetchJson(apiBase, `/api/v1/cases/${selected.case_id}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ assigned_to: assignee }),
    });
    setSelected({ ...selected, ...updated }); await refresh();
  }

  async function addNote(event) {
    event.preventDefault(); if (!note.trim()) return;
    setBusy(true);
    try {
      await fetchJson(apiBase, `/api/v1/cases/${selected.case_id}/timeline`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ event_type: 'note', body: note.trim() }),
      });
      setNote(''); await openCase(selected.case_id);
    } finally { setBusy(false); }
  }

  async function uploadAttachment(event) {
    const file = event.target.files?.[0]; if (!file) return;
    setBusy(true);
    try {
      const body = new FormData(); body.append('file', file);
      const headers = window.__SEACOMMONS_ACCESS_TOKEN__ ? { Authorization: `Bearer ${window.__SEACOMMONS_ACCESS_TOKEN__}` } : {};
      const response = await fetch(`${apiBase}/api/v1/cases/${selected.case_id}/attachments`, { method: 'POST', headers, body });
      if (!response.ok) throw new Error(await response.text());
      await openCase(selected.case_id);
    } catch (err) { setError(err.message || 'Upload failed'); }
    finally { setBusy(false); event.target.value = ''; }
  }

  async function downloadAttachment(item) {
    const headers = window.__SEACOMMONS_ACCESS_TOKEN__ ? { Authorization: `Bearer ${window.__SEACOMMONS_ACCESS_TOKEN__}` } : {};
    const response = await fetch(`${apiBase}/api/v1/cases/${selected.case_id}/attachments/${item.attachment_id}`, { headers });
    if (!response.ok) { setError('Download failed'); return; }
    const url = URL.createObjectURL(await response.blob());
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = item.filename; anchor.click();
    URL.revokeObjectURL(url);
  }

  return <div className="panel-stack case-workspace">
    {error && <div className="demo-note">{error}</div>}
    {selected ? <section className="panel-block case-detail">
      <button className="link-button" onClick={() => setSelected(null)}>← All cases</button>
      <p className="section-kicker">Case / {selected.case_id.slice(0, 8)}</p>
      <h3>{selected.title}</h3>
      <div className="case-meta"><span>{caseTypeLabel(selected.case_type)}</span><span>{selected.priority}</span><span>{selected.status}</span><span>{selected.assigned_to || 'unassigned'}</span></div>
      <p className="panel-copy">{selected.summary || 'No operational summary yet.'}</p>
      <div className="action-row">
        {['triage', 'active', 'monitoring', 'resolved'].map(status =>
          <button key={status} disabled={selected.status === status} onClick={() => setStatus(status)}>{status}</button>)}
      </div>
      <label className="case-type-select">Type
        <select value={selected.case_type || 'unspecified'} onChange={e => setCaseType(e.target.value)}>
          {CASE_TYPES.map(type => <option key={type} value={type}>{caseTypeLabel(type)}</option>)}
        </select>
      </label>
      <div className="case-assignment"><input value={assignee} onChange={e => setAssignee(e.target.value)} placeholder="Operator subject / team"/><button onClick={updateAssignment}>Assign</button></div>
      <form className="case-note" onSubmit={addNote}><textarea value={note} onChange={e => setNote(e.target.value)} placeholder="Add an operational note…" rows="3"/><button disabled={busy || !note.trim()}>Add note</button></form>
      <div className="case-attachments"><div className="panel-title-row"><p className="section-kicker">Attachments · {selected.attachments?.length || 0}</p><label className="upload-button">Add file<input type="file" onChange={uploadAttachment} disabled={busy}/></label></div>
        <ul>{selected.attachments?.map(item => <li key={item.attachment_id}><button onClick={() => downloadAttachment(item)}><span>{item.filename}</span><small>{Math.round(item.size_bytes / 1024)} KB · SHA {item.sha256.slice(0, 8)}</small></button></li>)}</ul>
      </div>
      <p className="section-kicker timeline-kicker">Timeline</p>
      <ul className="case-timeline">{selected.timeline?.map(item => <li key={item.entry_id}>
        <strong>{item.event_type}</strong><span>{item.body}</span><time>{new Date(item.created_at).toLocaleString()}</time>
      </li>)}</ul>
    </section> : <>
      <section className="panel-block">
        <div className="panel-title-row"><div><p className="section-kicker">Operations</p><h3>Cases</h3></div>
          <div className="case-list-controls">
            <select value={typeFilter} onChange={e => setTypeFilter(e.target.value)}>
              <option value="">All types</option>
              {CASE_TYPES.map(type => <option key={type} value={type}>{caseTypeLabel(type)}</option>)}
            </select>
            <button onClick={refresh}>Refresh</button>
          </div>
        </div>
        <ul className="case-list">{cases.map(item => <li key={item.case_id}>
          <button onClick={() => openCase(item.case_id)}><span><strong>{item.title}</strong><small>{caseTypeLabel(item.case_type)} · {item.status} · {item.priority}</small></span><b>›</b></button>
        </li>)}</ul>
      </section>
      <section className="panel-block"><p className="section-kicker">Signal inbox · {inbox.length}</p><h3>Needs triage</h3>
        <ul className="case-list inbox-list">{inbox.map(signal => <li key={signal.signal_id}>
          <div><strong>{signal.source_channel}</strong><p>{signal.raw_text || 'Location share'}</p><small>{signal.lat != null ? `${Number(signal.lat).toFixed(4)}, ${Number(signal.lon).toFixed(4)}` : 'No position'}</small>
          <button onClick={() => promote(signal)}>Create case</button></div>
        </li>)}</ul>
      </section>
    </>}
  </div>;
}
