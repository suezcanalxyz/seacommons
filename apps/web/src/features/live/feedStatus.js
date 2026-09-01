/**
 * Canonical Live feed connection state (docs/fixes.md F-06 / Phase 0.4).
 *
 * A successful canonical response with zero events (`empty`) must never render
 * the same as a transport failure (`offline`/`retrying`) or the initial
 * connect (`loading`). A failure that still has a last-good snapshot to show
 * is `stale`, not `offline`.
 *
 * States: loading | live | stale | retrying | offline | empty
 */
export function deriveFeedStatus({
  everSucceeded = false,
  lastResponseEmpty = false,
  transportHealthy = false,
  consecutiveFailures = 0,
  haveCachedEvents = false,
} = {}) {
  if (transportHealthy) return lastResponseEmpty ? 'empty' : 'live';
  if (consecutiveFailures >= 3) return 'offline';
  if (haveCachedEvents) return 'stale';
  if (!everSucceeded && consecutiveFailures === 0) return 'loading';
  return 'retrying';
}

/** Whether a status means "the data on screen is trustworthy right now". */
export function feedStatusIsFresh(status) {
  return status === 'live' || status === 'empty';
}

/** Short label for a status chip. */
export const FEED_STATUS_LABEL = {
  loading: 'sync',
  live: 'live',
  empty: 'live',
  stale: 'stale',
  retrying: 'retry',
  offline: 'offline',
};

/** Chip tone for a status. */
export const FEED_STATUS_TONE = {
  loading: 'info',
  live: 'ok',
  empty: 'ok',
  stale: 'warn',
  retrying: 'warn',
  offline: 'warn',
};
