import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { PLAY_CLUSTER_BANDS } from '../map/fallbackRenderer.js';

test('PLAY cluster colors encode count not incident classification', async () => {
  const source = await readFile(new URL('./PlayTimeline.jsx', import.meta.url), 'utf8');
  assert.deepEqual(PLAY_CLUSTER_BANDS.map(({ minimum, color }) => [minimum, color]), [
    [2, '#38bdf8'], [10, '#2dd4bf'], [25, '#d4ff3f'], [75, '#facc15'], [200, '#f472b6'],
  ]);
  assert.match(source, /'circle-color': clusterPaint\('color'\)/);
  assert.match(source, /'circle-radius': clusterPaint\('radius'\)/);
  assert.match(source, /PLAY_CLUSTER_BANDS\.map\(\(\{ label, color \}\)/);
  assert.match(source, /cluster colors and sizes indicate grouped point count/);
});
