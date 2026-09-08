import { expect, test } from '@playwright/test';

import { installDeterministicRoutes, PUBLIC_LIVE_URL } from './support/publicFixtures.mjs';

test.beforeEach(async ({ page }) => {
  await installDeterministicRoutes(page);
});

test('public Live shell renders on the real public-host code path', async ({ page }) => {
  await page.goto(PUBLIC_LIVE_URL);
  await expect(page.locator('main.cop-shell.is-live-mode')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Live feed' })).toBeVisible();
});

test('Live semantics keep Humanitarian and Maritime as the public macro split', async ({ page }) => {
  await page.goto(PUBLIC_LIVE_URL);
  await page.getByRole('button', { name: 'Expand signal categories' }).click();

  const categories = page.getByRole('group', { name: 'Signal categories' });
  await expect(categories).toBeVisible();
  await expect(categories.getByRole('link', { name: /^Humanitarian/ })).toBeVisible();
  await expect(categories.getByRole('link', { name: /^Maritime/ })).toBeVisible();
  await expect(page.getByText('Maritime Security', { exact: true })).toHaveCount(0);

  await page.getByRole('button', { name: 'Expand Maritime' }).click();
  await expect(categories.getByRole('link', { name: /^Safety/ })).toBeVisible();
  await expect(page.getByText('Not under command report', { exact: true })).toBeVisible();
});

test('Humanitarian public browser surface contains no vessel dossier identifiers', async ({ page }) => {
  await page.goto(PUBLIC_LIVE_URL);
  const body = await page.locator('body').innerText();
  expect(body).not.toMatch(/\bMMSI\b/i);
  expect(body).not.toMatch(/\bIMO\b/i);
  expect(body).not.toMatch(/\bcallsign\b/i);
  expect(body).not.toMatch(/tracker dossier/i);
});
