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
  assert.match(source, /!publicMode \? <span className=\"intel-tier-count\">/);
  assert.match(source, /!publicMode \? <span className=\"intel-tier-head-count\">/);
});
