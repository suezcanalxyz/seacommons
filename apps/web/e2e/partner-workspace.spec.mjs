import { expect, test } from '@playwright/test';

const URL = 'http://127.0.0.1:4173/partners.html';
const record = { id: '11111111-1111-1111-1111-111111111111', kind: 'deck', title: 'Project deck',
  status: 'draft', owner: 'Research team', due_on: '2026-11-01', version: 1,
  created_at: '2026-10-03T13:00:00Z', updated_at: '2026-10-03T13:00:00Z',
  body: '# Private deck\nResearch brief\n---\n# Next step\nReview the evidence' };

async function mocks(page, { role = 'viewer', authorised = true, invalidCode = false } = {}) {
  let otpRequest = null;
  let recordReads = 0;
  let saved = null;
  const expires = Math.floor(Date.now() / 1000) + 3600;
  const token = [Buffer.from(JSON.stringify({ alg: 'ES256', typ: 'JWT' })).toString('base64url'),
    Buffer.from(JSON.stringify({ sub: 'partner-id', exp: expires, iat: expires - 3600 })).toString('base64url'), 'test-signature'].join('.');
  await page.route('https://partner-test.supabase.co/auth/v1/**', (route) => {
    const path = new globalThis.URL(route.request().url()).pathname;
    if (path.endsWith('/otp')) {
      otpRequest = route.request().postDataJSON();
      return route.fulfill({ json: {} });
    }
    if (path.endsWith('/verify')) {
      if (invalidCode) return route.fulfill({ status: 403, json: { code: 'otp_expired', msg: 'Expired code' } });
      return route.fulfill({ json: { access_token: token, refresh_token: 'synthetic-refresh', token_type: 'bearer',
        expires_in: 3600, expires_at: expires, user: { id: 'partner-id', email: 'partner@example.org', aud: 'authenticated', role: 'authenticated' } } });
    }
    return route.fulfill({ json: {} });
  });
  await page.route('**/api/v1/workspace/**', (route) => {
    const url = new globalThis.URL(route.request().url());
    if (url.pathname.endsWith('/me')) return route.fulfill(authorised ? {
      json: { subject: 'partner-id', email: 'partner@example.org', organization_id: 'seacommons', role, can_edit: role === 'editor' },
    } : { status: 403, json: { detail: 'Access denied' } });
    recordReads += 1;
    if (route.request().method() === 'PUT') {
      saved = route.request().postDataJSON();
      return route.fulfill({ json: { ...record, ...saved, version: 2 } });
    }
    if (url.pathname.endsWith('/history')) return route.fulfill({ json: { items: [] } });
    if (url.pathname.endsWith('/records')) return route.fulfill({ json: { items: [record], has_more: false } });
    return route.fulfill({ json: record });
  });
  return { otp: () => otpRequest, reads: () => recordReads, saved: () => saved };
}

async function login(page) {
  await page.goto(URL);
  await page.getByLabel('Work email').fill('partner@example.org');
  await page.getByRole('button', { name: 'Email me a code' }).click();
  await page.getByLabel('Email code').fill('123456');
  await page.getByRole('button', { name: 'Continue', exact: true }).click();
}

test('invalid code never opens records and OTP requests disable signup', async ({ page }) => {
  const state = await mocks(page, { invalidCode: true });
  await login(page);
  await expect(page.getByRole('alert')).toContainText('invalid or expired');
  expect(state.otp().create_user).toBe(false);
  expect(state.reads()).toBe(0);
  await expect(page.getByRole('navigation', { name: 'Workspace' })).toHaveCount(0);
});

test('a provider session without server approval never opens internal documents', async ({ page }) => {
  const state = await mocks(page, { authorised: false });
  await login(page);
  await expect(page.getByRole('alert')).toContainText('not been authorised');
  expect(state.reads()).toBe(0);
  await expect(page.getByText('Private deck', { exact: true })).toHaveCount(0);
});

test('viewers read decks and sign out without editing controls', async ({ page }) => {
  await mocks(page);
  await login(page);
  await expect(page.getByRole('navigation', { name: 'Workspace' })).toBeVisible();
  await expect(page.getByRole('button', { name: '+ New record' })).toHaveCount(0);
  await page.locator('.workspace-row').filter({ hasText: 'Project deck' }).click();
  await expect(page.getByRole('heading', { name: 'Private deck' })).toBeVisible();
  await page.getByRole('button', { name: 'Next →' }).click();
  await expect(page.getByRole('heading', { name: 'Next step' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Edit', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Sign out' }).click();
  await expect(page.getByRole('heading', { name: 'Partner workspace' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Next step' })).toHaveCount(0);
});

test('editors save an expected version and the workspace fits mobile', async ({ page }) => {
  const state = await mocks(page, { role: 'editor' });
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  await page.locator('.workspace-row').filter({ hasText: 'Project deck' }).click();
  await page.getByRole('button', { name: 'Edit', exact: true }).click();
  await page.getByRole('textbox', { name: 'Content', exact: true }).fill('# Updated working deck');
  await page.getByRole('button', { name: 'Save record' }).click();
  await expect(page.getByRole('heading', { name: 'Updated working deck' })).toBeVisible();
  expect(state.saved().version).toBe(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
