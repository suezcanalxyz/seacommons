import test from 'node:test';
import assert from 'node:assert/strict';

import { deriveFeedStatus, feedStatusIsFresh } from './feedStatus.js';

test('initial connect with nothing yet is loading', () => {
  assert.equal(deriveFeedStatus({}), 'loading');
});

test('a successful response with events is live', () => {
  assert.equal(
    deriveFeedStatus({ everSucceeded: true, transportHealthy: true, lastResponseEmpty: false }),
    'live',
  );
});

test('a successful canonical response with zero events is empty, not offline', () => {
  assert.equal(
    deriveFeedStatus({ everSucceeded: true, transportHealthy: true, lastResponseEmpty: true }),
    'empty',
  );
});

test('a transient failure while a snapshot is on screen is stale', () => {
  assert.equal(
    deriveFeedStatus({
      everSucceeded: true,
      transportHealthy: false,
      consecutiveFailures: 1,
      haveCachedEvents: true,
    }),
    'stale',
  );
});

test('a failure with no snapshot after having connected is retrying', () => {
  assert.equal(
    deriveFeedStatus({
      everSucceeded: true,
      transportHealthy: false,
      consecutiveFailures: 2,
      haveCachedEvents: false,
    }),
    'retrying',
  );
});

test('repeated failures are offline regardless of snapshot', () => {
  assert.equal(
    deriveFeedStatus({
      everSucceeded: true,
      transportHealthy: false,
      consecutiveFailures: 3,
      haveCachedEvents: true,
    }),
    'offline',
  );
});

test('feedStatusIsFresh only trusts live and empty', () => {
  assert.equal(feedStatusIsFresh('live'), true);
  assert.equal(feedStatusIsFresh('empty'), true);
  assert.equal(feedStatusIsFresh('stale'), false);
  assert.equal(feedStatusIsFresh('offline'), false);
  assert.equal(feedStatusIsFresh('loading'), false);
});

test('liveSignalTotal prefers canonical mode counts over the transport buffer length', async () => {
  const { liveSignalTotal } = await import('./feedStatus.js');
  assert.equal(liveSignalTotal({ humanitarian: 1, security: 1250, safety: 44 }, 150), 1295);
  assert.equal(liveSignalTotal({}, 150), 150);
});
