import { expect, test } from '@playwright/test';

const FUTURES_URL = 'http://127.0.0.1:4173/futures.html';

const statusFixture = {
  service: 'SeaCommons',
  status: 'operational',
  window_hours: 24,
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
  await page.route('**/api/v1/status?hours=168', (route) => route.fulfill({ json: {
    ...statusFixture, window_hours: 168, pipeline: { ...statusFixture.pipeline, raw_observations: 1680, parsed_events: 780, derived_cues: 310 },
  } }));
  await page.route('**/api/v1/play/counts', (route) => route.fulfill({ json: countsFixture }));
  await page.route('**/api/v1/live/pipeline', (route) => route.fulfill({ json: pipelineFixture }));
  await page.route('**/api/v1/futures/overall', (route) => route.fulfill({ json: {
    generated_at: '2026-10-12T12:00:00Z',
    scope: 'retained_intel_events',
    intel_record: {
      total_events: 378826, positioned_events: 378107,
      oldest_event_utc: '2026-05-01T00:00:00Z',
      newest_event_utc: '2026-10-12T12:00:00Z',
      monthly: [
        { month: '2026-05', count: 32100 },
        { month: '2026-06', count: 40100 },
        { month: '2026-10', count: 79000 },
      ],
    },
  } }));
}

test('Futures overview uses canonical operational contracts', async ({ page }) => {
  await mockOperationalContracts(page);
  await page.goto(FUTURES_URL);

  await expect(page.getByRole('heading', { name: /Understand what happens at sea/i })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Overall historical totals' })).toContainText('378,826');
  await expect(page.getByRole('group', { name: 'Analytics time window' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Overall', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('region', { name: 'Overall historical totals' })).toContainText('378,826');
  await page.getByRole('button', { name: '24 hours', exact: true }).click();
  await expect(page.getByRole('region', { name: 'SeaCommons operational status' })).toContainText('226');
  await expect(page.getByText('raw observations', { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: /From scattered observations to evidence/i })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Application pathways and maturity' })).toContainText('Coastal and island resilience');
  await expect(page.getByRole('region', { name: 'Application pathways and maturity' })).toContainText('Future vertical');
  await expect(page.getByText(/platform does not currently measure their impact or outcomes/i)).toBeVisible();
  await expect(page.getByText('Evidence stages, not equivalent incident totals.')).toBeVisible();
  await expect(page.getByText('Live', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('240', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('AIS', { exact: true })).toBeVisible();
  await expect(page.getByText('legacy', { exact: true })).toBeVisible();
});

test('Futures is scoped to the SeaCommons workspace only', async ({ page }) => {
  await mockOperationalContracts(page);
  await page.goto(FUTURES_URL);

  await page.goto(FUTURES_URL + '?view=project');
  await expect(page.getByRole('heading', { name: /What SeaCommons is building/i })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'SeaCommons', exact: true })).toBeVisible();

  await expect(page.getByText('Republic', { exact: true })).toHaveCount(0);
  await expect(page.getByText('Swimming Cetacea', { exact: true })).toHaveCount(0);
  await expect(page.getByText('Case Rosa', { exact: true })).toHaveCount(0);
  await expect(page.getByText('Insulaphilia', { exact: true })).toHaveCount(0);
});

test('Futures guidebook and tools are native partner surfaces', async ({ page }) => {
  await mockOperationalContracts(page);
  await page.goto(FUTURES_URL);

  await page.goto(FUTURES_URL + '?view=guidebook');
  await expect(page.getByRole('heading', { name: 'Futures and access' })).toBeVisible();
  await page.getByRole('button', { name: 'Evidence model', exact: true }).click();
  await expect(page.getByText(/An observation is not an incident/i)).toBeVisible();

  await page.goto(FUTURES_URL + '?view=tools');
  await expect(page.getByRole('heading', { name: /Surfaces you can open/i })).toBeVisible();
  await expect(page.getByRole('link', { name: /SeaCommons Live/i }).first()).toHaveAttribute('href', 'https://live.seacommons.org');
  await expect(page.getByRole('link', { name: /SeaCommons Play/i }).first()).toHaveAttribute('href', 'https://play.seacommons.org');
  await expect(page.getByText('Republic', { exact: true })).toHaveCount(0);
});

test('Futures access page states final grant hierarchy without pretending auth is final', async ({ page }) => {
  await mockOperationalContracts(page);
  await page.goto(FUTURES_URL);

  await page.goto(FUTURES_URL + '?view=access');
  await expect(page.getByRole('heading', { name: /Your account and workspace access/i })).toBeVisible();
  await expect(page.getByText(/organisation → SeaCommons workspace → project \/ subproject → resource or tool/i)).toBeVisible();
  await expect(page.getByText(/A grant can stop at any level/i)).toBeVisible();
});


test('Futures navigation is deep-linkable and browser-history aware', async ({ page }) => {
  await mockOperationalContracts(page);
  await page.goto(`${FUTURES_URL}?view=roadmap`);

  await expect(page.getByRole('heading', { name: /What is being built/i })).toBeVisible();
  await expect(page).toHaveURL(/view=roadmap/);

  await page.goto(FUTURES_URL + '?view=project');
  await expect(page.getByRole('heading', { name: /What SeaCommons is building/i })).toBeVisible();
  await expect(page).toHaveURL(/view=project/);

  await page.goBack();
  await expect(page.getByRole('heading', { name: /What is being built/i })).toBeVisible();
  await expect(page).toHaveURL(/view=roadmap/);
});

test('Futures Docs searches resources and opens the native partner presentation', async ({ page }) => {
  await mockOperationalContracts(page);
  await page.goto(FUTURES_URL);
  await page.goto(FUTURES_URL + '?view=documents');
  await expect(page.getByRole('heading', { name: /Documents, presentations and project knowledge|documents and presentations/i })).toBeVisible();
  await expect(page.getByText('SeaCommons partner introduction').first()).toBeVisible();
  await page.getByRole('button', { name: /view presentation/i }).click();
  await expect(page.getByRole('region', { name: 'SeaCommons partner presentation' })).toContainText('From observation to accountable evidence.');
  await page.getByRole('button', { name: /next/i }).click();
  await expect(page.getByRole('region', { name: 'SeaCommons partner presentation' })).toContainText('What can we actually know about events at sea?');
  await page.getByRole('button', { name: /close presentation/i }).click();
  await page.getByPlaceholder('Title, format or topic').fill('architecture');
  await expect(page.getByRole('region', { name: 'SeaCommons project documents' })).toContainText('System architecture');
  await expect(page.getByRole('region', { name: 'SeaCommons project documents' })).not.toContainText('Engineering roadmap');
});

test('Futures does not claim administrator grants from a browser session', async ({ page }) => {
  await mockOperationalContracts(page);
  await page.goto(FUTURES_URL + '?view=access');
  await expect(page.getByText('not asserted by frontend')).toBeVisible();
  await expect(page.getByText('OIDC identity only')).toBeVisible();
  await expect(page.getByText('full bootstrap access')).toHaveCount(0);
});

test('Futures switches equal-weight 24 hours / 7 days / Overall panels using real contracts', async ({ page }) => {
  await mockOperationalContracts(page);
  await page.goto(FUTURES_URL + '?view=overview');
  const group = page.getByRole('group', { name: 'Analytics time window' });
  await expect(group.getByRole('button', { name: 'Overall' })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('region', { name: 'Overall historical totals' })).toContainText('378,826');
  await expect(page.getByRole('region', { name: 'Overall historical totals' })).toContainText('378,107');
  await group.getByRole('button', { name: '24 hours' }).click();
  await expect(group.getByRole('button', { name: '24 hours' })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByText('raw envelopes / 24 hours')).toBeVisible();
  await expect(page.getByText('240', { exact: true }).first()).toBeVisible();
  await group.getByRole('button', { name: '7 days' }).click();
  await expect(group.getByRole('button', { name: '7 days' })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByText('raw envelopes / 7 days')).toBeVisible();
  await expect(page.getByText('1,680', { exact: true }).first()).toBeVisible();
  await group.getByRole('button', { name: 'Overall' }).click();
  await expect(page.getByRole('region', { name: 'Overall historical totals' })).toContainText('378,826');
  await expect(page.getByText('raw envelopes / 7 days')).toHaveCount(0);
});

test('Historical and Operations pages use canonical ops data and never fake unknown totals', async ({ page }) => {
  await mockOperationalContracts(page);
  await page.goto(FUTURES_URL + '?view=history');
  await expect(page.getByRole('heading', { name: /What has SeaCommons recorded over time/i })).toBeVisible();
  await expect(page.getByRole('img', { name: 'Monthly retained Intel events' })).toContainText('2026-05');
  await expect(page.getByText('2026-06')).toBeVisible();
  await page.goto(FUTURES_URL + '?view=operations');
  await expect(page.getByRole('heading', { name: /How reliably is SeaCommons working/i })).toBeVisible();
  await expect(page.getByText('AIS', { exact: true })).toBeVisible();
  await expect(page.getByText('Radio bursts', { exact: true }).first()).toBeVisible();
});

test('Overall fetches the dedicated safe historical endpoint and not private Ops APIs', async ({page}) => {
  const requested = [];
  await mockOperationalContracts(page);
  page.on('request', (request) => {
    if (request.url().includes('/api/v1/')) requested.push(request.url());
  });
  await page.goto(FUTURES_URL + '?view=overview');
  await expect(page.getByRole('region', {name:'Overall historical totals'})).toContainText('378,826');
  expect(requested.some(url=>url.includes('/api/v1/futures/overall'))).toBe(true);
  expect(requested.some(url=>url.includes('/api/v1/ops/'))).toBe(false);
});

test('Unavailable Overall is explicitly unknown, never a synthetic zero', async ({page}) => {
  await mockOperationalContracts(page);
  await page.route('**/api/v1/futures/overall', route => route.fulfill({status:503, json:{detail:'Overall temporarily unavailable'}}));
  await page.goto(FUTURES_URL + '?view=overall');
  await expect(page.getByRole('region', {name:'Overall historical totals'})).toContainText('Historical data temporarily unavailable');
  await expect(page.getByRole('region', {name:'Overall historical totals'})).toContainText('—');
});


test('Futures Platform connects software, illustrated devices and safe network contributions', async ({page}) => {
  await mockOperationalContracts(page);
  await page.goto(FUTURES_URL + '?view=platform');
  await expect(page.getByRole('heading', {name: /Software, devices and a shared method/i})).toBeVisible();
  await expect(page.getByRole('link', {name:/Live/i}).first()).toHaveAttribute('href','https://live.seacommons.org');
  await page.getByRole('button', {name:/Drifter/i}).click();
  await expect(page.getByRole('heading',{name:'Drifter'})).toBeVisible();
  await page.getByRole('tab',{name:'Specifications'}).click();
  await expect(page.getByText('GNSS/GPS position and timestamp')).toBeVisible();
  await page.goto(FUTURES_URL + '?view=contributions');
  await expect(page.getByRole('heading',{name:/A network of shared infrastructure/i})).toBeVisible();
  await expect(page.getByText(/not the intended permanent central point of failure/i)).toBeVisible();
});

test('Futures overview method describes maritime and humanitarian uses separately', async ({page})=>{
  await mockOperationalContracts(page);
  await page.goto(FUTURES_URL + '?view=overview');
  await expect(page.getByRole('heading',{name:/From scattered observations to evidence/i})).toBeVisible();
  await expect(page.getByRole('heading',{name:/Understand activity at sea/i})).toBeVisible();
  await expect(page.getByRole('heading',{name:/Investigate with care/i})).toBeVisible();
  await page.getByRole('tab',{name:/Filter/i}).click();
  await expect(page.getByRole('tabpanel')).toContainText(/identify duplicates/i);
});
