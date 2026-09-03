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

## Update 2026-09-03: M2.1 -- corpus expanded, HumanitarianAssessment scored

`docs/fixes.md` M2.1: `humanitarian.jsonl` grew from 12 to 18 fixtures
(added `hum-007`..`hum-012`, covering the multi-quantity-separation
headline rule, pushback, interception, land_humanitarian, a clean
resolution case, and non-memorial advocacy), and every row now carries
`provenance_kind`, `expected_case_type`, `expected_counts` and
`expected_publication` alongside the existing `expected_is_distress` /
`expected_lifecycle`. All fixtures are `provenance_kind: synthetic` --
no repository access to real historical Alarm Phone posts was available
for this pass.

A new `score_humanitarian_recognition()` scores
`core.intel.humanitarian_recognition.assess()` (#87/#88) against the same
corpus on the four M2.1 exit-gate dimensions: case_type, lifecycle,
people-count accuracy, and publication recommendation. Ground-truthing
the corpus by hand caught and fixed two real extraction gaps in `assess()`
itself before this report was captured -- role-word-before-count ordering
("dispersi almeno 12 persone") and a small filler-verb tolerance ("45
people *believed* aboard") -- plus one lifecycle gap (a `missing`-case-type
report was falling through to `needs_review` instead of `active`). See
`tests/test_humanitarian_recognition.py` for the regression tests.

**One known, intentionally NOT fixed gap remains**: `hum-004`, a French
distress report ("Détresse maritime signalée..."), is the sole false
negative on case_type/lifecycle/publication. `is_direct_distress_call()`
and `_case_type()` have no French distress-call patterns yet -- `is_distress()`
(the loose ingestion prefilter, scored separately above) does still catch
it. Extending direct-call recognition to French/Italian is out of scope
for this corpus/scorer PR and is recorded here rather than silently
patched, per this file's own "do not claim an improvement unless the
evaluation corpus demonstrates it" rule.

## Update 2026-09-03: M4.1 -- ais_behaviour.jsonl scored

`docs/fixes.md` M4.1: a new `core/intel/ais_behaviour_replay.py` gives
`AISSpikeDetector` (stateful, time-series-driven, polls the live vessel
registry) a pure `classify(input) -> (label, confidence)` entry point that
matches `ais_behaviour.jsonl`'s fixture shape exactly. Covers 3 of its
kinds -- `sudden_stop`, `rescue_cluster`, `ngo_search_pattern` (the ones
the current 5 fixtures exercise) -- built directly against
`ais_spike_detector`'s existing threshold constants (`SPEED_THRESHOLD_KN`,
`STOP_THRESHOLD_KN`, `CLUSTER_RADIUS_NM`, `SEARCH_TRACK_MIN_FIXES`,
`SEARCH_TRACK_WINDOW_MIN`), imported rather than duplicated, so neither
module's tuning can drift out of sync with the other. `vessel_loiter` has
no fixture or classifier yet; a row of that kind would report as its own
`unscored_count` inside an otherwise-scored file, not silently dropped.

Scores perfectly (1.00/1.00 on both dimensions the fixture schema
carries: classification-label accuracy and confidence-range membership)
-- the classifier was built directly against this exact fixture set, so
this locks in a regression guard, not a claimed improvement over prior
behaviour (there was no prior scored behaviour for this file).

`ais_integrity.jsonl` (gap/impossible_speed/dark_zone_entry) stays
unscored -- its gap classifier is `docs/fixes.md` M4.2 territory
(coverage-baseline reasoning should inform it before it's built).

## Full report

```
# Alert Recognition Baseline

## humanitarian.jsonl (18 fixtures)

| class | precision | recall | F1 | FP | FN |
|---|---|---|---|---|---|
| is_distress | 1.00 | 1.00 | 1.00 | 0 | 0 |

## humanitarian.jsonl (recognition v2) (18 fixtures)

| class | precision | recall | F1 | FP | FN |
|---|---|---|---|---|---|
| case_type | 1.00 | 0.94 | 0.97 | 0 | 1 |
| lifecycle | 1.00 | 0.88 | 0.93 | 0 | 1 |
| people_counts | 1.00 | 1.00 | 1.00 | 0 | 0 |
| publication_recommendation | 1.00 | 0.94 | 0.97 | 0 | 1 |

False negatives (case_type): hum-004
False negatives (lifecycle): hum-004
False negatives (publication_recommendation): hum-004

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

| class | precision | recall | F1 | FP | FN |
|---|---|---|---|---|---|
| classification | 1.00 | 1.00 | 1.00 | 0 | 0 |
| confidence_in_range | 1.00 | 1.00 | 1.00 | 0 | 0 |

## ais_integrity.jsonl (4 fixtures)

NOT YET SCORED -- see module docstring. Fixtures committed, no classifier wired yet.
```
