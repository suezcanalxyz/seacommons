import React, { useEffect, useState } from 'react';
import { fetchJson } from '../services/api/client.js';

const PAGE = 50;

/** Source-listed vessel identities are visible even with no recent AIS fix. */
export default function SanctionsCatalog({ apiBase }) {
  const [search, setSearch] = useState('');
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState({ entries: [], total: 0, has_more: false });
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    setError('');
    const path = `/api/v1/live/sanctioned-catalog?limit=${PAGE}&offset=${offset}&search=${encodeURIComponent(search)}`;
    fetchJson(apiBase, path, undefined, 15000)
      .then((result) => { if (active) setData(result); })
      .catch(() => { if (active) setError('Sanctions catalog unavailable'); });
    return () => { active = false; };
  }, [apiBase, offset, search]);
  return (
    <section className="sanctions-catalog" aria-label="Sanctioned vessel reference catalog">
      <div className="sanctions-catalog__intro"><strong>Sanctions registry</strong><span>{data.total} listed entries</span></div>
      <p>Listed identities, independently of current AIS reception. No location is inferred from a listing.</p>
      <input aria-label="Search sanctioned vessels" placeholder="Search name, IMO, MMSI or program" value={search} onChange={(e) => { setOffset(0); setSelected(null); setSearch(e.target.value); }} />
      {error && <p role="status">{error}</p>}
      {data.entries?.length === 0 && !error && <p>No entries available. Source ingestion may need attention.</p>}
      <ul className="sanctions-catalog__list">
        {(data.entries || []).map((entry) => (
          <li key={entry.id}>
            <button type="button" onClick={() => setSelected(selected?.id === entry.id ? null : entry)} aria-expanded={selected?.id === entry.id}>
              <strong>{entry.name || entry.imo || entry.mmsi || 'Unnamed vessel'}</strong>
              <small>{entry.source_list}{entry.program ? ` · ${entry.program}` : ''}</small>
            </button>
            {selected?.id === entry.id && <div className="sanctions-catalog__details">
              <p>IMO: {entry.imo || 'Not recorded'} · MMSI: {entry.mmsi || 'Not recorded'}</p>
              <p>Source: {entry.source_list} · Listed/first observed: {entry.listed_on || 'Not recorded'}</p>
              <p>Sanctions program: {entry.program || 'Not recorded'}</p>
              <p>Detailed designation grounds: not yet verified from the primary notice. Listing alone does not establish illegal behaviour.</p>
            </div>}
          </li>
        ))}
      </ul>
      <div className="sanctions-catalog__pager">
        <button type="button" disabled={!offset} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</button>
        <span>{data.total ? `${offset + 1}–${Math.min(offset + PAGE, data.total)} of ${data.total}` : '0 entries'}</span>
        <button type="button" disabled={!data.has_more} onClick={() => { setOffset(offset + PAGE); setSelected(null); }}>Next</button>
      </div>
    </section>
  );
}
