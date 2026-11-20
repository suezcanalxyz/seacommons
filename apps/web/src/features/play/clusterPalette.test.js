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
  // Count bands are applied by clusterPaint in the renderer, while the
  // historical always-visible legend was replaced by MapReferenceBar.
  assert.match(source, /const \[first, \.\.\.remaining\] = PLAY_CLUSTER_BANDS/);
  const reference = await readFile(new URL('../../components/MapReferenceBar.jsx', import.meta.url), 'utf8');
  assert.match(reference, /Grouped records reflect the number of nearby markers/);
  assert.match(reference, /Brightness and size indicate a group of observations/);
});
