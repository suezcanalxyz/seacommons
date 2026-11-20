import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';

test('public SAR asset markers stay triangular even when stationary', async () => {
  const source = await readFile(new URL('../../main.jsx', import.meta.url), 'utf8');
  assert.match(source, /id: 'vessels-stationary-layer'.*?type: 'circle'/s);
  assert.match(source, /id: 'vessels-layer'.*?icon-image': 'vessel-arrow'/s);
  assert.match(source, /id: 'vessels-ngo-stationary'.*?type: 'symbol'.*?icon-image': 'vessel-arrow'/s);
  assert.match(source, /id: 'vessels-ngo'.*?icon-image': 'vessel-arrow'/s);
  assert.match(source, /id: 'selected-vessel-track'.*?type: 'line'/s);
});

test('vessel click handler opens reports from moving and stationary AIS layers', async () => {
  const source = await readFile(new URL('../../main.jsx', import.meta.url), 'utf8');
  assert.match(source, /for \(const lyr of \['vessels-layer', 'vessels-stationary-layer', 'vessels-ngo', 'vessels-ngo-stationary'/);
  assert.match(source, /openVesselReport\(feature\)/);
});


test('moving vessel symbols distinguish missing AIS bearings from northbound 0 degrees', async () => {
  const { vesselBearingExpression, vesselDirectionalIconExpression } =
    await import('../map/vesselMarker.js');
  const bearing = vesselBearingExpression();
  const icon = vesselDirectionalIconExpression();
  assert.equal(bearing[0], 'case');
  assert.equal(bearing.at(-1), 0); // rotation only; diamond remains non-directional
  assert.equal(icon[0], 'case');
  assert.equal(icon.at(-2), 'vessel-arrow');
  assert.equal(icon.at(-1), 'vessel-diamond');
  // Explicit missing/null values become -1, never fabricated 0°.
  assert.deepEqual(bearing[1][1][1], ['case', ['==', ['get', 'heading_deg'], null], -1, ['to-number', ['get', 'heading_deg'], -1]]);
});

test('MapLibre registers a separate SDF diamond for moving vessels without a valid bearing', async () => {
  const source = await readFile(new URL('../../main.jsx', import.meta.url), 'utf8');
  assert.match(source, /map.addImage\('vessel-diamond', createVesselDiamondImage\(48\), \{ sdf: true \}\)/);
  for (const layer of ['intel-vessel-core', 'vessels-layer', 'vessels-ngo', 'sanctioned-vessels-moving']) {
    const layerStart = source.indexOf(`id: '${layer}'`);
    assert.ok(layerStart >= 0, layer);
    const layout = source.slice(layerStart, source.indexOf('paint:', layerStart));
    assert.match(layout, /'icon-image': vesselDirectionalIconExpression\(/, layer);
    assert.match(layout, /'icon-rotate': vesselBearingExpression\(/, layer);
  }
});
