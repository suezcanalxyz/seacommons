import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

test('PLAY cluster colors encode count not incident classification', async () => {
  const source = await readFile(new URL('./PlayTimeline.jsx', import.meta.url), 'utf8');
  assert.match(source, /'circle-color': \['step', \['get', 'point_count'\], '#38bdf8', 10, '#2dd4bf', 25, '#d4ff3f', 75, '#facc15', 200, '#f472b6'\]/);
  assert.match(source, /'circle-radius': \['step', \['get', 'point_count'\]/);
  assert.match(source, /200\+ grouped points/);
  assert.match(source, /cluster colors and sizes indicate grouped point count/);
});
