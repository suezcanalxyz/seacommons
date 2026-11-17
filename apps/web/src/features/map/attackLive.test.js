import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
test('LIVE renders attack crosshairs independently of red humanitarian markers', async () => {
  const source = await readFile(new URL('../../main.jsx', import.meta.url), 'utf8');
  assert.match(source, /id: 'intel-attack-markers'/);
  assert.match(source, /isAttackIncident\(f\.properties\)/);
  assert.match(source, /map\.moveLayer\('intel-attack-markers'\)/);
});
