# Contributing to SeaCommons

Thank you for helping build open-source infrastructure for maritime search and rescue, operational awareness and accountable documentation.

SeaCommons welcomes contributions from developers, SAR practitioners, cartographers, oceanographers, designers, translators, legal researchers, data-protection specialists and humanitarian organisations.

## Before you contribute

SeaCommons concerns safety-critical and potentially sensitive contexts. Contributions must not include real distress-case data, personal information, private communications, credentials or operational details that could place people or rescue activities at risk.

The platform is not a certified navigation or emergency-response system. Features and documentation must not imply otherwise.

## Ways to contribute

Useful contribution areas include:

- improving installation and deployment;
- creating synthetic rescue scenarios;
- accessibility and low-bandwidth support;
- multilingual interfaces and documentation;
- environmental-data and drift-model integrations;
- maritime-system interoperability;
- security and privacy reviews;
- ethical governance and data-retention practices;
- testing, bug reports and documentation.

## Development setup

The recommended starting point is the pilot stack:

```bash
git clone https://github.com/suezcanalxyz/seacommons.git
cd seacommons
cp .env.example .env
docker compose -f deploy/docker-compose.pilot.yml up --build
```

The dashboard is available at `http://localhost:3000`, the API at `http://localhost:8000` and the API documentation at `http://localhost:8000/docs`.

## Issues

Before opening an issue:

1. Search existing issues and documentation.
2. Remove all real personal, operational and distress-case data.
3. State whether the problem affects the pilot, full runtime or public demo.
4. Include reproducible steps, expected behaviour and actual behaviour.
5. Add screenshots or logs only after removing sensitive information and secrets.

Feature proposals should explain the operational problem before proposing a technical solution.

## Pull requests

Keep pull requests focused and reasonably small. Include:

- what changed;
- why the change is needed;
- which part of SeaCommons is affected;
- how the change was tested;
- any safety, privacy or operational implications;
- screenshots for visible interface changes.

Do not mix unrelated refactors with a feature or fix.

## Code and documentation principles

Contributions should favour:

- human oversight over opaque automation;
- traceability over silent mutation;
- interoperability over unnecessary lock-in;
- data minimisation over indiscriminate collection;
- clear limitations over inflated claims;
- accessible and low-bandwidth operation where possible;
- the safety and dignity of people at sea.

## Synthetic data

Use fictional or fully anonymised data for development, demonstrations and tests. Coordinates, timestamps, identities and vessel details must not be copied from an active or identifiable distress case.

## Security reports

Do not open public issues for vulnerabilities or exposure of sensitive data. Follow the private reporting process in [`SECURITY.md`](./SECURITY.md).

## Licensing

By contributing, you agree that your contribution will be licensed under the GNU Affero General Public License v3.0 used by this repository.