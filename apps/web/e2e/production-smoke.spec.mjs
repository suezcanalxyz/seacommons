import { expect, test } from '@playwright/test';

const LIVE_URL = String(process.env.E2E_LIVE_URL || 'https://live.seacommons.org').replace(/\/$/, '');
const PLAY_URL = String(process.env.E2E_PLAY_URL || 'https://play.seacommons.org').replace(/\/$/, '');
const CANONICAL_FAMILIES = ['ais', 'first_party', 'partner', 'public_feed', 'radio'];

test('production public browser release path is read-only and healthy', async ({ page, request }) => {
  await page.goto(LIVE_URL, { waitUntil: 'domcontentloaded' });
  await expect(page.locator('main.cop-shell.is-live-mode')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Live feed' })).toBeVisible();

  await page.goto(PLAY_URL, { waitUntil: 'domcontentloaded' });
  await expect(page.locator('main.play-public-shell')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Play' })).toBeVisible();

  const pipelineResponse = await request.get(`${LIVE_URL}/api/v1/live/pipeline`);
  expect(pipelineResponse.ok()).toBeTruthy();
  const pipeline = await pipelineResponse.json();
  const families = new Set((pipeline?.sources || []).map((source) => source?.family));
  for (const family of CANONICAL_FAMILIES) expect(families.has(family)).toBeTruthy();

  const meshResponse = await request.get(`${LIVE_URL}/api/v1/live/receivers/mesh?limit=64`);
  expect(meshResponse.ok()).toBeTruthy();
  const mesh = await meshResponse.json();
  const receiver = (mesh?.receivers || []).find((item) => item?.listen_available);

  if (!receiver?.receiver_id) {
    test.info().annotations.push({
      type: 'listen',
      description: 'No receiver is currently listen_available; Listen smoke skipped without fabricating success.',
    });
    return;
  }

  const listenResponse = await request.get(
    `${LIVE_URL}/api/v1/live/radio/listen/${encodeURIComponent(receiver.receiver_id)}?stream_seconds=1`,
    { timeout: 20_000 },
  );
  expect(listenResponse.status()).toBe(200);
  expect(listenResponse.headers()['cache-control'] || '').toContain('no-store');
  expect(listenResponse.headers()['x-seacommons-persistent']).toBe('false');
  expect((await listenResponse.body()).byteLength).toBeGreaterThan(0);
});


// Independent geographic gate: fixture-based MapLibre screenshots deliberately mock
// provider tiles, so they cannot certify that the public basemap loads.
test('production PLAY renders real geographic tiles without provider interception', async ({ page }) => {
  const tileResponses = [];
  const tileFailures = [];
  page.on('response', response => {
    const url = response.url();
    if (/\\.(?:png|jpe?g|webp)(?:\\?|$)|\\/(?:tiles?|styles?)\\//i.test(url) &&
        !url.startsWith('data:')) {
      tileResponses.push({ status: response.status(), url: new URL(url).hostname });
    }
  });
  page.on('requestfailed', request => {
    if (/\\.(?:png|jpe?g|webp)(?:\\?|$)|\\/(?:tiles?|styles?)\\//i.test(request.url())) {
      tileFailures.push(request.failure()?.errorText || 'tile request failed');
    }
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(PLAY_URL, { waitUntil: 'domcontentloaded' });
  await expect(page.locator('main.play-public-shell')).toBeVisible();
  await expect.poll(async () => page.locator('.maplibregl-canvas, .leaflet-container').count(), {
    timeout: 20_000,
  }).toBeGreaterThan(0);

  // The map's own load event is insufficient: the geographic provider must
  // deliver at least one successful non-synthetic tile or style resource.
  await expect.poll(() => tileResponses.filter(item => item.status >= 200 && item.status < 300).length, {
    timeout: 25_000,
  }).toBeGreaterThan(0);
  expect(tileFailures, 'No geographic tile requests may fail').toEqual([]);
  expect(tileResponses.filter(item => item.status >= 400), 'No tile HTTP failures').toEqual([]);
  await page.screenshot({ path: test.info().outputPath('production-play-mobile-basemap.png'), fullPage: true });
});
