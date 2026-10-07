import { expect, test } from '@playwright/test';

const FUTURES_URL = 'http://127.0.0.1:4173/futures.html';

const statusFixture = {
  service: 'SeaCommons',
  status: 'operational',
  live: { total: 12, operational: 9, humanitarian: 4, maritime: 8 },
  pipeline: {
    raw_observations: 240,
    parsed_events: 118,
    analysis_outputs: 43,
    maritime_episodes: 21,
    corroborated_episodes: 7,
    investigation_hypotheses: 9,
  },
  sensor_activity: {
    ais_fixes: 1000,
    radio_bursts: 80,
    radio_events: 12,
    satellite_observations: 6,
  },
};

const countsFixture = {
  total_count: 226,
  humanitarian_count: 54,
  maritime_count: 172,
  investigation_count: 14,
};

const pipelineFixture = {
  sources: [
    { family: 'ais', state: 'live', mode: 'legacy' },
    { family: 'first_party', state: 'live' },
    { family: 'partner', state: 'degraded' },
    { family: 'public_feed', state: 'live' },
    { family: 'radio', state: 'live' },
  ],
};

async function mockOperationalContracts(page) {
  await page.route('**/api/v1/status?hours=24', (route) => route.fulfill({ json: statusFixture }));
  await page.route('**/api/v1/play/counts', (route) => route.fulfill({ json: countsFixture }));
  await page.route('**/api/v1/live/pipeline', (route) => route.fulfill({ json: pipelineFixture }));
}

test('Futures overview uses canonical operational contracts', async ({ page }) => {
  await mockOperationalContracts(page);
  await page.goto(FUTURES_URL);

  await expect(page.getByRole('heading', { name: /Project state, development work/i })).toBeVisible();
  await expect(page.getByRole('region', { name: 'SeaCommons operational status' })).toContainText('226');
  await expect(page.getByText('raw observations', { exact: true })).toBeVisible();
  await expect(page.getByText('240', { exact: true })).toBeVisible();
  await expect(page.getByText('AIS', { exact: true })).toBeVisible();
  await expect(page.getByText('legacy', { exact: true })).toBeVisible();
});

test('Futures is scoped to the SeaCommons workspace only', async ({ page }) => {
  await mockOperationalContracts(page);
  await page.goto(FUTURES_URL);

  await page.locator('.future-sidebar nav').getByRole('button', { name: /^project/i }).click();
  await expect(page.getByRole('heading', { name: /One workspace, one project context/i })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'SeaCommons', exact: true })).toBeVisible();

  await expect(page.getByText('Republic', { exact: true })).toHaveCount(0);
  await expect(page.getByText('Swimming Cetacea', { exact: true })).toHaveCount(0);
  await expect(page.getByText('Case Rosa', { exact: true })).toHaveCount(0);
  await expect(page.getByText('Insulaphilia', { exact: true })).toHaveCount(0);
});

test('Futures guidebook and tools are native partner surfaces', async ({ page }) => {
  await mockOperationalContracts(page);
  await page.goto(FUTURES_URL);

  await page.locator('.future-sidebar nav').getByRole('button', { name: /^guidebook/i }).click();
  await expect(page.getByRole('heading', { name: 'Futures and access' })).toBeVisible();
  await page.getByRole('button', { name: 'Evidence model', exact: true }).click();
  await expect(page.getByText(/An observation is not an incident/i)).toBeVisible();

  await page.locator('.future-sidebar nav').getByRole('button', { name: /^tools/i }).click();
  await expect(page.getByRole('heading', { name: /Surfaces you can open/i })).toBeVisible();
  await expect(page.getByRole('link', { name: /SeaCommons Live/i })).toHaveAttribute('href', 'https://live.seacommons.org');
  await expect(page.getByRole('link', { name: /SeaCommons Play/i })).toHaveAttribute('href', 'https://play.seacommons.org');
  await expect(page.getByText('Republic', { exact: true })).toHaveCount(0);
});

test('Futures access page states final grant hierarchy without pretending auth is final', async ({ page }) => {
  await mockOperationalContracts(page);
  await page.goto(FUTURES_URL);

  await page.locator('.future-sidebar nav').getByRole('button', { name: /^access/i }).click();
  await expect(page.getByRole('heading', { name: /Full bootstrap access now/i })).toBeVisible();
  await expect(page.getByText(/organisation → SeaCommons workspace → project \/ subproject → resource or tool/i)).toBeVisible();
  await expect(page.getByText(/final Suez Supabase identity tenant/i)).toBeVisible();
});


test('Futures navigation is deep-linkable and browser-history aware', async ({ page }) => {
  await mockOperationalContracts(page);
  await page.goto(`${FUTURES_URL}?view=roadmap`);

  await expect(page.getByRole('heading', { name: /What is being built/i })).toBeVisible();
  await expect(page).toHaveURL(/view=roadmap/);

  await page.locator('.future-sidebar nav').getByRole('button', { name: /^project/i }).click();
  await expect(page.getByRole('heading', { name: /One workspace, one project context/i })).toBeVisible();
  await expect(page).toHaveURL(/view=project/);

  await page.goBack();
  await expect(page.getByRole('heading', { name: /What is being built/i })).toBeVisible();
  await expect(page).toHaveURL(/view=roadmap/);
});
