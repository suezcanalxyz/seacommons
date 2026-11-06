# Experiment 2026-11-06 — Web dependency security release gate

Status: **observed CI blocker; remediation not yet implemented**. Parent #431; related #443–#445. Capability: **observed** CI detection; **experimental** remediation; **unsupported** assertion of safe public release.

## Research question and tradecraft
Can the current web dependency tree pass a reproducible security gate without breaking LIVE mobile map and PLAY timeline semantics? Intelligence tradecraft: distinguish source observations (CI findings) from inferred exposure (runtime exploitability), preserve evidence and test competing hypotheses.

## Baseline (verified 2026-11-06)
Full CI run https://github.com/suezcanalxyz/seacommons/actions/runs/42154250659: radio-dotnet, edge, API and repository jobs succeeded; web failed; browser-e2e and browser-production-smoke skipped. The previous run identified npm audit vulnerabilities involving DOMPurify (critical) and Vite (high); exact installed versions, dependency ancestry and active exploit conditions require lockfile + job-log verification. Main apps/web/package.json declares vite ^6.2.0 in both dependencies and devDependencies. **No evidence that the proposed UI changes are live.**

## Primary research register
| Source | Published / accessed | Terms | Finding / decision |
| --- | --- | --- | --- |
| https://github.com/advisories/GHSA-cg2g-xh64-v4q7 | 2026-10-12 / 2026-11-06 | Public security advisory; no dataset license | DOMPurify 3.4.4–3.4.16 affected; patched 3.4.17. Exploit requires SAFE_FOR_TEMPLATES + DOM-returning mode + shadow-root input + downstream template evaluation. **Adopt** patched dependency if installed and audit confirms. |
| https://github.com/advisories/GHSA-698v-4r3x-3vcv | Accessed 2026-11-06 | Public security advisory; no dataset license | Vite advisory flagged in preceding CI diagnosis. **Investigate** exact affected range and lockfile before choosing upgrade; do not assume a safe target. |
| https://docs.npmjs.com/cli/v10/commands/npm-audit | Accessed 2026-11-06 | Public documentation; no dataset license | Reproduce severity and dependency ancestry using npm audit --json and npm explain. **Adopt** for evidence. |
| https://docs.npmjs.com/cli/v10/commands/npm-ci | Accessed 2026-11-06 | Public documentation; no dataset license | Deterministic installation from committed lockfile. **Adopt** as verification gate. |

## Minimal reproducible experiment (not yet run)
In a clean branch checkout, run:
```sh
cd apps/web
npm ci
npm explain dompurify
npm explain vite
npm audit --json > /tmp/seacommons-web-audit.json
npm test
npm run build
npm run test:e2e
```
Record npm/node versions, exact vulnerable package versions, parent chains, audit counts by severity, test counts, build result, browser screenshot/viewport, peak memory and runtime. Inspect whether DOMPurify is used with SAFE_FOR_TEMPLATES and DOM-returning modes; do not infer exploitability from an advisory alone. Baseline: web security gate failed, browser E2E skipped. Target: zero unresolved high/critical advisories, all web tests and mobile LIVE/PLAY E2E pass.

## Alternative hypotheses and negative controls
- DOMPurify is transitive and not reachable from the production browser bundle; prove with bundle analysis rather than assumption.
- Vite advisory applies only to dev server; check production packaging and preview exposure, but do not suppress CI findings without a reviewed risk decision.
- UI regression may be independent of dependency changes; verify LIVE panel padding and PLAY day-vs-ALL counts before and after upgrade.
- An npm audit pass alone does not prove privacy, incident attribution or geospatial correctness.

## Proposed change, risk and rollback
Smallest follow-up: selectively update affected versions and regenerate the lockfile with npm, preserving transitive integrity hashes; run audit/tests/CI, then create a distinct GREEN PR. Avoid hand-editing integrity values or deploying on failing CI. Rollback: revert the lockfile/package commit and redeploy the prior known-good Vercel build if post-deploy smoke regresses. No Oracle, PostgreSQL, WAL, AIS, or humanitarian records touched.

## Verified live
**Not deployed.** No deploy SHA, URL or smoke evidence available for this experiment. Blocker: missing verified dependency resolution + passing web security CI + browser E2E. Next executable action: clean checkout, npm explain/audit, selective lockfile update, CI and browser E2E, then authorized GREEN release.
