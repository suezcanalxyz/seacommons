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
