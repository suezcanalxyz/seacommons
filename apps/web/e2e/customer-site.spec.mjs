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
  test(`public site points to partner access without fundraising at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto('http://127.0.0.1:4173/site.html');
    await expect(page.locator('#overview')).toContainText('Partner workspace');
    await expect(page.getByText(/funding|sponsorship|six-month pilot/i)).toHaveCount(0);
    await page.locator('.hero__actions').getByRole('link', { name: /Partner workspace/ }).click();
    await expect(page).toHaveURL(/partners.html$/);
    await expect(page.getByRole('heading', { name: 'Partner workspace' })).toBeVisible();
    await expect(page.getByLabel('Work email')).toBeVisible();
    await expect(page.getByRole('navigation', { name: 'Workspace' })).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });
}
