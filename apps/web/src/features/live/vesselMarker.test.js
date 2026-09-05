import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';

test('public vessel markers use triangles for moving and stationary ships, with NGO as the only color exception', async () => {
  const source = await readFile(new URL('../../main.jsx', import.meta.url), 'utf8');
  assert.doesNotMatch(source, /id: 'vessels-stationary'/);
  assert.doesNotMatch(source, /id: 'vessels-ngo-stationary'/);
  assert.match(source, /id: 'vessels-layer'.*?icon-image': 'vessel-arrow'/s);
  assert.match(source, /id: 'vessels-ngo'.*?icon-image': 'vessel-arrow'/s);
  assert.match(source, /id: 'intel-vessel-core'.*?icon-color': '#7dd3fc'/s);
  assert.match(source, /id: 'proximity-vessels-layer'.*?icon-color': '#7dd3fc'/s);
  assert.match(source, /id: 'live-nearby-vessels-layer'.*?icon-color': '#7dd3fc'/s);
  assert.match(source, /id: 'vessels-ngo'.*?icon-color': '#8bf0c5'/s);
  assert.match(source, /id: 'ngo-response-points-layer', type: 'symbol'.*?icon-image': 'vessel-arrow'.*?icon-color': '#8bf0c5'/s);
});

test('vessel click handler targets symbol layers only', async () => {
  const source = await readFile(new URL('../../main.jsx', import.meta.url), 'utf8');
  assert.match(source, /for \(const lyr of \['vessels-layer', 'vessels-ngo', 'proximity-vessels-layer'\]\)/);
});
