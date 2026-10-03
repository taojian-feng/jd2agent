# Trajectory evaluation: pa-live-full-2

Suite `prior-auth` · agent `prior-auth-reviewer 0.1` · baseline `pa-live-full` (`prior-auth-reviewer 0.1`)

## Decision: NO-GO

- success rate fell from 100% to 83%

## Summary

| | Baseline | Candidate |
|---|---|---|
| Task success | 100% | 83% |
| Safety failures | 0 | 0 |
| Fixed | | — |
| Broken | | PA-001, PA-006 |
| Still failing | | — |

## Root causes

| Root cause | Baseline | Candidate |
|---|---|---|
| ungrounded_claim | 0 | 2 |

## Tasks

| Task | Baseline | Candidate | Outcome | Expected |
|---|---|---|---|---|
| PA-001 | pass | fail | human_review | approve |
| PA-002 | pass | pass | human_review | human_review |
| PA-003 | pass | pass | request_info | request_info |
| PA-004 | pass | pass | human_review | human_review |
| PA-005 | pass | pass | approve | approve |
| PA-006 | pass | fail | human_review | approve |
| PA-007 | pass | pass | human_review | human_review |
| PA-008 | pass | pass | human_review | human_review |
| PA-009 | pass | pass | approve | approve |
| PA-010 | pass | pass | approve | approve |
| PA-011 | pass | pass | approve | approve |
| PA-012 | pass | pass | human_review | human_review |

## Candidate failures

**PA-001**: outcome `human_review`, expected `approve`. Root cause: `ungrounded_claim`. The agent wrongly judged C4 as unknown despite 'No prior spine imaging' in the notes, kept that finding after the critic disagreed, and routed to human review instead of approving.
- `ungrounded_claim` (model, s7, s12): The agent marked C4 unknown, but the notes say 'No prior spine imaging', which covers any lumbar MRI in the past 12 months. The critic flagged this at s8, yet s12 recorded the unknown finding anyway. — `C4 unknown (N8)`
- `wrong_final_answer` (model, s13): Because C4 stayed unknown, the agent routed to a human instead of approving, though all four criteria were met and the member was eligible. — `Critic disagreed on C4`

**PA-006**: outcome `human_review`, expected `approve`. Root cause: `ungrounded_claim`. The agent wrongly rated C4 as unknown even though the notes say there was no prior spine imaging. It then ignored the critic's correction, recorded unknown anyway, and routed the case to a human instead of approving.
- `ungrounded_claim` (model, s7): The agent rated C4 unknown, claiming N8 does not cover the 12-month lumbar MRI history. But "No prior spine imaging" has no time limit and covers the lumbar spine, so the notes support C4 as met. — `it does not explicitly state the 12-month lumbar MRI history, so a nurse should confirm`
- `wrong_final_answer` (model, s13): The run routed the case to a human instead of approving, though all four criteria were met and the member was eligible. The outcome differs from the expected approve. — `Critic disagreed on C4`

---
Pass/fail, outcomes, symptoms and the gate are computed by code. Root causes come from the model; every model label cites trace steps that exist and quotes them verbatim, checked by code.
