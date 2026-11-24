# FUTURES activity register

The shared journal is rendered in both Strategy → Updates and Agents → Activity.
The read-only scheduler snapshot remains a separate view, and is not evidence of execution.

## Write contract
- `apps/web/src/futures/strategyJournal.json`: array of dated bilingual records, one per commit, with category, status, deployment reference and origin. Use the current schema. A READY Vercel build describes frontend build completion, not operational validation of the API or sensors.
- `apps/web/src/futures/agenticRuns.json`: run records with ID, UTC timestamp, origin, status and bilingual description. A verified scheduled record requires a real execution reference; manual backfill must never be counted as a scheduled run.
- Deduplicate by commit SHA (including short/full aliases) and run ID. Preserve existing entries. Only include non-sensitive verified changes. Plans belong in the strategy plan and must be labelled proposed.

## Publication protocol
1. Identify the current production commit and a clean isolated branch based on the current release; do not deploy an older branch.
2. Review changes since the journal watermark using actual source, CI and Vercel results. Confirm release references; otherwise record commit-only scope.
3. Append bilingual entries. Update the run register only with observed facts, never invent a run or claim the publication of the current commit before verification.
4. Run the journal tests and existing FUTURES tests, lint and unified build. Review the diff for scope and secrets.
5. Push and deploy the tested exact commit through the existing authorized release process; confirm READY and verify the published frontend bundle. If any gate fails, report the blocker, never report success.
6. No meaningful change: no new journal commit. A run can report no change in ChatGPT without rebuilding the site.

The automation is scheduled in ChatGPT. It requires working authorized connectors; a scheduled task alone is not a verified site integration. Do not edit production infrastructure, scheduler permissions, private evidence or operational data. No secrets or personal information in the journal.
