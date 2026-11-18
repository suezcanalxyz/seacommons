import React, { useMemo, useState } from 'react';

export default function VesselCaseSearch({ cases, onSelect }) {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const needle = query.trim().toLowerCase().replace(/^(imo|mmsi)\s*[:#-]?\s*/i, '');
  const matches = useMemo(() => {
    if (needle.length < 2) return [];
    return cases.filter((record) => [
      record.title, record.vessel_name, record.ship_name, record.name,
      record.imo, record.mmsi, record.linked_mmsi, record.incident_id,
      ...(Array.isArray(record.subject_ids) ? record.subject_ids : []),
    ].some((value) => String(value ?? '').toLowerCase().includes(needle))).slice(0, 8);
  }, [cases, needle]);

  function select(record) {
    onSelect(record);
    setOpen(false);
  }

  return <form className="vessel-case-search" role="search" aria-label="Vessel case search"
    onSubmit={(event) => { event.preventDefault(); if (matches[0]) select(matches[0]); }}>
    <input type="search" aria-label="Search vessel by IMO, MMSI or name" placeholder="Vessel name, IMO or MMSI"
      value={query} onFocus={() => setOpen(true)} onChange={(event) => { setQuery(event.target.value); setOpen(true); }}
      onKeyDown={(event) => { if (event.key === 'Escape') setOpen(false); }} />
    {open && needle.length >= 2 && (matches.length ? <ul>
      {matches.map((record) => <li key={record.incident_id || record.id}>
        <button type="button" onClick={() => select(record)}>{record.vessel_name || record.ship_name || record.title || record.incident_id}</button>
      </li>)}
    </ul> : <p>No matching case in this view.</p>)}
  </form>;
}
