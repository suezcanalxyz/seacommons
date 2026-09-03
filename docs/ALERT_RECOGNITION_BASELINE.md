# Alert Recognition Baseline

Captured 2026-09-03, on top of `fix/taxonomy-service-lane` + `fix/maritime-safety-lane`
+ `feat/event-assessment` (PRs #61/#62/#63) -- before any detector threshold
is touched, per this session's priority order (docs/prompt.md Phase 3:
"Do not claim an improvement unless the evaluation corpus demonstrates it").

Regenerate: `python -m core.intel.alert_recognition_scorer` from `apps/api/`.
The exact numbers below are locked in as a regression guard by
`tests/test_alert_recognition_scorer.py` -- if a future change intentionally
moves them, update that test in the same PR, not silently.

## Finding: `is_distress()` has 3 confirmed false positives

`core.intel.geoextract.is_distress()` is a bare substring match against
`DISTRESS_KW`. The corpus (`tests/fixtures/alert_recognition/humanitarian.jsonl`)
confirms three of `docs/prompt.md`'s named hard-negative failure modes are
real, today, in production code:

| id | input (truncated) | why it false-positives |
|---|---|---|
| `hum-neg-001` | "SOS Mediterranee published its annual report..." | the org's name contains the literal keyword `sos` -- the exact case `docs/prompt.md` names |
| `hum-neg-003` | "...funding package for search and rescue operations..." | `rescue operation` (singular) is a substring of `rescue operations` (plural) |
| `hum-neg-004` | "Last year's shipwreck anniversary was marked with a vigil..." | bare `shipwreck` keyword matches a retrospective/memorial mention |

**Not fixed by this PR** -- PR-4 in this session's series is corpus +
scorer + baseline only. A fix (word-boundary matching, negative-context
exclusion, or folding these into the existing `is_resolved_distress()` /
`is_direct_distress_call()` distinction) is follow-up work, to be measured
against this same corpus per `docs/prompt.md`'s own rule.

## Full report

```
# Alert Recognition Baseline

## humanitarian.jsonl (12 fixtures)

| class | precision | recall | F1 | FP | FN |
|---|---|---|---|---|---|
| is_distress | 0.67 | 1.00 | 0.80 | 3 | 0 |

False positives (is_distress): hum-neg-001, hum-neg-003, hum-neg-004

## ais_status.jsonl (10 fixtures)

| class | precision | recall | F1 | FP | FN |
|---|---|---|---|---|---|
| publishable | 1.00 | 1.00 | 1.00 | 0 | 0 |
| service=None/lane=None | 1.00 | 1.00 | 1.00 | 0 | 0 |
| service=humanitarian/lane=distress | 1.00 | 1.00 | 1.00 | 0 | 0 |
| service=humanitarian/lane=missing | 1.00 | 1.00 | 1.00 | 0 | 0 |
| service=maritime/lane=intelligence | 1.00 | 1.00 | 1.00 | 0 | 0 |
| service=maritime/lane=safety | 1.00 | 1.00 | 1.00 | 0 | 0 |

## ais_behaviour.jsonl (5 fixtures)

NOT YET SCORED -- see module docstring. Fixtures committed, no classifier wired yet.

## ais_integrity.jsonl (4 fixtures)

NOT YET SCORED -- see module docstring. Fixtures committed, no classifier wired yet.
```
