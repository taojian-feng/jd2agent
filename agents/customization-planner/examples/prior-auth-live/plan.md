# Customization plan: live-5-runs

Runs: `pa-live-nocritic`, `pa-live-full`, `pa-live-full-2`, `pa-live-full-3`, `pa-live-full-4` · 60 traces · 58 passed

## Verdict: NOT READY TO TRAIN

- 6 model decisions differ from the verified answer with the evidence in context (PA-001 C4 unknown->met, PA-006 C4 unknown->met), on 2 task(s). This is a judgment error, the kind post-training can address.
- Not ready to train: preference pairs (train) 2 (needs >= 100); SFT examples (train) 7 (needs >= 200); distinct tasks behind the pairs 2 (needs >= 20); largest expected-outcome share in SFT 71% (needs <= 70%).
- The traces give 2 unique preference pair(s) and 9 SFT example(s). Keep the workflow fix in place and collect more verified cases before training.

## Runs

| Run | Passed | Model calls |
|---|---|---|
| `pa-live-nocritic` | 12/12 | 11 |
| `pa-live-full` | 12/12 | 22 |
| `pa-live-full-2` | 10/12 | 22 |
| `pa-live-full-3` | 12/12 | 28 |
| `pa-live-full-4` | 12/12 | 30 |

## Failures and fix routes

| Run | Task | Label | Route |
|---|---|---|---|
| `pa-live-full-2` | PA-001 | `wrong_final_answer` | model_judgment |
| `pa-live-full-2` | PA-006 | `wrong_final_answer` | model_judgment |

## Model decisions that differ from the verified answer

| Task | Criterion | Run | Where | Model said | Verified | Evidence in context | Route |
|---|---|---|---|---|---|---|---|
| PA-001 | C4 | `pa-live-full-2` | failing run | unknown | met | yes | model_judgment |
| PA-006 | C4 | `pa-live-full-2` | failing run | unknown | met | yes | model_judgment |
| PA-001 | C4 | `pa-live-full-3` | first pass | unknown | met | yes | model_judgment |
| PA-006 | C4 | `pa-live-full-3` | first pass | unknown | met | yes | model_judgment |
| PA-001 | C4 | `pa-live-full-4` | first pass | unknown | met | yes | model_judgment |
| PA-006 | C4 | `pa-live-full-4` | first pass | unknown | met | yes | model_judgment |

Changed decisions code cannot verify (the task's outcome does not pin the criterion down): 1.

## Training data

| | Raw | Kept |
|---|---|---|
| SFT examples | 53 | 9 |
| Preference pairs | 6 | 2 |

Dropped:

- pairs: duplicate of a pair already kept: 4
- sft: conflicting targets across passing runs (task dropped): 2

Split by task. Train: PA-001, PA-004, PA-005, PA-006, PA-007, PA-009, PA-011, PA-012. Eval: PA-002, PA-003, PA-010.

## Readiness gates

| Gate | Target | Actual | |
|---|---|---|---|
| preference pairs (train) | >= 100 | 2 | **fail** |
| SFT examples (train) | >= 200 | 7 | **fail** |
| distinct tasks behind the pairs | >= 20 | 2 | **fail** |
| held-out tasks | >= 3 | 3 | pass |
| largest expected-outcome share in SFT | <= 70% | 71% | **fail** |
| no task in both train and eval | 0 | 0 | pass |
| every expected outcome held out | none missing | none missing | pass |

---
Everything above is computed by code from the recorded traces: pass/fail by the evaluator's success check, verified answers from passing runs on approve tasks, targets checked by the reviewer's own citation validator, identifiers checked for masking. Gate thresholds are starting points in `resources/fix_routes.yaml`.
