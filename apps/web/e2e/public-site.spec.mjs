import { expect, test } from '@playwright/test';

const SITE_URL = 'http://127.0.0.1:4173/site.html';

test('institutional homepage explains Humanitarian and Maritime without legacy simulation surfaces', async ({ page }) => {
  await page.goto(SITE_URL);

  await expect(page.getByRole('heading', { level: 1 })).toContainText('traceable public cases');
  await expect(page.locator('#humanitarian')).toContainText('Humanitarian');
  await expect(page.locator('#maritime')).toContainText('Maritime');

  await expect(page.getByText('Evidence in motion', { exact: true })).toHaveCount(0);
  await expect(page.getByText(/Pipeline \/ 24 h/i)).toHaveCount(0);
  await expect(page.getByText('ENGINE', { exact: true })).toHaveCount(0);
  await expect(page.getByText(/drift demonstrator/i)).toHaveCount(0);
});

test('overall strip is one all-time row with four public case totals', async ({ page }) => {
  await page.goto(SITE_URL);

  const strip = page.getByRole('region', { name: 'SeaCommons all-time public case totals' });
  await expect(strip).toBeVisible();
  for (const label of ['Overall', 'Humanitarian', 'Maritime', 'Investigations']) {
    await expect(strip.getByText(label, { exact: true })).toBeVisible();
  }
  await expect(strip.getByText(/24 h/i)).toHaveCount(0);
});

test('homepage routes readers from simple surfaces to technical documentation', async ({ page }) => {
  await page.goto(SITE_URL);

  await expect(page.locator('a[href="https://live.seacommons.org"]').first()).toBeVisible();
  await expect(page.locator('a[href="https://play.seacommons.org"]').first()).toBeVisible();
  await expect(page.locator('a[href="/docs"]').first()).toBeVisible();

  await expect(page.getByRole('heading', { name: /One pipeline/i })).toBeVisible();
  await expect(page.getByText('Source independence', { exact: true })).toBeVisible();
});
