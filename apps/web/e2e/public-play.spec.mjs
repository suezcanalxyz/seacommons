import { expect, test } from '@playwright/test';

import { installDeterministicRoutes, PUBLIC_PLAY_URL } from './support/publicFixtures.mjs';

test.beforeEach(async ({ page }) => {
  await installDeterministicRoutes(page);
});

test('Play archive exposes deterministic filters, dossier and global timeline', async ({ page }) => {
  await page.goto(PUBLIC_PLAY_URL);

  await expect(page.locator('main.play-public-shell')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Play' })).toBeVisible();
  const filters = page.getByRole('group', { name: 'Play archive filters' });
  for (const label of ['ALL', 'HUMANITARIAN', 'MARITIME', 'SATELLITE', 'SANCTIONS', 'INVESTIGATION']) {
    await expect(filters.getByRole('button', { name: label })).toBeVisible();
  }
  await expect(filters.getByRole('button', { name: 'CORRELATED' })).toHaveCount(0);
  await expect(filters.getByRole('combobox', { name: 'Incident type' })).toBeVisible();

  const cases = page.locator('.play-cases__list');
  await expect(cases.getByText('Historical distress', { exact: true })).toBeVisible();
  await expect(cases.getByText('Historical safety report', { exact: true })).toBeVisible();
  await expect(cases.getByText('Reviewed correlated case', { exact: true })).toBeVisible();

  await filters.getByRole('button', { name: 'HUMANITARIAN' }).click();
  await expect(cases.getByText('Historical distress', { exact: true })).toBeVisible();
  await expect(cases.getByText('Historical safety report', { exact: true })).toHaveCount(0);
  await expect(cases.getByText('Reviewed correlated case', { exact: true })).toHaveCount(0);

  await filters.getByRole('button', { name: 'ALL' }).click();
  await cases.getByText('Historical distress', { exact: true }).click();
  const dossier = page.locator('.play-evidence.is-open');
  await expect(dossier).toBeVisible();
  await expect(dossier.locator('h2', { hasText: 'Historical distress' })).toBeVisible();
  await expect(dossier.getByText('RESOLVED', { exact: true })).toBeVisible();

  await expect(page.getByRole('slider', { name: 'Global archive timeline' })).toBeVisible();
  await expect(page.locator('.play-all-badge strong')).toHaveText('ALL');
});

test('mobile Play keeps an interactive archive map when MapLibre cannot initialize', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript(() => { window.__SEACOMMONS_FORCE_MAP_FALLBACK__ = true; });
  await page.goto(PUBLIC_PLAY_URL);
  await expect(page.locator('.leaflet-container')).toBeVisible();
  const markers = page.locator('.seacommons-fallback-marker');
  await expect(markers).toHaveCount(3);
  const targetMarker = page.locator('.seacommons-fallback-marker--play-humanitarian-1');
  await expect(targetMarker).toHaveAttribute('role', 'button');
  await targetMarker.dispatchEvent('pointerup');
  const dossier = page.locator('.play-evidence.is-open');
  await expect(dossier).toBeVisible();
  await expect(dossier.locator('h2')).toContainText('Historical distress');
});


test('desktop and mobile Play preserve archive navigation with MapLibre or the supported fallback', async ({ page }, testInfo) => {
  for (const viewport of [{ width: 1280, height: 800 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport);
    await page.goto(PUBLIC_PLAY_URL);
    // CI Chromium can lack WebGL: PLAY intentionally switches to Leaflet then.
    // Assert the actual supported renderer rather than falsely requiring WebGL.
    const canvas = page.locator('.maplibregl-canvas');
    const fallback = page.locator('.leaflet-container');
    await expect.poll(async () => (await canvas.count()) + (await fallback.count())).toBeGreaterThan(0);
    const renderer = await canvas.count() ? 'maplibre' : 'leaflet';
    await expect(renderer === 'maplibre' ? canvas : fallback).toBeVisible();
    await expect(page.locator('.play-map-error')).toHaveCount(0);
    testInfo.annotations.push({ type: 'renderer', description: `${viewport.width}x${viewport.height}: ${renderer}` });
    await page.screenshot({ path: testInfo.outputPath(`play-${viewport.width}-continent.png`), fullPage: true });
    const cases = page.locator('.play-cases__list');
    if (viewport.width < 600) {
      // Phone layout hides the legacy toggle; navigate through the visible dock.
      await page.getByRole('navigation', { name: 'Play navigation' }).getByRole('button', { name: 'Archive' }).click();
      await expect(page.locator('.play-archive-panel')).toHaveClass(/is-mobile-open/);
    }
    await cases.getByText('Historical distress', { exact: true }).click();
    await expect(page.locator('.play-evidence.is-open')).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath(`play-${viewport.width}-dossier.png`), fullPage: true });
  }
});


test('MapLibre PLAY captures continent, Mediterranean and detail zoom evidence when WebGL is available', async ({ page }, testInfo) => {
  await page.addInitScript(() => { window.__SEACOMMONS_E2E_MAP__ = true; });
  const rendererErrors = [];
  page.on('pageerror', error => rendererErrors.push(`pageerror: ${error.message}`));
  page.on('console', message => { if (message.type() === 'error' || message.text().includes('[PLAY_MAP_RENDERER_FALLBACK]')) rendererErrors.push(`console: ${message.text()}`); });
  for (const viewport of [{ width: 1280, height: 800 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport);
    await page.goto(PUBLIC_PLAY_URL);
    await expect.poll(async () =>
      (await page.locator('.maplibregl-canvas').count()) + (await page.locator('.leaflet-container').count())
    ).toBeGreaterThan(0);
    if (!(await page.locator('.maplibregl-canvas').count())) {
      await page.locator('.maplibregl-canvas').waitFor({ state: 'attached', timeout: 2500 }).catch(() => {});
    }
    if (!(await page.locator('.maplibregl-canvas').count())) {
      testInfo.annotations.push({ type: 'webgl-unavailable', description: `${viewport.width}: Leaflet fallback; MapLibre visual gate NOT satisfied` });
      // Opt-in release gate: a green fallback-only CI run is not proof of MapLibre.
      // Run with SEACOMMONS_REQUIRE_WEBGL=1 on a WebGL-capable browser runner.
      if (process.env.SEACOMMONS_REQUIRE_WEBGL === '1') {
        const diagnostics = await page.evaluate(() => {
          const probe = document.createElement('canvas');
          const webgl2 = probe.getContext('webgl2');
          const webgl = webgl2 || probe.getContext('webgl');
          return {
            webglAvailable: Boolean(webgl),
            webglVersion: webgl?.getParameter(webgl.VERSION) || null,
            fallbackMarkerCount: document.querySelectorAll('.seacommons-fallback-marker').length,
            mapError: document.querySelector('.play-map-error')?.textContent?.trim() || null,
            forcedFallback: window.__SEACOMMONS_FORCE_MAP_FALLBACK__ === true,
          };
        });
        diagnostics.rendererErrors = rendererErrors.slice(-12).map(message => message.slice(0, 400));
        testInfo.annotations.push({ type: 'webgl-diagnostics', description: JSON.stringify(diagnostics) });
        throw new Error(`MapLibre WebGL renderer missing at ${viewport.width}x${viewport.height}; diagnostics=${JSON.stringify(diagnostics)}; release visual gate failed`);
      }
      continue;
    }
    const canvas = page.locator('.maplibregl-canvas');
    await expect(canvas).toBeVisible();
    const zoomIn = page.locator('.maplibregl-ctrl-zoom-in');
    await expect(zoomIn).toBeVisible();
    let currentZoomSteps = 0;
    for (const [label, targetZoomSteps] of [['continent', 0], ['mediterranean', 2], ['detail', 4]]) {
      // Targets are absolute offsets from the initial 3.55 zoom, not cumulative clicks.
      const delta = targetZoomSteps - currentZoomSteps;
      expect(delta).toBeGreaterThanOrEqual(0);
      for (let i = 0; i < delta; i++) await zoomIn.click();
      currentZoomSteps = targetZoomSteps;
      // Wait for actual MapLibre rendering, not an arbitrary animation delay.
      // A screenshot of a pending tile/source is not valid visual evidence.
      await expect.poll(() => page.evaluate(() => {
        const map = window.__SEACOMMONS_PLAY_MAP__;
        return Boolean(map && map.loaded() && map.isSourceLoaded('play-incidents'));
      }), { timeout: 15000, intervals: [250, 500, 1000] }).toBe(true);
      await page.screenshot({ path: testInfo.outputPath(`play-maplibre-${viewport.width}-${label}.png`), fullPage: true });
      await expect(page.locator('.play-map-error')).toHaveCount(0);
    }
  }
  // This visual artifact test does not prove cluster expansion or dossier completeness.
  // A dedicated WebGL-enabled cluster interaction gate is still required before release.
});


test('MapLibre cluster expansion preserves every synthetic archive dossier', async ({ page }) => {
  test.skip(process.env.SEACOMMONS_REQUIRE_WEBGL !== '1', 'Cluster interaction requires the dedicated WebGL-enabled release gate');
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.addInitScript(() => { window.__SEACOMMONS_E2E_MAP__ = true; });
  const rendererErrors = [];
  const failedWorkerRequests = [];
  page.on('response', response => {
    if (/maplibre-gl-worker/i.test(response.url()) && response.status() >= 400) {
      failedWorkerRequests.push(`${response.status()} ${response.url()}`);
    }
  });
  page.on('requestfailed', request => {
    if (/maplibre-gl-worker/i.test(request.url())) {
      failedWorkerRequests.push(`${request.failure()?.errorText || 'request failed'} ${request.url()}`);
    }
  });
  page.on('pageerror', error => rendererErrors.push(`pageerror: ${error.message}`));
  page.on('console', message => {
    if (message.type() === 'error' || message.text().includes('PLAY_MAP_RENDERER_FALLBACK')) {
      rendererErrors.push(`console: ${message.text()}`);
    }
  });
  await page.goto(PUBLIC_PLAY_URL);
  try {
    await expect.poll(() => page.evaluate(() => Boolean(window.__SEACOMMONS_PLAY_MAP__)), {
      timeout: 15000,
      intervals: [250, 500, 1000],
    }).toBe(true);
  } catch (error) {
    const diagnostic = await page.evaluate(() => ({
      e2eFlag: window.__SEACOMMONS_E2E_MAP__ === true,
      mapExposed: Boolean(window.__SEACOMMONS_PLAY_MAP__),
      maplibreCanvases: document.querySelectorAll('.maplibregl-canvas').length,
      fallbackMaps: document.querySelectorAll('.leaflet-container').length,
      visibleError: document.querySelector('.play-map-error')?.textContent?.trim() || null,
    }));
    throw new Error(`MapLibre cluster gate failed: ${JSON.stringify({ ...diagnostic, errors: rendererErrors.slice(-10).map(item => item.slice(0, 350)), failedWorkerRequests })}; cause=${error.message}`);
  }
  // Map construction alone is not a functional cluster gate: require installed layers.
  await expect.poll(() => page.evaluate(() => {
    const map = window.__SEACOMMONS_PLAY_MAP__;
    return Boolean(map?.getLayer('play-clusters') && map?.getSource('play-incidents'));
  }), { timeout: 15000, intervals: [250, 500, 1000] }).toBe(true);
  // Verify the upstream archive contract before diagnosing MapLibre rendering.
  const archiveList = page.locator('.play-cases__list');
  for (const title of ['Historical distress', 'Historical safety report', 'Reviewed correlated case']) {
    await expect(archiveList.getByText(title, { exact: true })).toBeVisible();
  }
  // An installed source is not necessarily loaded; keep this a hard WebGL gate.
  await expect.poll(() => page.evaluate(() => {
    const map = window.__SEACOMMONS_PLAY_MAP__;
    return Boolean(map?.getSource('play-incidents') && map?.isSourceLoaded('play-incidents'));
  }), { timeout: 15000, intervals: [250, 500, 1000] }).toBe(true);
  expect(failedWorkerRequests, 'MapLibre worker must not return 404 or fail to load').toEqual([]);
  // A layer can exist before the GeoJSON worker has finished setData. At zoom 1,
  // all three historical fixtures are close enough to test low-zoom grouping.
  await page.evaluate(() => window.__SEACOMMONS_PLAY_MAP__.jumpTo({ center: [15.1, 35.6], zoom: 1 }));
  const readCluster = () => page.evaluate(() => {
    const map = window.__SEACOMMONS_PLAY_MAP__;
    const feature = map.queryRenderedFeatures({ layers: ['play-clusters'] })
      .find(item => item.properties?.point_count >= 3);
    if (!feature) return null;
    const point = map.project(feature.geometry.coordinates);
    return { x: point.x, y: point.y, count: feature.properties.point_count };
  });
  try {
    await expect.poll(readCluster, { timeout: 15000, intervals: [250, 500, 1000] }).not.toBeNull();
  } catch (error) {
    // Source readiness and rendered visibility are different evidence layers.
    // Preserve a bounded diagnostic without exposing any real-world coordinates.
    const diagnostics = await page.evaluate(() => {
      const map = window.__SEACOMMONS_PLAY_MAP__;
      const source = map?.getSource('play-incidents');
      const rendered = map?.queryRenderedFeatures({ layers: ['play-clusters'] }) || [];
      const sourceFeatures = map?.querySourceFeatures('play-incidents') || [];
      return {
        zoom: map?.getZoom(),
        styleLoaded: map?.isStyleLoaded(),
        sourceLoaded: map?.isSourceLoaded('play-incidents'),
        sourcePresent: Boolean(source),
        clusterLayerVisible: map?.getLayoutProperty('play-clusters', 'visibility') !== 'none',
        sourceFeatureCount: sourceFeatures.length,
        sourceClusterCounts: sourceFeatures.filter(f => f.properties?.cluster).map(f => f.properties?.point_count).slice(0, 20),
        renderedClusterCounts: rendered.map(f => f.properties?.point_count).slice(0, 20),
        fixtureIds: sourceFeatures.filter(f => !f.properties?.cluster).map(f => f.properties?.incident_id).filter(Boolean).slice(0, 10),
      };
    });
    throw new Error(`MapLibre cluster evidence mismatch: ${JSON.stringify(diagnostics)}; cause=${error.message}`);
  }
  const cluster = await readCluster();
  expect(cluster, 'three nearby historical observations must form a low-zoom cluster').not.toBeNull();
  expect(cluster.count).toBe(3);
  const canvas = page.locator('.maplibregl-canvas');
  const box = await canvas.boundingBox();
  await page.mouse.click(box.x + cluster.x, box.y + cluster.y);
  await expect.poll(() => page.evaluate(() => window.__SEACOMMONS_PLAY_MAP__.getZoom())).toBeGreaterThan(1);
  // At detail zoom the original observations must remain individually selectable.
  await page.evaluate(() => window.__SEACOMMONS_PLAY_MAP__.jumpTo({ center: [15.1, 35.6], zoom: 10 }));
  const observations = [
    ['play-humanitarian-1', [14.1, 35.2], 'Historical distress'],
    ['play-maritime-1', [15.1, 36.0], 'Historical safety report'],
    ['play-correlated-1', [16.0, 35.8], 'Reviewed correlated case'],
  ];
  for (const [id, coordinates, title] of observations) {
    const point = await page.evaluate(coords => {
      const map = window.__SEACOMMONS_PLAY_MAP__;
      map.jumpTo({ center: coords, zoom: 10 });
      const p = map.project(coords);
      return { x: p.x, y: p.y };
    }, coordinates);
    await expect.poll(() => page.evaluate(coords => {
      const map = window.__SEACOMMONS_PLAY_MAP__;
      return map.queryRenderedFeatures(map.project(coords), { layers: ['play-incidents', 'play-vessels'] })
        .some(feature => feature.properties?.incident_id);
    }, coordinates)).toBe(true);
    const bounds = await canvas.boundingBox();
    await page.mouse.click(bounds.x + point.x, bounds.y + point.y);
    await expect(page.locator('.play-evidence.is-open h2')).toContainText(title);
    await expect(page.locator('.play-evidence.is-open')).toBeVisible();
  }
});
