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
  for (const label of ['ALL', 'HUMANITARIAN', 'MARITIME', 'CORRELATED', 'SATELLITE']) {
    await expect(filters.getByRole('button', { name: label })).toBeVisible();
  }

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
  await expect(dossier.getByRole('heading', { name: 'Historical distress' })).toBeVisible();
  await expect(dossier.getByText('RESOLVED', { exact: true })).toBeVisible();

  await expect(page.getByRole('slider', { name: 'Global archive timeline' })).toBeVisible();
  await expect(page.locator('.play-all-badge strong')).toHaveText('ALL');
});
