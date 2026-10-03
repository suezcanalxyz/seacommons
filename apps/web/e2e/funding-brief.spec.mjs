import { expect, test } from '@playwright/test';

test('public totals preserve missing values and identify retrieval time', async ({ page }) => {
  await page.route('**/api/v1/play/counts', (route) => route.fulfill({ json: { total_count: 12, humanitarian_count: 0, maritime_count: null } }));
  await page.goto('http://127.0.0.1:4173/site.html');
  const strip = page.getByRole('region', { name: 'SeaCommons all-time public case totals' });
  await expect(strip.locator('strong')).toHaveText(['12', '0', '—', '—']);
  await expect(page.locator('.overall-counter__context')).toContainText(/Retrieved .* UTC/);
});

test('failed public totals do not imply zero activity or continuous loading', async ({ page }) => {
  await page.route('**/api/v1/play/counts', (route) => route.fulfill({ status: 503, body: 'unavailable' }));
  await page.goto('http://127.0.0.1:4173/site.html');
  await expect(page.locator('.overall-counter__context')).toContainText('Totals currently unavailable');
  await expect(page.locator('.overall-counter strong')).toHaveText(['—', '—', '—', '—']);
});

for (const width of [1440, 390]) {
  test(`funding journey and ten-slide deck are readable at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto('http://127.0.0.1:4173/site.html');
    await expect(page.locator('#overview')).toContainText('Current stage');
    await page.locator('#funding').scrollIntoViewIfNeeded();
    await expect(page.locator('#funding')).toContainText('Months 5–6');
    await page.getByRole('link', { name: /Read the funding deck/ }).click();
    await expect(page).toHaveURL(/funding.html$/);
    await expect(page.locator('.deck-slide')).toHaveCount(10);
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Maritime evidence infrastructure');
    await expect(page.locator('#slide-5')).toContainText('Requires validation');
    await expect(page.locator('#slide-8')).toContainText('Proposed measures');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    for (const slide of await page.locator('.deck-slide').all()) {
      expect(await slide.evaluate((el) => el.scrollHeight <= el.clientHeight + 1)).toBe(true);
    }
    await page.emulateMedia({ media: 'print' });
    for (const slide of await page.locator('.deck-slide').all()) {
      expect(await slide.evaluate((el) => el.scrollHeight <= el.clientHeight + 1)).toBe(true);
    }
  });
}
