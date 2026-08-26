# Contributing

Use a feature branch and keep changes scoped. Before opening a pull request run:

```text
python -m pytest -q
cd apps/web
npm run lint
npm run test:simulation
npm run build
cd ../edge
npm test
```

Use the pull request template to state the outcome, risk, rollback and exact
verification performed. Architecture changes that alter a durable boundary,
contract or operating model require an ADR under `docs/adr/`; small
implementation choices do not.

New analytical outputs must document source, timestamp, model/version,
uncertainty and limitations. Never commit credentials, personal data, live
distress locations or unredacted operational exports.

Report vulnerabilities through the repository's private security advisory
channel, never a public issue. Public issue forms reject active emergencies and
sensitive reports by design.

By contributing you agree that your contribution is licensed under the project's
AGPL-3.0-or-later licence.
