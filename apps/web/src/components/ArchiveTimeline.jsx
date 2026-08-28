import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { currentEstimateFeature } from '../simulation/liveTracking.js';
import { fetchJson } from '../services/api/client.js';

const EMPTY = { type: 'FeatureCollection', features: [] };
const PLAY_SECONDS = 22; // whole drift span compressed to this wall-clock duration

function trajectoryOf(geojson) {
  return (geojson?.features || []).find((f) => f?.properties?.type === 'trajectory') || null;
}

function bounds(coords) {
  let [w, s, e, n] = [180, 90, -180, -90];
  for (const [lon, lat] of coords) {
    if (lon < w) w = lon; if (lon > e) e = lon;
    if (lat < s) s = lat; if (lat > n) n = lat;
  }
  return [[w, s], [e, n]];
}

/**
 * Play-only. A general timeline of every archived incident; clicking one opens
 * its drift and a marker walks the trajectory as the scrubber advances.
 * Owns three MapLibre sources (archive-incidents / pb-drift / pb-marker) and
 * cleans them up on unmount. The live realtime feed is untouched.
 */
export default function ArchiveTimeline({ mapRef, mapReady, apiBase }) {
  const [cases, setCases] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [geoById, setGeoById] = useState({});
  const [clockMs, setClockMs] = useState(0);
  const [range, setRange] = useState([0, 1]);
  const [playing, setPlaying] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const rafRef = useRef(0);

  // ── the archive index ──────────────────────────────────────────────────────
  useEffect(() => {
    let alive = true;
    fetchJson(apiBase, '/api/v1/live/archives?limit=200')
      .then((data) => {
        if (!alive) return;
        const rows = (Array.isArray(data) ? data : data?.archives || [])
          .filter((r) => Number.isFinite(Number(r.lat)) && Number.isFinite(Number(r.lon)))
          .map((r) => ({
            id: String(r.id),
            ts: Date.parse(r.timestamp) || 0,
            lat: Number(r.lat),
            lon: Number(r.lon),
            vessel: r.vessel_type || 'case',
            persons: Number(r.persons) || 1,
          }))
          .filter((r) => r.ts > 0)
          .sort((a, b) => a.ts - b.ts);
        setCases(rows);
      })
      .catch(() => setCases([]));
    return () => { alive = false; };
  }, [apiBase]);

  // ── map sources / layers, created once the map is ready ─────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return undefined;
    const add = (id, data) => {
      if (!map.getSource(id)) map.addSource(id, { type: 'geojson', data });
    };
    add('archive-incidents', EMPTY);
    add('pb-drift', EMPTY);
    add('pb-marker', EMPTY);
    const layer = (spec) => { if (!map.getLayer(spec.id)) map.addLayer(spec); };
    layer({
      id: 'pb-cone', type: 'fill', source: 'pb-drift',
      filter: ['==', ['geometry-type'], 'Polygon'],
      paint: { 'fill-color': '#5cffd7', 'fill-opacity': 0.07 },
    });
    layer({
      id: 'pb-track', type: 'line', source: 'pb-drift',
      filter: ['==', ['geometry-type'], 'LineString'],
      paint: { 'line-color': '#5cffd7', 'line-width': 2, 'line-dasharray': [2, 1.5], 'line-opacity': 0.85 },
    });
    layer({
      id: 'archive-dot', type: 'circle', source: 'archive-incidents',
      paint: {
        'circle-radius': ['case', ['==', ['get', 'id'], ['literal', activeId || '']], 7, 4],
        'circle-color': '#8bf0c5',
        'circle-opacity': ['case', ['==', ['get', 'id'], ['literal', activeId || '']], 0.95, 0.4],
        'circle-stroke-color': '#0b1a1f', 'circle-stroke-width': 1,
      },
    });
    layer({
      id: 'pb-marker-halo', type: 'circle', source: 'pb-marker',
      paint: { 'circle-radius': 16, 'circle-color': '#ffd166', 'circle-opacity': 0.18 },
    });
    layer({
      id: 'pb-marker', type: 'circle', source: 'pb-marker',
      paint: { 'circle-radius': 6, 'circle-color': '#ffd166', 'circle-stroke-color': '#3a2a00', 'circle-stroke-width': 1 },
    });
    const onClick = (ev) => {
      const id = ev.features?.[0]?.properties?.id;
      if (id) selectCase(String(id));
    };
    map.on('click', 'archive-dot', onClick);
    map.getCanvas().style.cursor = '';
    return () => {
      map.off('click', 'archive-dot', onClick);
      for (const id of ['pb-cone', 'pb-track', 'archive-dot', 'pb-marker-halo', 'pb-marker']) {
        if (map.getLayer(id)) map.removeLayer(id);
      }
      for (const id of ['archive-incidents', 'pb-drift', 'pb-marker']) {
        if (map.getSource(id)) map.removeSource(id);
      }
    };
    // selectCase is stable enough; re-running on activeId is handled below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mapRef, mapReady]);

  // keep the "active" dot styling in sync
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.getLayer('archive-dot')) return;
    map.setPaintProperty('archive-dot', 'circle-radius',
      ['case', ['==', ['get', 'id'], ['literal', activeId || '']], 7, 4]);
    map.setPaintProperty('archive-dot', 'circle-opacity',
      ['case', ['==', ['get', 'id'], ['literal', activeId || '']], 0.95, 0.4]);
  }, [activeId, mapRef]);

  // push all incident dots onto the map
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.getSource('archive-incidents')) return;
    map.getSource('archive-incidents').setData({
      type: 'FeatureCollection',
      features: cases.map((c) => ({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [c.lon, c.lat] },
        properties: { id: c.id, ts: c.ts, vessel: c.vessel },
      })),
    });
  }, [cases, mapRef]);

  const selectCase = useCallback(async (id) => {
    setPlaying(false);
    setActiveId(id);
    const map = mapRef.current;
    let geojson = geoById[id];
    if (!geojson) {
      try {
        geojson = await fetchJson(apiBase, `/api/v1/live/archives/${encodeURIComponent(id)}/geojson`);
        setGeoById((prev) => ({ ...prev, [id]: geojson }));
      } catch {
        return;
      }
    }
    if (map?.getSource('pb-drift')) map.getSource('pb-drift').setData(geojson);
    const traj = trajectoryOf(geojson);
    const times = (traj?.properties?.timestamps_utc || []).map((t) => Date.parse(t)).filter(Number.isFinite);
    if (times.length >= 2) {
      setRange([times[0], times.at(-1)]);
      setClockMs(times[0]);
      paintMarker(geojson, times[0]);
    }
    if (map && traj?.geometry?.coordinates?.length) {
      map.fitBounds(bounds(traj.geometry.coordinates), { padding: 90, duration: 900, maxZoom: 9 });
    }
  }, [apiBase, geoById, mapRef]);

  const paintMarker = useCallback((geojson, atMs) => {
    const map = mapRef.current;
    if (!map?.getSource('pb-marker')) return;
    const traj = trajectoryOf(geojson);
    const eventTs = traj?.properties?.timestamps_utc?.[0];
    const point = traj ? currentEstimateFeature(traj, eventTs, atMs) : null;
    map.getSource('pb-marker').setData(point ? { type: 'FeatureCollection', features: [point] } : EMPTY);
  }, [mapRef]);

  // scrubber → marker
  useEffect(() => {
    if (activeId && geoById[activeId]) paintMarker(geoById[activeId], clockMs);
  }, [clockMs, activeId, geoById, paintMarker]);

  // play loop: advance clockMs, whole span in PLAY_SECONDS, stop at the end
  useEffect(() => {
    if (!playing) { cancelAnimationFrame(rafRef.current); return undefined; }
    const [start, end] = range;
    const spanMs = Math.max(1, end - start);
    const startedAt = performance.now();
    const startClock = clockMs >= end ? start : clockMs;
    const tick = (nowPerf) => {
      const progressed = ((nowPerf - startedAt) / 1000) / PLAY_SECONDS;
      const next = startClock + progressed * spanMs;
      if (next >= end) { setClockMs(end); setPlaying(false); return; }
      setClockMs(next);
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing]);

  const span = useMemo(() => {
    if (!cases.length) return [Date.now() - 8.64e7, Date.now()];
    return [cases[0].ts, cases.at(-1).ts];
  }, [cases]);

  const activeCase = cases.find((c) => c.id === activeId) || null;
  const elapsedH = activeCase ? Math.max(0, (clockMs - range[0]) / 3.6e6) : 0;

  return (
    <div className={`archive-timeline ${collapsed ? 'is-collapsed' : ''}`}>
      <div className="atl-head">
        <strong>Archive</strong>
        <span className="atl-count">{cases.length} incidents</span>
        {activeCase ? (
          <span className="atl-active">
            {activeCase.vessel.replace(/_/g, ' ')} · {new Date(activeCase.ts).toLocaleDateString()} · +{elapsedH.toFixed(1)} h
          </span>
        ) : null}
        <button className="atl-collapse" onClick={() => setCollapsed((v) => !v)}>
          {collapsed ? '▲' : '▼'}
        </button>
      </div>

      {!collapsed ? (
        <>
          <div className="atl-strip">
            {cases.map((c) => {
              const left = ((c.ts - span[0]) / Math.max(1, span[1] - span[0])) * 100;
              return (
                <button
                  key={c.id}
                  className={`atl-tick ${c.id === activeId ? 'is-active' : ''}`}
                  style={{ left: `${left}%` }}
                  title={`${c.vessel} — ${new Date(c.ts).toLocaleString()}`}
                  onClick={() => selectCase(c.id)}
                />
              );
            })}
          </div>

          {activeCase ? (
            <div className="atl-controls">
              <button className="atl-play" onClick={() => setPlaying((v) => !v)}>
                {playing ? '❚❚' : '▶'}
              </button>
              <input
                type="range"
                min={range[0]}
                max={range[1]}
                step={Math.max(1, (range[1] - range[0]) / 400)}
                value={Math.min(range[1], Math.max(range[0], clockMs))}
                onChange={(e) => { setPlaying(false); setClockMs(Number(e.target.value)); }}
              />
              <span className="atl-time">{new Date(clockMs).toISOString().slice(11, 16)} UTC</span>
            </div>
          ) : (
            <div className="atl-hint">Select an incident on the map or the strip to replay its drift.</div>
          )}
        </>
      ) : null}
    </div>
  );
}
