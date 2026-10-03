import { useEffect, useRef, useState } from 'react';
import { workspaceApi } from './api.js';
import { usePartner } from './PartnerGate.jsx';

const NAV = ['Overview', 'Documents', 'Analysis', 'Workflow', 'Milestones'];
const KINDS = { Documents: ['document', 'deck'], Analysis: ['analysis'], Workflow: ['workflow'], Milestones: ['milestone'] };
const STATUSES = ['draft', 'planned', 'in_progress', 'blocked', 'complete', 'archived'];
const label = (value) => value.replaceAll('_', ' ');
const blank = (section) => ({ kind: KINDS[section]?.[0] || 'document', title: '', body: '', status: 'draft', owner: '', due_on: '' });

function TextContent({ body }) {
  // React escapes text. HTML and scripts in imported documents never execute.
  return <div className="workspace-document">{body.split('\n').map((line, index) => {
    if (line.startsWith('# ')) return <h2 key={index}>{line.slice(2)}</h2>;
    if (line.startsWith('## ')) return <h3 key={index}>{line.slice(3)}</h3>;
    if (line.startsWith('### ')) return <h4 key={index}>{line.slice(4)}</h4>;
    if (line.startsWith('- ')) return <p className="workspace-document__bullet" key={index}>• {line.slice(2)}</p>;
    return <p key={index}>{line || '\u00a0'}</p>;
  })}</div>;
}

function Deck({ body }) {
  const slides = body.split(/^---\s*$/m).filter((slide) => slide.trim());
  const [index, setIndex] = useState(0);
  return <div className="workspace-deck">
    <div className="workspace-deck__controls"><button disabled={index === 0} onClick={() => setIndex(index - 1)}>← Previous</button><span>{index + 1} / {slides.length}</span><button disabled={index >= slides.length - 1} onClick={() => setIndex(index + 1)}>Next →</button></div>
    <article className="workspace-deck__slide"><TextContent body={slides[index] || ''} /></article>
  </div>;
}

export default function Workspace() {
  const partner = usePartner();
  const [section, setSection] = useState('Overview');
  const [items, setItems] = useState([]);
  const [hasMore, setHasMore] = useState(false);
  const [selected, setSelected] = useState(null);
  const [history, setHistory] = useState(null);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState(blank('Documents'));
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [mobileMenu, setMobileMenu] = useState(false);
  const request = useRef(0);

  async function handleError(err) {
    if (err.status === 401 || err.status === 403) { await partner.signOut(); return; }
    setError(err.message);
  }

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    workspaceApi('/records?limit=200', partner.token, { signal: controller.signal }).then((data) => {
      setItems(data.items); setHasMore(data.has_more); setError('');
    }).catch((err) => { if (err.name !== 'AbortError') setError(err.message); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [partner.token]);

  async function loadMore() {
    setError('');
    try {
      const data = await workspaceApi(`/records?limit=200&offset=${items.length}`, partner.token);
      setItems((current) => [...current, ...data.items]); setHasMore(data.has_more);
    } catch (err) { await handleError(err); }
  }

  async function open(item) {
    const id = ++request.current;
    setError(''); setHistory(null); setSelected(null); setLoading(true);
    try {
      const data = await workspaceApi(`/records/${item.id}`, partner.token);
      if (id === request.current) setSelected(data);
    } catch (err) { if (id === request.current) await handleError(err); }
    finally { if (id === request.current) setLoading(false); }
  }

  function navigate(next) {
    request.current += 1; setSection(next); setSelected(null); setEditing(false); setHistory(null);
    setSearch(''); setMobileMenu(false); setError(''); setLoading(false);
  }

  async function save(event) {
    event.preventDefault(); setSaving(true); setError('');
    try {
      const data = await workspaceApi(selected ? `/records/${selected.id}` : '/records', partner.token, {
        method: selected ? 'PUT' : 'POST', body: { ...form, due_on: form.due_on || null, ...(selected ? { version: selected.version } : {}) },
      });
      setItems((current) => [data, ...current.filter((item) => item.id !== data.id)]);
      setSelected(data); setEditing(false); setHistory(null);
    } catch (err) { await handleError(err); } finally { setSaving(false); }
  }

  async function importText(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (file.size > 200_000 || !/\.(md|txt)$/i.test(file.name)) { setError('Choose a Markdown or text file under 200 KB.'); return; }
    const body = await file.text();
    setForm((current) => ({ ...current, body, title: current.title || file.name.replace(/\.(md|txt)$/i, '') }));
  }

  async function showHistory() {
    setError('');
    try { const data = await workspaceApi(`/records/${selected.id}/history`, partner.token); setHistory(data.items); }
    catch (err) { await handleError(err); }
  }

  const visible = items.filter((item) => (section === 'Overview' || KINDS[section].includes(item.kind))
    && `${item.title} ${item.owner}`.toLowerCase().includes(search.toLowerCase()));
  const active = items.filter((item) => !['complete', 'archived'].includes(item.status));
  const upcoming = active.filter((item) => item.due_on).sort((a, b) => a.due_on.localeCompare(b.due_on));

  return <div className="partner-shell">
    <aside className={`partner-sidebar${mobileMenu ? ' is-open' : ''}`}>
      <a className="partner-brand" href="/site.html">SEA COMMONS</a>
      <p className="partner-sidebar__caption">Partner workspace</p>
      <button className="partner-menu" onClick={() => setMobileMenu(false)}>Close menu</button>
      <nav aria-label="Workspace">{NAV.map((name) => <button key={name} className={section === name ? 'is-active' : ''} aria-current={section === name ? 'page' : undefined} onClick={() => navigate(name)}>{name}</button>)}</nav>
      <div className="partner-sidebar__base"><span>{partner.email}</span><small>{partner.role}</small><button onClick={partner.signOut}>Sign out</button><a href="/docs">Public documentation ↗</a></div>
    </aside>
    <main className="partner-main">
      <header className="partner-topbar"><button className="partner-menu" aria-label="Toggle workspace navigation" aria-expanded={mobileMenu} onClick={() => setMobileMenu(!mobileMenu)}>☰</button><span>{partner.organization_id}</span><span>Private workspace</span></header>
      <div className="partner-page">
        <div className="partner-page__heading"><div><p className="partner-eyebrow">SeaCommons / {section}</p><h1>{editing ? selected ? 'Edit record' : 'New record' : selected?.title || section}</h1></div>{partner.can_edit && !selected && !editing && <button className="partner-primary" onClick={() => { setForm(blank(section)); setEditing(true); }}>+ New record</button>}</div>
        {error && <div className="partner-error" role="alert">{error}{selected && <button onClick={() => { setEditing(false); open(selected); }}>Reload record</button>}</div>}
        {editing ? <form className="workspace-editor" onSubmit={save}>
          <label>Title<input required maxLength={200} value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} /></label>
          <div className="workspace-editor__meta"><label>Type<select value={form.kind} onChange={(event) => setForm({ ...form, kind: event.target.value })}>{['document', 'deck', 'analysis', 'workflow', 'milestone'].map((kind) => <option key={kind}>{kind}</option>)}</select></label><label>Status<select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value })}>{STATUSES.map((status) => <option key={status} value={status}>{label(status)}</option>)}</select></label><label>Owner<input maxLength={200} value={form.owner} onChange={(event) => setForm({ ...form, owner: event.target.value })} /></label><label>Due date<input type="date" value={form.due_on} onChange={(event) => setForm({ ...form, due_on: event.target.value })} /></label></div>
          <label>Content<textarea rows={18} maxLength={200_000} value={form.body} onChange={(event) => setForm({ ...form, body: event.target.value })} /></label>
          <p className="partner-muted">Use Markdown headings. For decks, separate slides with a line containing ---.</p>
          <label className="workspace-import">Import Markdown / text<input type="file" accept=".md,.txt" onChange={importText} /></label>
          <div className="workspace-actions"><button className="partner-primary" disabled={saving}>{saving ? 'Saving…' : 'Save record'}</button><button type="button" disabled={saving} onClick={() => setEditing(false)}>Cancel</button></div>
        </form> : selected ? <>
          <div className="workspace-actions"><button onClick={() => setSelected(null)}>← Back to {section}</button>{partner.can_edit && <button onClick={() => { setForm({ ...selected, due_on: selected.due_on || '' }); setEditing(true); }}>Edit</button>}<button onClick={showHistory}>History</button></div>
          <div className="workspace-meta"><span>{selected.kind}</span><span>{label(selected.status)}</span>{selected.owner && <span>Owner: {selected.owner}</span>}{selected.due_on && <span>Due: {selected.due_on}</span>}<span>Version {selected.version}</span></div>
          {selected.kind === 'deck' ? <Deck key={`${selected.id}-${selected.version}`} body={selected.body} /> : <TextContent body={selected.body} />}
          {history && <section className="workspace-history"><h2>Revision history</h2>{history.map((entry) => <details key={entry.version}><summary>Version {entry.version} / {entry.timestamp}</summary><TextContent body={entry.snapshot.body} /></details>)}</section>}
        </> : <>
          {section === 'Overview' && <div className="workspace-overview"><section><h2>Delivery</h2><p>{active.length} active records in the loaded workspace.</p><ul>{upcoming.slice(0, 5).map((item) => <li key={item.id}><button onClick={() => open(item)}>{item.title}</button><time dateTime={item.due_on}>{item.due_on}</time></li>)}</ul>{!upcoming.length && <p className="partner-muted">No scheduled deadlines yet.</p>}</section><section><h2>Working together</h2><p>Use Documents for decks and references, Analysis for research notes, Workflow for ongoing steps and Milestones for delivery dates.</p><a href="/docs">Open-source project documentation ↗</a></section></div>}
          <div className="workspace-list__head"><h2>{section === 'Overview' ? 'Recently updated' : section}</h2><label><span className="sr-only">Search records</span><input placeholder="Search title or owner" value={search} onChange={(event) => setSearch(event.target.value)} /></label></div>
          {loading ? <p role="status">Loading workspace…</p> : !visible.length ? <div className="workspace-empty"><h3>{search ? 'No matching records' : 'No records yet'}</h3><p>{search ? 'Try another title or owner.' : partner.can_edit ? 'Create a record or import a Markdown document to begin.' : 'Your team has not shared any records here yet.'}</p></div> : <div className="workspace-list">{visible.map((item) => <button className="workspace-row" key={item.id} onClick={() => open(item)}><span><strong>{item.title}</strong><small>{item.kind}{item.owner ? ` / ${item.owner}` : ''}</small></span><span>{label(item.status)}</span><time>{item.due_on || item.updated_at.slice(0, 10)}</time><span aria-hidden="true">→</span></button>)}</div>}
          {hasMore && <button className="workspace-more" onClick={loadMore}>Load more records</button>}
        </>}
      </div>
    </main>
  </div>;
}
