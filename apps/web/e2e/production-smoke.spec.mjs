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
  const rasterResponses = [];
  const rasterDecodeErrors = [];
  const pendingRasterDecodes = new Set();
  let lastRasterActivity = Date.now();
  page.on('response', response => {
    const url = response.url();
    if (/\.(?:png|jpe?g|webp)(?:\?|$)|\/(?:tiles?|styles?)\//i.test(url) &&
        !url.startsWith('data:')) {
      tileResponses.push({ status: response.status(), url: new URL(url).hostname });
      // A 2xx style JSON response alone cannot prove geographic raster coverage.
      if (/\.(?:png|jpe?g|webp)(?:\?|$)|\/tiles?\//i.test(url) && response.status() >= 200 && response.status() < 300) {
        if (/^image\//i.test(response.headers()['content-type'] || '')) {
          // Verify a browser decoder can read the actual network payload, not just its MIME header.
          lastRasterActivity = Date.now();
          const decode = response.body().then(async bytes => {
            const encoded = bytes.toString('base64');
            const decoded = await page.evaluate(async ({ encoded, mime }) => {
              const image = new Image();
              image.src = `data:${mime};base64,${encoded}`;
              await image.decode();
              return image.naturalWidth > 0 && image.naturalHeight > 0;
            }, { encoded, mime: response.headers()['content-type'].split(';')[0] });
            if (decoded) rasterResponses.push({ url: new URL(url).hostname, contentType: response.headers()['content-type'] });
            else rasterDecodeErrors.push('Zero-size decoded raster tile');
          }).catch(error => rasterDecodeErrors.push(String(error)));
          pendingRasterDecodes.add(decode);
          void decode.finally(() => {
            pendingRasterDecodes.delete(decode);
            lastRasterActivity = Date.now();
          });
        }
      }
    }
  });
  page.on('requestfailed', request => {
    if (/\.(?:png|jpe?g|webp)(?:\?|$)|\/(?:tiles?|styles?)\//i.test(request.url())) {
      tileFailures.push(request.failure()?.errorText || 'tile request failed');
    }
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(PLAY_URL, { waitUntil: 'domcontentloaded' });
  await expect(page.locator('main.play-public-shell')).toBeVisible();
  await expect.poll(async () => page.locator('.maplibregl-canvas, .leaflet-container').count(), {
    timeout: 20_000,
  }).toBeGreaterThan(0);
  // A detached or zero-sized canvas/container is not evidence of visible geography.
  await expect.poll(async () => page.locator('.maplibregl-canvas, .leaflet-container').evaluateAll(nodes =>
    nodes.some(node => {
      const rect = node.getBoundingClientRect();
      const style = getComputedStyle(node);
      return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
    })), {
    message: 'PLAY map must have a visible, nonzero viewport',
    timeout: 20_000,
  }).toBeTruthy();

  // The map's own load event is insufficient: the geographic provider must
  // deliver at least one successful non-synthetic tile or style resource.
  await expect.poll(() => tileResponses.filter(item => item.status >= 200 && item.status < 300).length, {
    timeout: 25_000,
  }).toBeGreaterThan(0);
  await expect.poll(() => rasterResponses.filter(item => /^image\//i.test(item.contentType)).length, {
    message: 'At least one real raster tile must be decoded by the browser; MIME headers alone do not count',
    timeout: 25_000,
  }).toBeGreaterThan(0);
  // A successful first tile must not mask failures from other decodes already in flight.
  // Wait for the decode set to drain AND remain quiet. A one-time Promise.all
  // snapshot can miss late network responses after the first successful tile.
  await expect.poll(() => pendingRasterDecodes.size === 0 && Date.now() - lastRasterActivity >= 750, {
    message: 'All raster decodes must settle and remain quiet for 750 ms',
    timeout: 15_000,
    intervals: [100, 200, 300],
  }).toBeTruthy();
  expect(rasterDecodeErrors, 'Raster payloads must decode successfully').toEqual([]);
  expect(tileFailures, 'No geographic tile requests may fail').toEqual([]);
  expect(tileResponses.filter(item => item.status >= 400), 'No tile HTTP failures').toEqual([]);
  await page.screenshot({ path: test.info().outputPath('production-play-mobile-basemap.png'), fullPage: true });
});
