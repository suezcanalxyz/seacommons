import React, { useState } from 'react';
import { fetchJson } from '../services/api/client.js';
import { resolveSiteApiBase } from '../site/liveApi.js';
import { validIMO, validMMSI, vesselFinderEmbedHtml } from './aisCrossCheck.js';

function positionAge(value) {
  const ms = new Date(value).getTime();
  if (!Number.isFinite(ms)) return 'Timestamp unavailable';
  const minutes = Math.max(0, Math.floor((Date.now() - ms) / 60000));
  return minutes < 10 ? 'Recent AIS observation' : minutes < 120 ? 'Last observed, not necessarily current' : 'Historical AIS position';
}

function coordsText(value, positive, negative) {
  if (value === null || value === undefined || value === '' || !Number.isFinite(Number(value))) {
    return 'Unavailable';
  }
  const coordinate = Number(value);
  return Math.abs(coordinate).toFixed(5) + '° ' + (coordinate < 0 ? negative : positive);
}

export default function AisCrossCheck() {
  const [imo, setIMO] = useState('9316359');
  const [mmsi, setMMSI] = useState('636017239');
  const [reference, setReference] = useState(null);
  const [state, setState] = useState({ loading: false, error: '', vessel: null, checkedAt: null });
  const valid = validIMO(imo) || validMMSI(mmsi);

  async function loadComparison(event) {
    event.preventDefault();
    if (!valid) return;
    const id = validIMO(imo) ? imo.trim() : mmsi.trim();
    const selected = { imo: validIMO(imo) ? imo.trim() : '', mmsi: validMMSI(mmsi) ? mmsi.trim() : '' };
    setReference(null);
    setState({ loading: true, error: '', vessel: null, checkedAt: null });
    try {
      const result = await fetchJson(
        resolveSiteApiBase(),
        '/api/v1/vessels/search?q=' + encodeURIComponent(id) + '&active_only=false&limit=25',
        undefined, 12000,
      );
      const vessels = Array.isArray(result.vessels) ? result.vessels : [];
      const vessel = vessels.find((item) =>
        (selected.imo && String(item.imo || '') === selected.imo)
        || (selected.mmsi && String(item.mmsi || '') === selected.mmsi)
      );
      setState({
        loading: false,
        error: vessel ? '' : 'No matching AIS identity is currently stored by SeaCommons.',
        vessel: vessel || null,
        checkedAt: new Date().toISOString(),
      });
    } catch {
      setState({
        loading: false,
        error: 'The authenticated SeaCommons AIS search is unavailable. No position is inferred.',
        vessel: null, checkedAt: null,
      });
    }
    // The external visual check is opt-in and never read back into SeaCommons.
    setReference(selected);
  }

  return (
    <>
      <section className="future-page-head">
        <span className="future-eyebrow">intelligence / external visual reference</span>
        <h1>Compare a vessel’s AIS position.</h1>
        <p>Review SeaCommons’ last directly received AIS fix alongside a separate VesselFinder map. The external map is a visual reference, not an automated verification source or a second independent sensor lineage.</p>
      </section>
      <section className="future-section future-ais-check">
        <form className="future-ais-form" onSubmit={loadComparison} aria-label="Select a vessel for visual comparison">
          <label>IMO<input inputMode="numeric" maxLength={7} placeholder="7-digit IMO" value={imo} onChange={(event) => setIMO(event.target.value)} /></label>
          <label>MMSI<input inputMode="numeric" maxLength={9} placeholder="9-digit MMSI" value={mmsi} onChange={(event) => setMMSI(event.target.value)} /></label>
          <button type="submit" disabled={!valid || state.loading}>{state.loading ? 'Loading SeaCommons…' : 'Load comparison'}</button>
        </form>
        <p className="future-data-provenance">Provide a valid IMO or MMSI. VesselFinder accepts an IMO when both are present. Its own map and AIS timestamps may differ from ours because receiver coverage varies.</p>
        {reference && (
          <div className="future-ais-grid">
            <article className="future-ais-local">
              <span className="future-eyebrow">SeaCommons / canonical AIS registry</span>
              <h3>Last received position</h3>
              {state.vessel ? (
                <>
                  <p><strong>{state.vessel.ship_name || state.vessel.mmsi}</strong> · IMO {state.vessel.imo || 'not reported'} · MMSI {state.vessel.mmsi}</p>
                  <dl>
                    <div><dt>Latitude</dt><dd>{coordsText(state.vessel.lat, 'N', 'S')}</dd></div>
                    <div><dt>Longitude</dt><dd>{coordsText(state.vessel.lon, 'E', 'W')}</dd></div>
                    <div><dt>Speed</dt><dd>{state.vessel.speed_kn ?? 'Unavailable'} kn</dd></div>
                    <div><dt>Course</dt><dd>{state.vessel.course_deg ?? 'Unavailable'}°</dd></div>
                    <div><dt>Observed (UTC)</dt><dd>{state.vessel.last_seen || 'Unavailable'}</dd></div>
                  </dl>
                  <p className="future-ais-freshness">{positionAge(state.vessel.last_seen)}</p>
                </>
              ) : <p role="status">{state.error || 'Loading SeaCommons AIS data…'}</p>}
              <p className="future-data-provenance">Checked: {state.checkedAt ? new Date(state.checkedAt).toLocaleString() : 'Not available'}. This is a point-in-time comparison, not continuously synchronized tracking.</p>
            </article>
            <article className="future-ais-external">
              <span className="future-eyebrow">VesselFinder / third-party map</span>
              <h3>Visual cross-check · last 24h track</h3>
              <iframe
                title="VesselFinder vessel map, visual inspection only"
                sandbox="allow-scripts"
                referrerPolicy="no-referrer"
                loading="lazy"
                srcDoc={vesselFinderEmbedHtml(reference)}
              />
              <p className="future-data-provenance">Official VesselFinder embed. It does not return AIS values to SeaCommons; no scraping, automated comparison or ingestion takes place. If the provider blocks a sandboxed embed, <a href="https://www.vesselfinder.com/it/embed" target="_blank" rel="noopener noreferrer">open VesselFinder’s embed page</a>.</p>
            </article>
          </div>
        )}
      </section>
    </>
  );
}
