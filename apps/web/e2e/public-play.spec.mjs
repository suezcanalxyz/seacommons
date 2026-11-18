import { expect, test } from '@playwright/test';

import { installDeterministicRoutes, playIncidents, PUBLIC_PLAY_URL } from './support/publicFixtures.mjs';

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
    await expect(page.locator('.play-map-message.is-error')).toHaveCount(0);
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
  test.slow();
  await page.addInitScript(() => { window.__SEACOMMONS_EXPOSE_PLAY_MAP__ = true; });
  const rendererErrors = [];
  page.on('pageerror', error => rendererErrors.push(`pageerror: ${error.message}`));
  page.on('console', message => { if (message.type() === 'error' || message.text().includes('[PLAY_MAP_RENDERER_FALLBACK]')) rendererErrors.push(`console: ${message.text()}`); });
  for (const viewport of [{ width: 1280, height: 800 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport);
    await page.goto(PUBLIC_PLAY_URL);
    try {
      await expect.poll(async () =>
        (await page.locator('.maplibregl-canvas').count()) + (await page.locator('.leaflet-container').count())
      , { timeout: 25_000 }).toBeGreaterThan(0);
    } catch (error) {
      throw new Error(`PLAY renderer did not mount: ${JSON.stringify(rendererErrors.slice(-12).map(message => message.slice(0, 400)))}; cause=${error.message}`);
    }
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
            mapError: document.querySelector('.play-map-message.is-error')?.textContent?.trim() || null,
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
    await expect.poll(() => page.evaluate(() => {
      const style = window.__SEACOMMONS_PLAY_MAP__?.getStyle();
      return Boolean(style?.sources?.baseMap && style?.sources?.satelliteContext
        && style?.layers?.some(layer => layer.id === 'base-map')
        && style?.layers?.some(layer => layer.id === 'satellite-context'));
    })).toBe(true);
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
      if (label === 'detail') {
        await expect.poll(() => page.evaluate(() => window.__SEACOMMONS_PLAY_MAP__
          .queryRenderedFeatures({ layers: ['play-vessels'] })
          .some((feature) => feature.properties?.incident_id === 'play-maritime-1'))).toBe(true);
      }
      await page.screenshot({ path: testInfo.outputPath(`play-maplibre-${viewport.width}-${label}.png`), fullPage: true });
      await expect(page.locator('.play-map-message.is-error')).toHaveCount(0);
    }
  }
  // This visual artifact test does not prove cluster expansion or dossier completeness.
  // A dedicated WebGL-enabled cluster interaction gate is still required before release.
});


test('MapLibre cluster expansion preserves every synthetic archive dossier', async ({ page }) => {
  test.skip(process.env.SEACOMMONS_REQUIRE_WEBGL !== '1', 'Cluster interaction requires the dedicated WebGL-enabled release gate');
  test.slow();
  await page.addInitScript(() => { window.__SEACOMMONS_EXPOSE_PLAY_MAP__ = true; });
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
  for (const viewport of [{ width: 1280, height: 800 }, { width: 390, height: 844 }]) {
  await page.setViewportSize(viewport);
  await page.goto(PUBLIC_PLAY_URL);
  try {
    await expect.poll(() => page.evaluate(() => Boolean(window.__SEACOMMONS_PLAY_MAP__)), {
      timeout: 15000,
      intervals: [250, 500, 1000],
    }).toBe(true);
  } catch (error) {
    const diagnostic = await page.evaluate(() => ({
      e2eFlag: window.__SEACOMMONS_EXPOSE_PLAY_MAP__ === true,
      mapExposed: Boolean(window.__SEACOMMONS_PLAY_MAP__),
      maplibreCanvases: document.querySelectorAll('.maplibregl-canvas').length,
      fallbackMaps: document.querySelectorAll('.leaflet-container').length,
      visibleError: document.querySelector('.play-map-message.is-error')?.textContent?.trim() || null,
    }));
    throw new Error(`MapLibre cluster gate failed at ${viewport.width}x${viewport.height}: ${JSON.stringify({ ...diagnostic, errors: rendererErrors.slice(-10).map(item => item.slice(0, 350)), failedWorkerRequests })}; cause=${error.message}`);
  }
  // Map construction alone is not a functional cluster gate: require installed layers.
  try {
    await expect.poll(() => page.evaluate(() => {
      const map = window.__SEACOMMONS_PLAY_MAP__;
      return Boolean(map?.getLayer('play-clusters') && map?.getSource('play-incidents'));
    }), { timeout: 25_000, intervals: [250, 500, 1000] }).toBe(true);
  } catch (error) {
    const diagnostic = await page.evaluate(() => ({
      mapExposed: Boolean(window.__SEACOMMONS_PLAY_MAP__),
      maplibreCanvases: document.querySelectorAll('.maplibregl-canvas').length,
      fallbackMaps: document.querySelectorAll('.leaflet-container').length,
      visibleError: document.querySelector('.play-map-message.is-error')?.textContent?.trim() || null,
    }));
    throw new Error(`PLAY layers did not install: ${JSON.stringify({ ...diagnostic, errors: rendererErrors.slice(-12).map(item => item.slice(0, 400)), failedWorkerRequests })}; cause=${error.message}`);
  }
  // Verify the upstream archive contract before diagnosing MapLibre rendering.
  const archiveList = page.locator('.play-cases__list');
  for (const title of ['Historical distress', 'Historical safety report', 'Reviewed correlated case']) {
    // The mobile archive panel is intentionally collapsed until opened; verify fixture presence, not visibility.
    await expect(archiveList.getByText(title, { exact: true })).toHaveCount(1);
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
    throw new Error(`MapLibre cluster evidence mismatch at ${viewport.width}x${viewport.height}: ${JSON.stringify(diagnostics)}; cause=${error.message}`);
  }
  const cluster = await readCluster();
  expect(cluster, 'three nearby historical observations must form a low-zoom cluster').not.toBeNull();
  expect(cluster.count).toBe(3);
  // A rendered cluster count is not evidence that all canonical observations
  // remain recoverable. Inspect its source leaves, not tiled feature counts.
  const leafIds = await page.evaluate(async () => {
    const map = window.__SEACOMMONS_PLAY_MAP__;
    const rendered = map.queryRenderedFeatures({ layers: ['play-clusters'] })
      .find(item => item.properties?.point_count === 3);
    if (!rendered) throw new Error('Expected three-observation cluster is absent');
    const source = map.getSource('play-incidents');
    const leaves = await source.getClusterLeaves(rendered.properties.cluster_id, 10, 0);
    return leaves.map(item => item.properties?.incident_id).sort();
  });
  expect(leafIds).toEqual([
    'play-correlated-1',
    'play-humanitarian-1',
    'play-maritime-1',
  ]);
  // Diagnose real pointer interception without force-clicking or bypassing overlays.
  // Only DOM tag/class metadata is reported; never expose case coordinates.
  const assertMapHitTarget = async (x, y, label) => {
    const hit = await page.evaluate(({ x, y }) => {
      const element = document.elementFromPoint(x, y);
      const canvas = document.querySelector('.maplibregl-canvas');
      return {
        canvasReceivesPointer: Boolean(canvas && (element === canvas || canvas.contains(element))),
        targetTag: element?.tagName || null,
        targetClass: typeof element?.className === 'string' ? element.className.slice(0, 160) : null,
        canvasPointerEvents: canvas ? getComputedStyle(canvas).pointerEvents : null,
      };
    }, { x, y });
    expect(hit.canvasReceivesPointer, `MapLibre ${label} click intercepted: ${JSON.stringify(hit)}`).toBe(true);
  };
  const canvas = page.locator('.maplibregl-canvas');
  const box = await canvas.boundingBox();
  expect(box, 'MapLibre canvas must have a measurable click target').not.toBeNull();
  await assertMapHitTarget(box.x + cluster.x, box.y + cluster.y, 'cluster');
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
    // A map jump can leave the previous frame's rendered features visible.
    // Require the *expected* canonical ID at the click coordinate; another
    // incident being present is not evidence that this dossier is selectable.
    try {
      await expect.poll(() => page.evaluate(({ coords, expectedId }) => {
        const map = window.__SEACOMMONS_PLAY_MAP__;
        if (map.isMoving()) return false;
        return map.queryRenderedFeatures(map.project(coords), { layers: ['play-incidents', 'play-vessels'] })
          .some(feature => feature.properties?.incident_id === expectedId);
      }, { coords: coordinates, expectedId: id }), {
        timeout: 15000,
        intervals: [100, 250, 500],
        message: `Expected canonical PLAY observation ${id} to be rendered at detail zoom`,
      }).toBe(true);
    } catch (error) {
      // Preserve the failing assertion: inspect source-vs-rendered evidence,
      // tile readiness and layer filters instead of forcing a click or hiding loss.
      const diagnostic = await page.evaluate(({ coords, expectedId }) => {
        const map = window.__SEACOMMONS_PLAY_MAP__;
        const source = map.getSource('play-incidents');
        const sourceFeatures = map.querySourceFeatures('play-incidents');
        const rendered = map.queryRenderedFeatures(map.project(coords), { layers: ['play-incidents', 'play-vessels'] });
        return {
          expectedId, zoom: map.getZoom(), center: map.getCenter().toArray(),
          moving: map.isMoving(), tilesLoaded: map.areTilesLoaded(), loaded: map.loaded(),
          sourcePresent: Boolean(source), sourceCount: sourceFeatures.length,
          sourceIds: sourceFeatures.map(f => f.properties?.incident_id).filter(Boolean).slice(0, 20),
          renderedIds: rendered.map(f => f.properties?.incident_id).filter(Boolean),
          layers: ['play-incidents', 'play-vessels'].map(layer => ({
            id: layer, visibility: map.getLayoutProperty(layer, 'visibility') ?? 'visible',
            filter: map.getFilter(layer),
          })),
        };
      }, { coords: coordinates, expectedId: id });
      throw new Error(`PLAY canonical detail-render gate: ${JSON.stringify(diagnostic)}; cause=${error.message}`);
    }
    // Reproject after the renderer settles; the earlier point may be stale.
    const clickPoint = await page.evaluate(coords => {
      const map = window.__SEACOMMONS_PLAY_MAP__;
      const p = map.project(coords);
      return { x: p.x, y: p.y };
    }, coordinates);
    // A docked case dossier may legitimately cover part of the map. Recenter
    // the observation into the actual unobstructed map viewport before a real
    // pointer click; never force-click through an overlay or skip the dossier.
    const safePoint = await page.evaluate(coords => {
      const map = window.__SEACOMMONS_PLAY_MAP__;
      const canvas = map.getCanvas();
      const rect = canvas.getBoundingClientRect();
      const overlays = [...document.querySelectorAll('.play-evidence, .play-cartographic-legend, .play-all-badge')]
        .map(el => el.getBoundingClientRect())
        .filter(r => r.width > 0 && r.height > 0);
      // Sample the *actual* interactive viewport rather than six hard-coded
      // points: responsive docks may leave a narrow but valid map strip.
      const candidates = [];
      for (let fy = 0.10; fy <= 0.90; fy += 0.10) {
        for (let fx = 0.10; fx <= 0.90; fx += 0.10) {
          candidates.push({ x: rect.width * fx, y: rect.height * fy });
        }
      }
      const diagnostics = candidates.map(p => {
        const x = rect.left + p.x, y = rect.top + p.y;
        const hit = document.elementFromPoint(x, y);
        const blockedByOverlay = overlays.some(r => x >= r.left && x <= r.right && y >= r.top && y <= r.bottom);
        return { ...p, hit: hit?.className?.baseVal ?? hit?.className ?? hit?.tagName ?? null,
          canvasHit: hit === canvas || canvas.contains(hit), blockedByOverlay };
      });
      const safe = diagnostics.find(p => p.canvasHit && !p.blockedByOverlay);
      if (!safe) {
        throw new Error('No unobstructed PLAY map viewport for real pointer selection: ' +
          JSON.stringify({ viewport: { width: rect.width, height: rect.height },
            overlays: overlays.map(r => ({ x: r.x, y: r.y, width: r.width, height: r.height })),
            samples: diagnostics.filter((_, i) => i % 10 === 0) }));
      }
      const current = map.project(coords);
      map.panBy([current.x - safe.x, current.y - safe.y], { duration: 0 });
      return safe;
    }, coordinates);
    await expect.poll(() => page.evaluate(({ coords, expectedId }) => {
      const map = window.__SEACOMMONS_PLAY_MAP__;
      if (map.isMoving()) return false;
      return map.queryRenderedFeatures(map.project(coords), { layers: ['play-incidents', 'play-vessels'] })
        .some((feature) => feature.properties?.incident_id === expectedId);
    }, { coords: coordinates, expectedId: id }), { timeout: 15_000, intervals: [100, 250, 500] }).toBe(true);
    const bounds = await canvas.boundingBox();
    const adjusted = await page.evaluate(coords => window.__SEACOMMONS_PLAY_MAP__.project(coords), coordinates);
    await assertMapHitTarget(bounds.x + adjusted.x, bounds.y + adjusted.y, id);
    await page.evaluate(() => {
      window.__SEACOMMONS_LAST_PLAY_CLICK__ = null;
      const map = window.__SEACOMMONS_PLAY_MAP__;
      map.once('click', (event) => {
        window.__SEACOMMONS_LAST_PLAY_CLICK__ = {
          point: { x: event.point.x, y: event.point.y },
          renderedIds: map.queryRenderedFeatures(event.point, { layers: ['play-incidents', 'play-vessels'] })
            .map((feature) => feature.properties?.incident_id)
            .filter(Boolean),
        };
      });
    });
    await page.mouse.click(bounds.x + adjusted.x, bounds.y + adjusted.y);
    try {
      await expect(page.locator('.play-evidence.is-open h2')).toContainText(title);
    } catch (error) {
      const clickDiagnostic = await page.evaluate(() => window.__SEACOMMONS_LAST_PLAY_CLICK__);
      throw new Error(`PLAY pointer selection failed for ${id}: ${JSON.stringify(clickDiagnostic)}; cause=${error.message}`);
    }
    await expect(page.locator('.play-evidence.is-open')).toBeVisible();
  }
  }
});

test('MapLibre asynchronous worker failure activates the interactive archive fallback', async ({ page }) => {
  test.skip(process.env.SEACOMMONS_REQUIRE_WEBGL !== '1', 'Runtime renderer failure requires the dedicated WebGL-enabled release gate');
  await page.addInitScript(() => { window.__SEACOMMONS_EXPOSE_PLAY_MAP__ = true; });
  await page.goto(PUBLIC_PLAY_URL);
  await expect.poll(
    () => page.evaluate(() => Boolean(window.__SEACOMMONS_PLAY_MAP__?.getLayer('play-incidents'))),
    { timeout: 25_000, intervals: [250, 500, 1000] },
  ).toBe(true);
  await page.evaluate(() => {
    window.__SEACOMMONS_PLAY_MAP__.fire('error', {
      error: new Error('MapLibre worker terminated unexpectedly'),
    });
  });
  await expect(page.locator('.leaflet-container')).toBeVisible();
  await expect(page.locator('.seacommons-fallback-marker')).toHaveCount(3);
  await expect(page.locator('.play-map-message.is-error')).toHaveCount(0);
});

async function openOverlapPickerAt(page, coordinates, targetPoint = { x: 195, y: 150 }) {
  await page.evaluate(({ coords, target }) => {
    const map = window.__SEACOMMONS_PLAY_MAP__;
    map.jumpTo({ center: coords, zoom: 10, padding: { top: 0, bottom: 0, left: 0, right: 0 } });
    const projected = map.project(coords);
    map.panBy([projected.x - target.x, projected.y - target.y], { duration: 0 });
  }, { coords: coordinates, target: targetPoint });
  await expect.poll(() => page.evaluate((coords) => {
    const map = window.__SEACOMMONS_PLAY_MAP__;
    if (map.isMoving()) return 0;
    return new Set(map.queryRenderedFeatures(map.project(coords), { layers: ['play-incidents', 'play-vessels'] })
      .map((feature) => feature.properties?.incident_id)
      .filter(Boolean)).size;
  }, coordinates), { timeout: 15_000, intervals: [100, 250, 500] }).toBeGreaterThan(1);
  const renderedPoint = await page.evaluate((coords) => {
    const projected = window.__SEACOMMONS_PLAY_MAP__.project(coords);
    return { x: projected.x, y: projected.y };
  }, coordinates);
  const bounds = await page.locator('.maplibregl-canvas').boundingBox();
  await page.mouse.click(bounds.x + renderedPoint.x, bounds.y + renderedPoint.y);
  const picker = page.getByRole('dialog', { name: 'Overlapping archive records' });
  await expect(picker).toBeVisible();
  return picker;
}

test('MapLibre overlapping archive records stay selectable above an open mobile dossier', async ({ page }) => {
  test.skip(process.env.SEACOMMONS_REQUIRE_WEBGL !== '1', 'Overlapping feature selection requires the dedicated WebGL-enabled release gate');
  await page.setViewportSize({ width: 390, height: 844 });
  const rendererErrors = [];
  page.on('pageerror', (error) => rendererErrors.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error') rendererErrors.push(message.text());
  });
  const colocated = {
    ...playIncidents[1],
    incident_id: 'play-maritime-colocated-2',
    title: 'Co-located safety report',
    reported_at: '2026-09-06T11:05:00Z',
  };
  await page.unroute('**/api/v1/**');
  await installDeterministicRoutes(page, { playIncidents: [...playIncidents, colocated] });
  await page.addInitScript(() => { window.__SEACOMMONS_EXPOSE_PLAY_MAP__ = true; });
  await page.goto(PUBLIC_PLAY_URL);
  await expect.poll(
    () => page.evaluate(() => Boolean(window.__SEACOMMONS_PLAY_MAP__?.getLayer('play-incidents'))),
    { timeout: 25_000, intervals: [250, 500, 1000] },
  ).toBe(true);
  await page.getByRole('navigation', { name: 'Play navigation' }).getByRole('button', { name: 'Archive' }).click();
  await page.locator('.play-cases__list').getByText('Historical distress', { exact: true }).click();
  await expect(page.locator('.play-evidence.is-open h2')).toContainText('Historical distress');
  const picker = await openOverlapPickerAt(page, [15.1, 36.0]);
  const firstChoice = picker.getByRole('button', { name: /Historical safety report/ });
  await expect(firstChoice).toBeInViewport();
  expect(await firstChoice.evaluate((button) => {
    const bounds = button.getBoundingClientRect();
    const hit = document.elementFromPoint(bounds.left + bounds.width / 2, bounds.top + bounds.height / 2);
    return hit === button || button.contains(hit);
  })).toBe(true);
  await picker.getByRole('button', { name: 'Co-located safety report' }).click();
  await expect(page.locator('.play-evidence.is-open h2')).toContainText('Co-located safety report');
  await expect(page.locator('.maplibregl-canvas')).toBeVisible();
  await expect(page.locator('.play-map-message.is-error')).toHaveCount(0);
  expect(rendererErrors.filter((message) => /play-vessels|icon-size|PLAY_MAP_RENDERER_FALLBACK/.test(message))).toEqual([]);
});

test('MapLibre large overlap groups keep first and last dossier choices accessible', async ({ page }) => {
  test.skip(process.env.SEACOMMONS_REQUIRE_WEBGL !== '1', 'Large overlap selection requires the dedicated WebGL-enabled release gate');
  test.slow();
  await page.setViewportSize({ width: 390, height: 844 });
  const colocated = Array.from({ length: 20 }, (_, index) => ({
    ...playIncidents[1],
    incident_id: `play-maritime-colocated-${index + 2}`,
    title: `Co-located safety report ${String(index + 1).padStart(2, '0')}`,
    reported_at: `2026-09-06T11:${String(index + 1).padStart(2, '0')}:00Z`,
  }));
  await page.unroute('**/api/v1/**');
  await installDeterministicRoutes(page, { playIncidents: [...playIncidents, ...colocated] });
  await page.addInitScript(() => { window.__SEACOMMONS_EXPOSE_PLAY_MAP__ = true; });
  await page.goto(PUBLIC_PLAY_URL);
  await expect.poll(
    () => page.evaluate(() => Boolean(window.__SEACOMMONS_PLAY_MAP__?.getLayer('play-incidents'))),
    { timeout: 25_000, intervals: [250, 500, 1000] },
  ).toBe(true);
  const picker = await openOverlapPickerAt(page, [15.1, 36.0]);
  const pickerBounds = await picker.boundingBox();
  expect(pickerBounds.y).toBeGreaterThanOrEqual(0);
  expect(pickerBounds.y + pickerBounds.height).toBeLessThanOrEqual(844);
  const records = picker.locator('.play-overlap-picker__records');
  await expect(records).toBeVisible();
  expect(await records.evaluate((node) => node.scrollHeight > node.clientHeight)).toBe(true);
  const firstChoice = records.getByRole('button', { name: /Co-located safety report 20/ });
  await expect(firstChoice).toBeInViewport();
  const lastChoice = records.getByRole('button', { name: /Historical safety report/ });
  await lastChoice.scrollIntoViewIfNeeded();
  await expect(lastChoice).toBeInViewport();
  await lastChoice.click();
  await expect(page.locator('.play-evidence.is-open h2')).toContainText('Historical safety report');
});

test('PLAY displays reviewed attack dossiers with dated public sources', async ({ page }) => {
  const { readFile } = await import('node:fs/promises');
  const archive = await readFile(new URL('../public/archive/reviewed-cases.json', import.meta.url), 'utf8');
  await page.route('**/archive/reviewed-cases.json', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: archive,
  }));
  await page.goto(PUBLIC_PLAY_URL);
  await page.getByRole('button', { name: 'ATTACKS', exact: true }).click();
  await page.getByRole('button', { name: /CONTSHIP JET/ }).click();
  const dossier = page.locator('.play-evidence.is-open');
  await expect(dossier.getByText('Reported area · Black Sea near Cape Kaliakra, off Bulgaria')).toBeVisible();
  await expect(dossier.getByRole('button', { name: 'Locate on map +' })).toBeDisabled();
  await expect(dossier.getByRole('link', { name: 'Original source' })).toHaveCount(2);
});
