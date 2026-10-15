import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { fetchJson } from '../services/api/client.js';
import { resolveSiteApiBase } from '../site/liveApi.js';
import { validIMO, validMMSI, vesselFinderEmbedHtml } from './aisCrossCheck.js';
import {
  aisFreshness, caseIdentity, caseKey, coordsText, renderTime, reviewableCases,
} from './aisCaseReview.js';

const API_BASE = '/api/v1/operator/ais-reviews';
const EMPTY_REVIEW = { verdict: '', position_check: '', explanation: '' };

function LiveCasesMap({ cases, selectedId, onSelect }) {
  const elementRef = useRef(null);
  const mapRef = useRef(null);
  const pinsRef = useRef(null);
  const leafletRef = useRef(null);
  const selectedCallback = useRef(onSelect);
  const fitted = useRef(false);
  const [ready, setReady] = useState(false);
  selectedCallback.current = onSelect;

  useEffect(() => {
    let disposed = false;
    (async () => {
      const [module] = await Promise.all([import('leaflet'), import('leaflet/dist/leaflet.css')]);
      if (disposed || !elementRef.current) return;
      const L = module.default;
      leafletRef.current = L;
      const map = L.map(elementRef.current, {
        center: [36.4, 14.2], zoom: 5, minZoom: 3, maxZoom: 15,
        zoomControl: true, scrollWheelZoom: true,
      });
      L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
        maxZoom: 19,
      }).addTo(map);
      mapRef.current = map;
      pinsRef.current = L.layerGroup().addTo(map);
      setReady(true);
    })().catch(() => setReady(false));
    return () => {
      disposed = true;
      mapRef.current?.remove();
      mapRef.current = null;
      leafletRef.current = null;
      pinsRef.current = null;
    };
  }, []);

  useEffect(() => {
    const L = leafletRef.current;
    if (!ready || !L || !mapRef.current || !pinsRef.current) return;
    pinsRef.current.clearLayers();
    const bounds = [];
    for (const feature of cases) {
      const [lon, lat] = feature.geometry.coordinates.map(Number);
      const id = caseKey(feature);
      const selected = id === selectedId;
      const pin = L.circleMarker([lat, lon], {
        radius: selected ? 10 : 6,
        weight: selected ? 3 : 1.5,
        color: selected ? '#99d8cf' : '#d7b568',
        fillColor: selected ? '#99d8cf' : '#e0a449',
        fillOpacity: selected ? 0.94 : 0.72,
      }).on('click', () => selectedCallback.current(feature));
      pin.bindTooltip(String(feature.properties?.title || 'Maritime case').slice(0, 120), { direction: 'top' });
      pinsRef.current.addLayer(pin);
      bounds.push([lat, lon]);
    }
    if (bounds.length && !fitted.current) {
      fitted.current = true;
      mapRef.current.fitBounds(bounds, { padding: [30, 30], maxZoom: 7 });
    }
  }, [ready, cases, selectedId]);

  useEffect(() => {
    const map = mapRef.current;
    const target = cases.find((item) => caseKey(item) === selectedId);
    if (!ready || !map || !target) return;
    const [lon, lat] = target.geometry.coordinates.map(Number);
    map.flyTo([lat, lon], Math.max(8, map.getZoom()), { duration: 0.5 });
  }, [ready, selectedId, cases]);

  return <div ref={elementRef} className="future-ais-live-map" role="application" aria-label="SeaCommons Live maritime cases map" />;
}

function ReviewForm({ selected, checked, reviewHistory, onSaved }) {
  const [review, setReview] = useState(EMPTY_REVIEW);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    setReview(EMPTY_REVIEW);
    setMessage('');
  }, [selected]);

  const submit = async (event) => {
    event.preventDefault();
    if (!selected || !review.verdict || !review.position_check || review.explanation.trim().length < 20) return;
    setBusy(true);
    setMessage('');
    try {
      await fetchJson(resolveSiteApiBase(), API_BASE, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          case_id: selected,
          verdict: review.verdict,
          position_check: review.position_check,
          explanation: review.explanation.trim(),
          external_visual_reference_checked: checked,
        }),
      });
      setMessage('Review saved. This annotation does not retrain or automatically reclassify the case.');
      onSaved();
    } catch (error) {
      const detail = String(error?.message || '');
      setMessage(detail.includes('403') || detail.includes('503')
        ? 'Reviewer write access is not enabled for this account. Ask an administrator to configure the approved reviewer list.'
        : detail.includes('409')
          ? 'This case left the current Live window. Refresh and select an eligible case.'
          : 'Review could not be saved. Nothing was submitted to the evaluation dataset.');
    } finally {
      setBusy(false);
    }
  };

  return <section className="future-ais-review" aria-label="Human evidence review">
    <h3>Human assessment</h3>
    <p>Evaluate whether the *reasoning* is supported, separately from whether the AIS positions agree. A visual map alone does not verify intent, vessel behaviour or independent corroboration.</p>
    <form onSubmit={submit}>
      <fieldset disabled={!selected || busy}>
        <legend>Evidence assessment</legend>
        <div className="future-ais-choices">
          {[['supported','Supported'],['false_positive','False positive'],['inconclusive','Inconclusive']].map(([value,label])=>
            <label key={value} className={review.verdict===value?'is-active':''}>
              <input type="radio" name="ais-verdict" value={value} checked={review.verdict===value}
                onChange={()=>setReview(old=>({...old,verdict:value}))} />{label}
            </label>
          )}
        </div>
      </fieldset>
      <fieldset disabled={!selected || busy}>
        <legend>Position comparison</legend>
        <div className="future-ais-choices">
          {[['consistent','Consistent'],['inconsistent','Mismatch'],['unavailable','Cannot determine']].map(([value,label])=>
            <label key={value} className={review.position_check===value?'is-active':''}>
              <input type="radio" name="ais-position" value={value} checked={review.position_check===value}
                onChange={()=>setReview(old=>({...old,position_check:value}))} />{label}
            </label>
          )}
        </div>
      </fieldset>
      <label className="future-ais-reason">Reasoning and observations
        <textarea required minLength={20} maxLength={2000} rows={3}
          placeholder="Explain what was observed, the source timestamps, alternative explanations and why the assessment is justified."
          value={review.explanation} disabled={!selected || busy}
          onChange={(event)=>setReview(old=>({...old,explanation:event.target.value}))} />
      </label>
      <div className="future-ais-review-actions">
        <button type="submit" disabled={!selected || busy || !review.verdict || !review.position_check || review.explanation.trim().length < 20}>
          {busy ? 'Saving…' : 'Save evidence review'}
        </button>
        <small>Append-only · reviewer identity verified · not automatic training</small>
      </div>
      {message && <p role="status" className="future-ais-save-message">{message}</p>}
    </form>
    {reviewHistory.length > 0 && <details className="future-ais-review-history">
      <summary>{reviewHistory.length} recorded review(s)</summary>
      {reviewHistory.map((item)=><article key={item.review_id}>
        <strong>{item.verdict.replaceAll('_',' ')} / {item.position_check}</strong>
        <small>{renderTime(item.created_at)}</small><p>{item.explanation}</p>
      </article>)}
    </details>}
  </section>;
}

export default function AisCrossCheck() {
  const [feed, setFeed] = useState({ features: [], fetchedAt: null, error: '', loading: true });
  const [filter, setFilter] = useState('');
  const [selectedId, setSelectedId] = useState('');
  const [manualIdentifier, setManualIdentifier] = useState('');
  const [manualSelection, setManualSelection] = useState(null);
  const [ais, setAIS] = useState({ loading: false, vessel: null, error: '' });
  const [history, setHistory] = useState([]);
  const [historyError, setHistoryError] = useState('');
  const [checkedExternal, setCheckedExternal] = useState(false);
  const [embedCycle, setEmbedCycle] = useState(0);
  const known = useMemo(() => reviewableCases(feed.features), [feed.features]);
  const selected = useMemo(() => known.find((c) => caseKey(c) === selectedId) || null, [known, selectedId]);
  const identity = selected ? caseIdentity(selected) : manualSelection;
  const externalKey = identity && (identity.imo || identity.mmsi);
  const selectedCoords = selected?.geometry?.coordinates;

  const refresh = useCallback(async (quiet = false) => {
    if (!quiet) setFeed((old) => ({...old, loading: true}));
    try {
      const result = await fetchJson(resolveSiteApiBase(), '/api/v1/live/signals?limit=500&days=7&mode=maritime', undefined, 18000);
      const features = Array.isArray(result.features) ? result.features : [];
      setFeed({ features, fetchedAt: new Date().toISOString(), loading: false, error: '' });
    } catch {
      setFeed((old) => ({
        ...old, loading: false,
        error: 'Live is unreachable. Previous positions are historical until connectivity recovers.',
      }));
    }
  }, []);

  useEffect(() => {
    let alive = true;
    const tick = () => { if (alive && document.visibilityState === 'visible') refresh(true); };
    refresh();
    const timer = window.setInterval(tick, 15000);
    document.addEventListener('visibilitychange', tick);
    return () => {
      alive = false;
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', tick);
    };
  }, [refresh]);

  const chooseCase = useCallback((feature) => {
    setSelectedId(caseKey(feature));
    setManualSelection(null);
    setCheckedExternal(false);
  }, []);

  useEffect(() => {
    if (!identity?.imo && !identity?.mmsi) { setAIS({loading:false,vessel:null,error:''}); return; }
    let active = true;
    async function check() {
      const id = identity.imo || identity.mmsi;
      setAIS((old) => ({...old,loading:true}));
      try {
        const data = await fetchJson(resolveSiteApiBase(), '/api/v1/vessels/search?q=' +
          encodeURIComponent(id) + '&active_only=false&limit=30', undefined, 12000);
        const vessels = Array.isArray(data.vessels) ? data.vessels : [];
        const vessel = vessels.find((item) => String(item.imo || '') === identity.imo
          || String(item.mmsi || '') === identity.mmsi);
        if (active) setAIS({loading:false,vessel:vessel || null,error:vessel?'':'No AIS registry match for this vessel.'});
      } catch {
        if (active) setAIS({loading:false,vessel:null,error:'SeaCommons AIS registry temporarily unavailable.'});
      }
    }
    check();
    const interval = window.setInterval(check, 30000);
    return () => { active = false; window.clearInterval(interval); };
  }, [identity?.imo, identity?.mmsi]);

  const reloadHistory = useCallback(async (id) => {
    if (!id) { setHistory([]); setHistoryError(''); return; }
    try {
      const data = await fetchJson(resolveSiteApiBase(), API_BASE + '?case_id=' + encodeURIComponent(id));
      setHistory(Array.isArray(data.reviews) ? data.reviews : []);
      setHistoryError('');
    } catch {
      setHistory([]);
      setHistoryError('Human-review history requires an approved reviewer account.');
    }
  }, []);

  useEffect(() => { reloadHistory(selectedId); }, [selectedId, reloadHistory]);

  const filtered = useMemo(() => {
    const query = filter.trim().toLowerCase();
    return known.filter((caseItem) => {
      if (!query) return true;
      const p = caseItem.properties || {};
      const id = caseIdentity(caseItem);
      return [p.title, p.anomaly_type, id.imo, id.mmsi].some((value) =>
        String(value || '').toLowerCase().includes(query));
    });
  }, [known, filter]);

  const selectByIdentifier = (event) => {
    event.preventDefault();
    const value = manualIdentifier.trim();
    if (!validIMO(value) && !validMMSI(value)) return;
    const match = known.find((item) => {
      const id = caseIdentity(item);
      return id.imo === value || id.mmsi === value;
    });
    if (match) chooseCase(match);
    else {
      setSelectedId('');
      setManualSelection({ imo: validIMO(value) ? value : '', mmsi: validMMSI(value) ? value : '' });
      setCheckedExternal(false);
    }
  };

  return <div className="future-ais-workspace">
    <header className="future-ais-heading">
      <div><span className="future-eyebrow">intelligence / human-in-the-loop / manual verification</span>
        <h1>AIS cross-check.</h1>
        <p>SeaCommons Live on the left, VesselFinder on the right. Selecting a case focuses both maps on its vessel. Only positions received by SeaCommons are stored as AIS evidence.</p>
      </div>
      <div className="future-ais-feed-status" role="status">
        <span className={feed.error ? 'is-stale' : 'is-fresh'}>{feed.error ? 'Feed delayed' : feed.loading ? 'Connecting' : 'Live feed'}</span>
        <small>{feed.fetchedAt ? 'Fetched '+renderTime(feed.fetchedAt) : 'Not yet received'}</small>
        <button type="button" onClick={() => refresh()}>Refresh Live</button>
      </div>
    </header>
    <div className="future-ais-split">
      <section className="future-ais-live" aria-label="SeaCommons Live cases">
        <div className="future-ais-split-title"><div><span className="future-eyebrow">01 / SeaCommons</span><h2>Live cases</h2></div><strong>{known.length}</strong></div>
        <LiveCasesMap cases={filtered} selectedId={selectedId} onSelect={chooseCase} />
        <div className="future-ais-case-filter">
          <label>Find a case<input aria-label="Search Live cases" placeholder="Ship, IMO, MMSI or anomaly" value={filter} onChange={event=>setFilter(event.target.value)} /></label>
        </div>
        {feed.error && <p role="alert" className="future-ais-notice">{feed.error}</p>}
        <div className="future-ais-case-list" aria-label="Select maritime case">
          {filtered.map((feature) => {
            const p = feature.properties || {};
            const id = caseKey(feature);
            const ship = caseIdentity(feature);
            return <button type="button" key={id} className={id===selectedId?'is-active':''} onClick={()=>chooseCase(feature)}
              aria-pressed={id===selectedId}>
              <span className="future-ais-case-meta">{p.anomaly_type || p.episode_family || 'Maritime case'} <i>{renderTime(p.timestamp_utc)}</i></span>
              <strong>{p.title || id}</strong>
              <small>{ship.imo ? 'IMO '+ship.imo : ''} {ship.mmsi ? '· MMSI '+ship.mmsi : ''}</small>
            </button>;
          })}
          {!filtered.length && <p className="future-ais-notice">{feed.loading ? 'Loading maritime cases…' : 'No vessel-linked cases match this search.'}</p>}
        </div>
      </section>
      <section className="future-ais-provider" aria-label="VesselFinder visual reference">
        <div className="future-ais-split-title">
          <div><span className="future-eyebrow">02 / independent visual reference</span><h2>VesselFinder</h2></div>
          <button type="button" onClick={()=>setEmbedCycle(v=>v+1)} disabled={!externalKey}>Reload map</button>
        </div>
        {identity && externalKey ? (
          <iframe key={externalKey + ':' + embedCycle} title="VesselFinder vessel map, visual inspection only"
            sandbox="allow-scripts" referrerPolicy="no-referrer" loading="eager"
            srcDoc={vesselFinderEmbedHtml(identity)} />
        ) : <div className="future-ais-blank">Select a case or enter an IMO/MMSI to focus VesselFinder on that vessel.</div>}
        <form className="future-ais-jump" onSubmit={selectByIdentifier}>
          <label>Direct IMO/MMSI<input aria-label="Direct IMO or MMSI" value={manualIdentifier}
            onChange={event=>setManualIdentifier(event.target.value.replace(/\D/g,'').slice(0,9))}
            placeholder="9316359 / 636017239" /></label>
          <button type="submit" disabled={!validIMO(manualIdentifier) && !validMMSI(manualIdentifier)}>Find vessel</button>
        </form>
        <p className="future-ais-notice">Selecting a Live case reloads the official widget for its IMO/MMSI. VesselFinder controls its own zoom and reported positions. Its embedded map cannot be read back or programmatically panned across origins.</p>
        <label className="future-ais-attestation"><input type="checkbox" checked={checkedExternal} disabled={!externalKey}
          onChange={(event)=>setCheckedExternal(event.target.checked)} />
          I personally inspected the external map for this case.
        </label>
        <a className="future-ais-provider-link" href="https://www.vesselfinder.com/it/embed" target="_blank" rel="noopener noreferrer">Official VesselFinder embed information ↗</a>
      </section>
    </div>
    <div className="future-ais-analysis">
      <article className="future-ais-evidence">
        <span className="future-eyebrow">03 / original AIS vs case position</span>
        <h3>{selected?.properties?.title || (identity ? 'Vessel selected without a Live case' : 'Select a case to inspect')}</h3>
        <div className="future-ais-evidence-grid">
          <div><small>Case event coordinates (historical)</small><strong>{selectedCoords ? coordsText(selectedCoords[1],'N','S') + ' · ' + coordsText(selectedCoords[0],'E','W') : 'Unavailable'}</strong>
            <span>{renderTime(selected?.properties?.timestamp_utc)}</span></div>
          <div><small>Last SeaCommons AIS fix</small><strong>{ais.vessel ? coordsText(ais.vessel.lat,'N','S') + ' · ' + coordsText(ais.vessel.lon,'E','W') : 'Unavailable'}</strong>
            <span>{ais.loading ? 'Refreshing…' : ais.error || renderTime(ais.vessel?.last_seen)}</span>
            <b className={'future-ais-age future-ais-age--' + aisFreshness(ais.vessel?.last_seen)}>{aisFreshness(ais.vessel?.last_seen)}</b></div>
        </div>
        <p className="future-ais-notice">An anomaly’s historical location must not be mistaken for a live vessel position. The external map is for human inspection, not independent machine-readable corroboration.</p>
      </article>
      <ReviewForm selected={selectedId && selected ? selectedId : null} checked={checkedExternal}
        reviewHistory={history} onSaved={()=>reloadHistory(selectedId)} />
    </div>
    {historyError && selected && <p className="future-ais-notice" role="status">{historyError}</p>}
  </div>;
}
