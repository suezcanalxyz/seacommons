import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';

test('public Live mobile reserves upper map and uses full-width readable report sheet', async () => {
  const css = await readFile(new URL('../../styles.css', import.meta.url), 'utf8');
  assert.match(css, /\.cop-shell\.is-live-mode\s*\{[^}]*--nav-h:\s*env\(safe-area-inset-bottom\)/s);
  assert.match(css, /\.cop-shell\.is-live-mode\s+\.cone-panel\s*\{[^}]*top:\s*34dvh/s);
  assert.match(css, /\.cop-shell\.is-live-mode\s+\.cone-panel\s*\{[^}]*max-height:\s*none/s);
  assert.match(css, /\.cop-shell\.is-live-mode\s+\.cone-row\s*\{[^}]*grid-template-columns:\s*minmax\(88px,\s*auto\)\s+minmax\(0,\s*1fr\)/s);
});

test('opening a mobile map panel recenters feature above the report sheet', async () => {
  const source = await readFile(new URL('../../main.jsx', import.meta.url), 'utf8');
  assert.match(source, /mobilePanelMapPadding/);
  assert.match(source, /bottom:\s*Math\.round\(window\.innerHeight\s*\*\s*0\.66\)/);
});


test('public Live hides transport-buffer tier counts', async () => {
  const source = await readFile(new URL('../../components/IntelDashboard.jsx', import.meta.url), 'utf8');
  assert.match(source, /!publicMode \? <span className="intel-tier-count">/);
  assert.match(source, /!publicMode \? <span className="intel-tier-head-count">/);
  assert.match(source, /!publicMode && Object\.keys\(intelStats\.by_type/);
});

test('public Live hides the persistent MapLibre attribution control', async () => {
  const source = await readFile(new URL('../../main.jsx', import.meta.url), 'utf8');
  assert.match(source, /attributionControl:\s*!isPublicLiveHost/);
});


test('public LIVE uses the selected satellite basemap rather than silently forcing standard', async () => {
  const source = await readFile(new URL('../../main.jsx', import.meta.url), 'utf8');
  assert.match(source, /const effectiveBaseMap = baseMap;/);
  assert.doesNotMatch(source, /isPublicLiveHost \? 'standard' : baseMap/);
  assert.match(source, /allowSatellite=\{true\}/);
  assert.match(source, /id: 'satellite', type: 'raster'/);
});

test('PLAY report leads with an accessible evidence summary before technical detail', async () => {
  const source = await readFile(new URL('../play/PlayTimeline.jsx', import.meta.url), 'utf8');
  assert.match(source, /aria-label="Report at a glance"/);
  assert.match(source, /What we know/);
  assert.match(source, /What remains uncertain:/);
  assert.match(source, /Evidence assessment · detailed record/);
});


test('PLAY creates incident layers on style readiness without waiting for satellite tile downloads', async () => {
  const source = await readFile(new URL('../play/PlayTimeline.jsx', import.meta.url), 'utf8');
  assert.match(source, /map\.on\('style\.load', \(\) => \{/);
  assert.doesNotMatch(source, /map\.on\('load', \(\) => \{/);
  assert.match(source, /map\.addSource\('play-incidents'/);
});

test('PLAY excludes rolling last 24h without deleting incident evidence and raises markers above raster', async () => {
  const source = await readFile(new URL('../play/PlayTimeline.jsx', import.meta.url), 'utf8');
  assert.match(source, /reported < archiveNow - 24 \* 60 \* 60 \* 1000/);
  assert.match(source, /resolveGlobalTimelinePosition\(historicalIncidents/);
  assert.match(source, /historicalIncidents\.filter\(/);
  assert.match(source, /map\.moveLayer\(layerId\)/);
  assert.match(source, /'play-incidents', 'play-vessels'/);
});
