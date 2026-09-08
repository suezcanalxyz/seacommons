# Production Browser & Release Qualification v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic Chromium E2E gate for public Live/Play and a separate read-only production smoke suite.

**Architecture:** Playwright runs Vite locally while Chromium resolves `live.seacommons.org` and `play.seacommons.org` to `127.0.0.1`, so the exact public-host code paths execute without changing application code. Tests intercept public API calls and external raster tiles with bounded fixtures; production smoke uses real public hosts with no mocks and never writes data.

**Tech Stack:** React 19, Vite 6, Playwright Test/Chromium, GitHub Actions, existing public REST APIs.

**Spec:** `docs/superpowers/specs/2026-09-08-production-browser-release-qualification-v1-design.md`

## Global Constraints

- No backend/API contract changes.
- Deterministic CI must not depend on live receivers, public feeds, OSM, Esri, NASA GIBS, or MapTiler availability.
- Humanitarian browser fixtures must contain no MMSI, IMO, callsign, tracker dossier, receiver lineage, frontend URL, or raw restricted text.
- Production smoke is GET/navigation-only and is not part of ordinary PR CI.
- Audio Evidence persistence remains disabled and outside this packet.
- Outbound HTTP/SSRF consolidation remains a separate packet.

---

### Task 1: Playwright foundation and deterministic network harness

**Files:**
- Modify: `apps/web/package.json`
- Modify: `apps/web/package-lock.json`
- Create: `apps/web/playwright.config.mjs`
- Create: `apps/web/e2e/support/publicFixtures.mjs`
- Create: `apps/web/e2e/public-live.spec.mjs`

**Interfaces:**
- Produces `installDeterministicRoutes(page)` for API/raster interception.
- Produces `PUBLIC_LIVE_URL` and `PUBLIC_PLAY_URL` constants for public-host navigation.

- [x] **Step 1: Verify the browser gate is RED before setup**

Run: `cd apps/web && npm run test:e2e`
Expected: FAIL with `Missing script: "test:e2e"`.

- [x] **Step 2: Add Playwright dependency and scripts**

Run: `cd apps/web && npm install --save-dev @playwright/test`

Add scripts:
```json
"test:e2e": "playwright test --config=playwright.config.mjs",
"test:e2e:production": "playwright test --config=playwright.production.config.mjs"
```

- [x] **Step 3: Add local-public-host Playwright config**

Create `playwright.config.mjs` with Chromium only, `workers: 1`, trace on first retry, screenshots on failure, a Vite webServer on `0.0.0.0:4173`, and Chromium arg:
```js
'--host-resolver-rules=MAP live.seacommons.org 127.0.0.1,MAP play.seacommons.org 127.0.0.1'
```
Set `baseURL` to `http://live.seacommons.org:4173` and test directory `./e2e` while excluding `production-smoke.spec.mjs`.

- [x] **Step 4: Add deterministic public fixtures**

`publicFixtures.mjs` must route `/api/v1/live/*` and `/api/v1/play/*` to bounded JSON fixtures and fulfill OSM/Esri/NASA raster requests with one valid 1×1 PNG. Unhandled same-origin public API calls must return a bounded empty/healthy response rather than reaching production.

The pipeline fixture must include exactly these five families:
```js
['ais', 'first_party', 'partner', 'public_feed', 'radio']
```
The radio fixture must contain one `listen_available: true` receiver and one unavailable receiver, with no endpoint or lineage field.

- [x] **Step 5: Add minimal browser smoke test**

Create a first test that installs deterministic routes, navigates to `PUBLIC_LIVE_URL`, and expects the public shell plus `Live feed` heading to render.

Run: `cd apps/web && npx playwright install chromium && npm run test:e2e -- --grep "public Live shell"`
Expected: PASS.

- [x] **Step 6: Commit foundation**

```bash
git add apps/web/package.json apps/web/package-lock.json apps/web/playwright.config.mjs apps/web/e2e
git commit -m "test: add deterministic browser harness"
```

### Task 2: Public Live semantic and privacy E2E

**Files:**
- Modify: `apps/web/e2e/public-live.spec.mjs`
- Modify: `apps/web/e2e/support/publicFixtures.mjs`

**Interfaces:**
- Consumes `installDeterministicRoutes(page)` and public fixture payloads from Task 1.
- Proves cross-layer UI semantics without changing React production code.

- [x] **Step 1: Write RED assertions for public semantics**

Add tests that expand signal categories and assert visible `Humanitarian` and `Maritime` macro controls, then expand Maritime and assert `Safety`. Fixture one maritime safety event with `type: 'vessel_incident'` and `navigation_status: 'not_under_command'`; assert the page never renders `Maritime Security`.

Add a browser privacy assertion over `document.body.innerText`:
```js
for (const forbidden of ['MMSI 247123456', 'IMO 9876543', 'CALLSIGN-SECRET', 'tracker-secret']) {
  expect(body).not.toContain(forbidden);
}
```
The forbidden strings may exist only in a deliberately private fixture field that the public projection must never render.

- [x] **Step 2: Run RED**

Run: `cd apps/web && npm run test:e2e -- --grep "Live semantics|Humanitarian privacy"`
Expected: FAIL until all fixture routes and selectors are complete.

- [x] **Step 3: Complete only the deterministic fixture/router needed by the assertions**

Do not add data-testid attributes unless an existing accessible role/name cannot identify the element. Prefer `getByRole`, `getByText`, and existing aria labels.

- [x] **Step 4: Run GREEN**

Run: `cd apps/web && npm run test:e2e -- --grep "Live semantics|Humanitarian privacy"`
Expected: PASS.

- [x] **Step 5: Commit Live semantics**

```bash
git add apps/web/e2e
git commit -m "test: cover public live browser semantics"
```

### Task 3: Acquisition health and Listen Live browser contract

**Files:**
- Modify: `apps/web/e2e/public-live.spec.mjs`
- Modify: `apps/web/e2e/support/publicFixtures.mjs`
- Create: `apps/web/e2e/radio-panel.html`
- Create: `apps/web/e2e/radio-panel-harness.jsx`

**Interfaces:**
- Consumes the five-family pipeline fixture and receiver mesh fixture.
- The E2E-only Vite harness mounts the production `MapFloatingPanel` with a public `radio_receiver` feature; it contains no alternate business logic.
- Proves Listen controls appear only for an eligible receiver and do not imply persistence.

- [x] **Step 1: Write RED acquisition assertions**

Open the Live acquisition panel and assert the five family labels/state rows are present. Assert the radio receiver row exposes only station/provider/channel/state and does not render frontend URL or physical lineage.

Add one eligible and one ineligible receiver to the mesh fixture. The Live page proves the bounded receiver rows are rendered. `radio-panel.html` mounts the same production `MapFloatingPanel` twice through query `?eligible=1|0`; assert the eligible receiver contains `Listen live` plus the non-persistence note and the ineligible receiver does not expose the control.

- [x] **Step 2: Run RED**

Run: `cd apps/web && npm run test:e2e -- --grep "acquisition|Listen live"`
Expected: FAIL until fixture routing and receiver interaction are complete.

- [x] **Step 3: Implement the deterministic receiver-panel harness**

Create `radio-panel.html` and `radio-panel-harness.jsx` under `apps/web/e2e/`. The harness imports the production `MapFloatingPanel`, builds a public `radio_receiver` feature with `listen_available` derived only from `new URLSearchParams(location.search).get('eligible') === '1'`, and renders it with `publicMode={true}`. It must not be added to Vite production build inputs and must not modify any production component or eligibility logic.

- [x] **Step 4: Run GREEN**

Run: `cd apps/web && npm run test:e2e -- --grep "acquisition|Listen live"`
Expected: PASS.

- [x] **Step 5: Commit radio browser contract**

```bash
git add apps/web/e2e
git commit -m "test: cover live radio browser contract"
```

### Task 4: Play deterministic browser E2E

**Files:**
- Create: `apps/web/e2e/public-play.spec.mjs`
- Modify: `apps/web/e2e/support/publicFixtures.mjs`

**Interfaces:**
- Uses `PUBLIC_PLAY_URL = 'http://play.seacommons.org:4173/play.html'`.
- Uses bounded incident/count/timeline fixtures.

- [x] **Step 1: Write RED Play assertions**

Fixture one Humanitarian incident, one Maritime incident and one correlated case. Assert Play renders the archive shell, `ALL / HUMANITARIAN / MARITIME / CORRELATED / SATELLITE` controls, filters correctly, opens a selected case dossier, and keeps the global timeline control accessible.

- [x] **Step 2: Run RED**

Run: `cd apps/web && npm run test:e2e -- --grep "Play archive"`
Expected: FAIL until Play API fixture routes are complete.

- [x] **Step 3: Complete Play fixture routes**

Return bounded payloads for:
```text
/api/v1/play/incidents?limit=500&offset=0
/api/v1/play/counts
/api/v1/play/incidents/{incident_id}/timeline
```
Use `next_offset: null` to prevent pagination beyond the fixture page.

- [x] **Step 4: Run GREEN**

Run: `cd apps/web && npm run test:e2e -- --grep "Play archive"`
Expected: PASS.

- [x] **Step 5: Commit Play E2E**

```bash
git add apps/web/e2e
git commit -m "test: add play browser qualification"
```

### Task 5: Production smoke, CI gate and controller evidence

**Files:**
- Create: `apps/web/playwright.production.config.mjs`
- Create: `apps/web/e2e/production-smoke.spec.mjs`
- Modify: `.github/workflows/ci.yml`
- Modify: `docs/TESTING.md`
- Modify: `docs/current_work.md`
- Modify: `prompt.md`

**Interfaces:**
- `E2E_LIVE_URL` defaults to `https://live.seacommons.org`.
- `E2E_PLAY_URL` defaults to `https://play.seacommons.org`.
- Production smoke must not register route mocks.

- [x] **Step 1: Add production smoke config and tests**

The smoke suite must navigate Live and Play, assert each public shell renders, fetch `/api/v1/live/pipeline`, verify the five canonical families are present, and inspect `/api/v1/live/receivers/mesh?limit=64`. If at least one receiver is `listen_available`, issue a bounded GET to its Listen endpoint and assert HTTP 200 plus `Cache-Control: no-store` and `x-seacommons-persistent: false`; otherwise record the receiver-unavailable condition without fabricating success.

- [x] **Step 2: Add blocking Chromium CI job**

Add a separate `browser-e2e` job after checkout/setup-node:
```yaml
- run: npm ci
  working-directory: apps/web
- run: npx playwright install --with-deps chromium
  working-directory: apps/web
- run: npm run test:e2e
  working-directory: apps/web
```
Do not run `test:e2e:production` in PR CI.

- [x] **Step 3: Update testing/controller docs**

Document deterministic Chromium as a blocking test layer and production smoke as an explicit post-deploy qualification command. Mark Packet I implemented only after exact-head gates and production smoke pass.

- [x] **Step 4: Run release gates**

Run:
```bash
cd apps/web && npm test && npm run lint && npm run build && npm run test:e2e
cd ../edge && npm test && npx wrangler deploy --dry-run
cd ../../ && git diff --check
```
Because Packet I changes no backend runtime, run the focused public/privacy backend gate rather than the full backend suite before merge; Full CI after push remains the exact-head integration gate.

- [x] **Step 5: Run read-only production smoke**

Run: `cd apps/web && npm run test:e2e:production`
Expected: Live and Play shells pass; pipeline families pass; Listen check either verifies a real eligible receiver or reports no currently eligible receiver without failing unrelated browser semantics.

- [x] **Step 6: Commit final qualification**

```bash
git add .github/workflows/ci.yml apps/web docs/TESTING.md docs/current_work.md prompt.md
git commit -m "test: qualify public browser release path"
```

- [x] **Step 7: Exact-diff review and integration**

Review the entire spec-to-HEAD diff for accidental runtime/API behavior changes, secrets, unbounded production requests, privacy leaks, and CI dependence on external services. Fix Critical/Important findings, rerun affected gates, then merge/push only after exact-head verification.


## Final acceptance evidence

- PR #155 merged Packet I at `dce7c30`; deterministic Chromium and the production-smoke workflow were integrated.
- PR #156 merged `f9ceb46`, fixing AIS distress beacons to remain canonical `distress` even in the Maritime Safety domain.
- PR #157 merged `908dc81`, making manual `workflow_dispatch` qualification skip only the redundant full-history gitleaks action; PR/push secret scanning remains enforced.
- Manual Full CI qualification run `34258991088` completed **SUCCESS**: `repository`, `api`, `web`, `edge`, `browser-e2e`, and `browser-production-smoke` all passed.
- Production smoke used the real Live/Play hosts with no route mocks. Packet I is accepted/closed.
