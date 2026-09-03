# Alert Recognition Baseline

Captured 2026-09-03, on top of `fix/taxonomy-service-lane` + `fix/maritime-safety-lane`
+ `feat/event-assessment` (PRs #61/#62/#63) -- before any detector threshold
is touched, per this session's priority order (docs/prompt.md Phase 3:
"Do not claim an improvement unless the evaluation corpus demonstrates it").

Regenerate: `python -m core.intel.alert_recognition_scorer` from `apps/api/`.
The exact numbers below are locked in as a regression guard by
`tests/test_alert_recognition_scorer.py` -- if a future change intentionally
moves them, update that test in the same PR, not silently.

## Update 2026-09-03: the 3 false positives below are fixed

The original baseline (PR #64) found 3 confirmed false positives in
`is_distress()`. All three are now fixed (see
`apps/api/core/intel/geoextract.py`):

| id | input (truncated) | fix |
|---|---|---|
| `hum-neg-001` | "SOS Mediterranee published its annual report..." | `is_distress()` now reuses `_SOS_MARKER_RE`, which already excluded this exact org-name shape for the stricter `is_direct_distress_call()` -- the two functions had drifted out of sync |
| `hum-neg-003` | "...funding package for search and rescue operations..." | `rescue operation` removed from `DISTRESS_KW` -- too weak/ambiguous as a bare trigger; no positive fixture relied on it |
| `hum-neg-004` | "Last year's shipwreck anniversary was marked with a vigil..." | new shared `_RETROSPECTIVE_COMMEMORATION_RE` exclusion (anniversary/memorial/vigil/commemorate), applied to **both** `is_distress()` and `is_direct_distress_call()` -- the stricter function had the identical defect, confirmed independently while fixing this (`is_direct_distress_call("...shipwreck anniversary...")` was also `True` before the fix) |

`is_distress()` now scores `1.00` precision / `1.00` recall / `1.00` F1 on
`humanitarian.jsonl` (0 FP, 0 FN) -- see full report below. Additional
direct unit tests for both functions: `tests/test_geoextract.py`.

## Full report

```
# Alert Recognition Baseline

## humanitarian.jsonl (12 fixtures)

| class | precision | recall | F1 | FP | FN |
|---|---|---|---|---|---|
| is_distress | 1.00 | 1.00 | 1.00 | 0 | 0 |

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
