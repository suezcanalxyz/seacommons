import test from 'node:test';
import assert from 'node:assert/strict';

import { parseLiveModeCounts } from '../../../api/status.js';

test('canonical humanitarian and maritime counts are valid despite obsolete security key', () => {
  assert.deepEqual(
    parseLiveModeCounts({ humanitarian: 3, maritime: 6, security: 0 }),
    { valid: true, humanitarian: 3, maritime: 6 },
  );
});

test('a quiet mode with zero published events is still healthy', () => {
  assert.deepEqual(
    parseLiveModeCounts({ humanitarian: 0, maritime: 0 }),
    { valid: true, humanitarian: 0, maritime: 0 },
  );
});

test('missing maritime counts do not silently fall back to security', () => {
  assert.deepEqual(
    parseLiveModeCounts({ humanitarian: 3, security: 6 }),
    { valid: false, humanitarian: 3, maritime: 0 },
  );
});

test('malformed, negative and missing counts fail closed', () => {
  for (const counts of [
    null,
    {},
    { humanitarian: 3, maritime: -1 },
    { humanitarian: 3, maritime: '' },
    { humanitarian: 'three', maritime: 6 },
    { humanitarian: 3, maritime: null },
  ]) {
    assert.equal(parseLiveModeCounts(counts).valid, false);
  }
});

test('numeric string counts are accepted without coercing blanks to zero', () => {
  assert.deepEqual(
    parseLiveModeCounts({ humanitarian: '3', maritime: '6' }),
    { valid: true, humanitarian: 3, maritime: 6 },
  );
});
