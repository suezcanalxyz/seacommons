# Contributing

SeaCommons welcomes focused improvements to its documentation, interfaces and analytical code. Start with an [open issue labelled `good first issue`](https://github.com/suezcanalxyz/seacommons/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22); comment there if the scope is unclear or you would like to work on it.

## Your first contribution

A documentation correction is a useful place to begin. You can do it entirely in GitHub without local credentials or a running SeaCommons service:

1. Pick a small documentation issue and check that it is still open. If you have a proposed change, describe it on the issue so a maintainer can guide you.
2. Fork this repository, open the Markdown file named in the issue, and use GitHub's **Edit this file** action. Choose a new branch in your fork when saving.
3. Preview the rendered Markdown. Check any links you changed and confirm the wording against the current public interface or source documentation. Do not add examples containing personal data or active distress locations.
4. Open a pull request to this repository, link the issue, and use the [pull request template](.github/pull_request_template.md) to describe what changed and which checks you actually performed. For a docs-only change, say that code tests were not run and why.
5. A maintainer reviews and merges pull requests. Respond to review comments on the PR; you do not need permission to propose a correction.

For code changes, follow [local development instructions](docs/DEVELOPMENT.md) and keep the change scoped. Changes developed with AI coding tools must also follow [the AI engineering policy](docs/AI_ENGINEERING_POLICY.md).

## Verification for code changes

Use a feature branch. Before opening a code pull request, run the relevant checks below and report the exact results or limitations in the pull request. The full suite may take time; do not claim a check passed unless you ran it.

```text
python -m pytest -q
cd apps/web
npm run lint
npm test
npm run build
cd ../edge
npm test
```

Use the pull request template to state the outcome, risk, rollback and exact verification performed. Architecture changes that alter a durable boundary, contract or operating model require an ADR under `docs/adr/`; small implementation choices do not.

New analytical outputs must document source, timestamp, model/version, uncertainty and limitations. Never commit credentials, personal data, live distress locations or unredacted operational exports.

Report vulnerabilities through the repository's [private security advisory channel](https://github.com/suezcanalxyz/seacommons/security/advisories/new), never a public issue. Public issue forms reject active emergencies and sensitive reports by design.

By contributing you agree that your contribution is licensed under the project's AGPL-3.0-or-later licence.
