# AI-assisted engineering policy

Status: canonical policy. Last reviewed: 2026-08-27.

Parts of SeaCommons are developed with AI coding tools (Claude Code, Codex).
This is allowed. The rules below make the practice safe and reviewable; they
apply to every contributor regardless of which tools they use.

## Principles

1. AI is an engineering tool, not an authority. The human who opens the PR owns
   the change and must understand every line of it.
2. No AI-generated change merges without a human review and approval.
3. Prefer small, single-purpose PRs. Do not submit large unexplained
   AI-generated diffs.
4. If the model is uncertain about domain behaviour, stop and document the
   uncertainty in the PR instead of guessing. This is a hard rule for anything
   touching incident lifecycle, coordinates, or the public/private boundary.

## Every AI-assisted change must pass

1. Deterministic tests — `pytest`, edge `node --test`, web `npm test`.
2. Lint and type checks — the CI gates in `.github/workflows/ci.yml`.
3. Architectural review — does it respect the one-way dependency direction and
   keep domain policy out of route handlers? ([ARCHITECTURE.md](ARCHITECTURE.md))
4. Security review for any change to auth, ingestion authenticity, webhooks,
   public projection, or configuration. Run `/security-review` or the
   equivalent and address findings.
5. Human approval on the PR.

## Never let an AI-assisted change

- Fabricate production claims, realtime data or coordinates.
- Silently change incident lifecycle semantics (active / resolved / archived /
  removed).
- Weaken a fail-closed production check or a privacy constraint.
- Expose operational secrets, or commit `.env*`, cookies, or exports.
- Present planned or experimental functionality as operational.

## PR hygiene

State in the PR description that the change was AI-assisted and what was
verified by a human. The standard template fields (why / what / architecture
impact / tests / risks / rollback) are mandatory; "the model says it works" is
not an entry for the tests field.

## Related documents

- [Contribution rules](../CONTRIBUTING.md)
- [Testing strategy](TESTING.md)
- [Security model](SECURITY_MODEL.md)
