import { useEffect, useState } from 'react';
import { fetchJson } from '../../services/api/client.js';

const count = new Intl.NumberFormat('en');
const labels = {
  vessel_tracks: 'Vessel track messages',
  source_observations: 'Source observation messages',
  naive: 'Time zone unverified',
  explicit_offset: 'Explicit offset, grouped in UTC',
  missing: 'Missing',
  unparseable: 'Unparseable',
  invalid: 'Invalid',
  zero_or_imputed_missing: 'Stored zero or imputed missing',
  '0_to_1': 'Above 0 to below 1',
  '1_to_5': '1 to below 5',
  '5_to_15': '5 to below 15',
  '15_to_30': '15 to below 30',
  '30_to_60': '30 to below 60',
  '60_or_more_review': '60 or above (review bin)',
};

const histogramOrder = Object.keys(labels);

function isHistogram(value) {
  return value === null || (value && typeof value === 'object' && !Array.isArray(value));
}

function hasCoverage(table) {
  return table && [table.sample_parts, table.total_parts, table.sample_rows].every(Number.isSafeInteger)
    && (table.total_rows === null || Number.isSafeInteger(table.total_rows))
    && isHistogram(table.calendar_months) && isHistogram(table.time_quality);
}

function Histogram({ title, values, calendar = false }) {
  const keys = values && (calendar ? Object.keys(values).sort() : histogramOrder.filter((key) => key in values));
  return (
    <div className="play-analytics__histogram">
      <h4>{title}</h4>
      {values === null ? <p>Withheld under the aggregate privacy threshold.</p> : !keys.length ? <p>No calendar months available.</p> : (
        <dl>
          {keys.map((key) => {
            const [basis, month] = key.split(':');
            return (
              <div key={key}>
                <dt>{calendar ? `${month} · ${labels[basis]}` : labels[key]}</dt>
                <dd>{count.format(values[key])}</dd>
              </div>
            );
          })}
        </dl>
      )}
    </div>
  );
}

export default function PlayAnalytics({ apiBase }) {
  const [result, setResult] = useState(null);
  useEffect(() => {
    let active = true;
    fetchJson(apiBase, '/api/v1/play/analytics', { cache: 'no-store' }, 10_000)
      .then((payload) => {
        if (!active) return;
        setResult(payload?.method === 'historical-observation-profile/v2' &&
          payload.status === 'incomplete' && hasCoverage(payload.tables?.vessel_tracks) &&
          isHistogram(payload.tables.vessel_tracks.reported_sog_knots) &&
          hasCoverage(payload.tables?.source_observations) ? payload : false);
      })
      .catch(() => { if (active) setResult(false); });
    return () => { active = false; };
  }, [apiBase]);

  return (
    <section className="sc-panel-tab-content play-analytics" aria-labelledby="play-analytics-title">
      <h2 id="play-analytics-title">Historical Analytics</h2>
      {result === null && <p role="status">Loading historical sample…</p>}
      {result === false && <p role="status">A reviewed historical sample is currently unavailable.</p>}
      {result && <>
        <p><strong>Incomplete archive coverage.</strong> {result.scope} Archive filters and the timeline do not change this sample.</p>
        <p>{result.limitations}</p>
        {['vessel_tracks', 'source_observations'].map((name) => {
          const table = result.tables[name];
          return (
            <section className="play-analytics__table" key={name}>
              <h3>{labels[name]}</h3>
              <p>{table.total_rows === null ? `${count.format(table.sample_rows)} messages · archive total withheld`
                : `${count.format(table.sample_rows)} of ${count.format(table.total_rows)} messages`}</p>
              <p>{count.format(table.sample_parts)} of {count.format(table.total_parts)} archive objects</p>
              <Histogram title="Timestamp quality" values={table.time_quality} />
              <Histogram title="Calendar month" values={table.calendar_months} calendar />
              {name === 'vessel_tracks' && <Histogram title="Stored speed over ground (knots)" values={table.reported_sog_knots} />}
            </section>
          );
        })}
      </>}
    </section>
  );
}
