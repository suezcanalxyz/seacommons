import React, { useEffect, useState } from 'react';
import { fetchJson } from '../../services/api/client.js';
import { resolveSiteApiBase } from '../liveApi.js';

function formatCount(value) {
  if (value == null || value === '') return '—';
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  return new Intl.NumberFormat('en-GB').format(n);
}

export default function OverallCounter() {
  const [play, setPlay] = useState(null);
  const [status, setStatus] = useState('loading');
  const [fetchedAt, setFetchedAt] = useState(null);

  useEffect(() => {
    let cancelled = false;
    const apiBase = resolveSiteApiBase();

    async function refresh() {
      try {
        const next = await fetchJson(apiBase, '/api/v1/play/counts', undefined, 7000);
        if (!cancelled) {
          setPlay(next);
          setStatus('available');
          setFetchedAt(new Date().toISOString());
        }
      } catch {
        if (!cancelled) {
          setPlay(null);
          setStatus('unavailable');
          setFetchedAt(null);
        }
      }
    }

    refresh();
    const timer = window.setInterval(refresh, 60_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  const metrics = [
    ['Overall', play?.total_count],
    ['Humanitarian', play?.humanitarian_count],
    ['Maritime', play?.maritime_count],
    ['Investigations', play?.investigation_count],
  ];

  return (
    <>
    <section className="overall-counter" aria-label="SeaCommons all-time public case totals">
      {metrics.map(([label, value]) => (
        <div className="overall-counter__metric" key={label}>
          <span>{label}</span>
          <strong>{play ? formatCount(value) : status === 'loading' ? '…' : '—'}</strong>
        </div>
      ))}
    </section>
    <p className="overall-counter__context" role="status">
      Public archive records / not verified outcomes.
      {' '}{status === 'loading' ? 'Loading totals.' : status === 'unavailable' ? 'Totals currently unavailable.' : `Retrieved ${fetchedAt.slice(11, 19)} UTC.`}
      {' '}<a href="/status">Source status ↗</a>
    </p>
    </>
  );
}
