import React, { useEffect, useState } from 'react';
import { fetchJson } from '../../services/api/client.js';
import { resolveSiteApiBase } from '../liveApi.js';

function formatCount(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  return new Intl.NumberFormat('en-GB').format(n);
}

export default function OverallCounter() {
  const [overall, setOverall] = useState(null);

  useEffect(() => {
    let cancelled = false;
    const apiBase = resolveSiteApiBase();

    async function refresh() {
      try {
        const next = await fetchJson(apiBase, '/api/v1/play/overall', undefined, 15_000);
        if (!cancelled) setOverall(next);
      } catch {
        if (!cancelled) setOverall(null);
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
    ['Observations', overall?.observations],
    ['Events', overall?.events],
    ['Episodes', overall?.episodes],
    ['Investigations', overall?.investigations],
  ];

  return (
    <section className="overall-counter" aria-label="SeaCommons all-time overall corpus totals">
      {metrics.map(([label, value]) => (
        <div className="overall-counter__metric" key={label}>
          <span>{label}</span>
          <strong>{overall ? formatCount(value) : '…'}</strong>
        </div>
      ))}
    </section>
  );
}
