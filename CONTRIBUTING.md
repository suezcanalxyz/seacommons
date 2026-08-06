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

New analytical outputs must document source, timestamp, model/version,
uncertainty and limitations. Never commit credentials, personal data, live
distress locations or unredacted operational exports.

By contributing you agree that your contribution is licensed under the project's
AGPL-3.0-or-later licence.
