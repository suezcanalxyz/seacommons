import test from 'node:test';
import assert from 'node:assert/strict';

import { normalizeLiveMode as normalizeRootLiveMode } from '../../../../../api/live.js';
import { normalizeLiveMode as normalizeWebLiveMode } from '../../../api/live.js';

for (const [name, normalize] of [
  ['root proxy', normalizeRootLiveMode],
  ['web proxy', normalizeWebLiveMode],
]) {
  test(`${name} preserves canonical maritime and maps legacy security to maritime`, () => {
    assert.equal(normalize('humanitarian'), 'humanitarian');
    assert.equal(normalize('maritime'), 'maritime');
    assert.equal(normalize('security'), 'maritime');
    assert.equal(normalize('all'), 'all');
    assert.equal(normalize('unexpected'), 'humanitarian');
  });
}
