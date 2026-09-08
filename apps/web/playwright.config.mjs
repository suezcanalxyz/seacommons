import { defineConfig, devices } from '@playwright/test';

const PUBLIC_HOST_RULES = [
  'MAP live.seacommons.org 127.0.0.1',
  'MAP play.seacommons.org 127.0.0.1',
].join(',');

export default defineConfig({
  testDir: './e2e',
  testIgnore: '**/production-smoke.spec.mjs',
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    ...devices['Desktop Chrome'],
    baseURL: 'http://live.seacommons.org:4173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'off',
    launchOptions: { args: [`--host-resolver-rules=${PUBLIC_HOST_RULES}`] },
  },
  webServer: {
    command: 'VITE_APP_PROFILE=live DISABLE_HMR=true npm run dev -- --host 0.0.0.0 --port 4173 --strictPort',
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
