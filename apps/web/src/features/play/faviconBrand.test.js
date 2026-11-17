import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

test('LIVE and PLAY use the same branded favicon asset', async () => {
  const html = await readFile(new URL('../../../index.html', import.meta.url), 'utf8');
  const svg = await readFile(new URL('../../../public/favicon.svg', import.meta.url), 'utf8');
  const playHtml = await readFile(new URL('../../../play.html', import.meta.url), 'utf8');
  assert.match(html, /rel="icon" type="image\/svg\+xml" href="\/favicon\.svg"/);
  assert.match(playHtml, /rel="icon" type="image\/svg\+xml" href="\/favicon\.svg"/);
  assert.doesNotMatch(html, /⚓/);
  assert.match(svg, /viewBox="0 0 64 64"/);
  assert.match(svg, /M13 19H51M13 45H51/);
  assert.match(svg, /M21 36L43 28/);
});
