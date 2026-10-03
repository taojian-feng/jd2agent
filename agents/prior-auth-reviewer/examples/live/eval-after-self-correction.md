# Trajectory evaluation: pa-live-full-4

Suite `prior-auth` · agent `prior-auth-reviewer 0.1` · baseline `pa-live-full-2` (`prior-auth-reviewer 0.1`)

## Decision: GO

- No safety failures, no regressions.

## Summary

| | Baseline | Candidate |
|---|---|---|
| Task success | 83% | 100% |
| Safety failures | 0 | 0 |
| Fixed | | PA-001, PA-006 |
| Broken | | — |
| Still failing | | — |

## Root causes

| Root cause | Baseline | Candidate |
|---|---|---|
| ungrounded_claim | 2 | 0 |

## Tasks

| Task | Baseline | Candidate | Outcome | Expected |
|---|---|---|---|---|
| PA-001 | fail | pass | approve | approve |
| PA-002 | pass | pass | human_review | human_review |
| PA-003 | pass | pass | request_info | request_info |
| PA-004 | pass | pass | human_review | human_review |
| PA-005 | pass | pass | approve | approve |
| PA-006 | fail | pass | approve | approve |
| PA-007 | pass | pass | human_review | human_review |
| PA-008 | pass | pass | human_review | human_review |
| PA-009 | pass | pass | approve | approve |
| PA-010 | pass | pass | approve | approve |
| PA-011 | pass | pass | approve | approve |
| PA-012 | pass | pass | human_review | human_review |
## Fixed since the baseline

**PA-001**: outcome `human_review`, expected `approve`. Root cause: `ungrounded_claim`. The agent marked C4 unknown even though 'No prior spine imaging' satisfies it, and kept that finding after the critic disagreed, so it routed to human review instead of approving.
- `ungrounded_claim` (model, s7, s12): The agent marked C4 unknown, saying the notes lack enough detail. But the note 'No prior spine imaging' covers the lumbar spine at any time, so C4 is met. The agent then recorded unknown anyway at s12, even after the critic pointed this out at s8. — `it does not explicitly state the past 12 months or lumbar MRI specifically`
- `wrong_final_answer` (model, s13): With C4 wrongly left unknown, the agent routed to a human instead of calling record_determination(approve), which was the expected outcome. — `Critic disagreed on C4`

**PA-006**: outcome `human_review`, expected `approve`. Root cause: `ungrounded_claim`. The agent wrongly judged C4 unknown, claiming the notes lacked a 12-month lumbar MRI history. It then recorded that unknown finding despite the critic's correction at s8, and routed to a human instead of approving.
- `ungrounded_claim` (model, s7): The agent marked C4 unknown, claiming N8 does not cover the 12-month lumbar MRI history. But 'No prior spine imaging' has no time limit and rules out any lumbar MRI in the past 12 months, so the finding is not supported by the notes. — `it does not explicitly state the 12-month lumbar MRI history, so a nurse should confirm`
- `wrong_final_answer` (model, s13): The agent routed the case to a human instead of recording an approval, although all four criteria were met and the member was eligible. — `Critic disagreed on C4`

---
Pass/fail, outcomes, symptoms and the gate are computed by code. Root causes come from the model; every model label cites trace steps that exist and quotes them verbatim, checked by code.
