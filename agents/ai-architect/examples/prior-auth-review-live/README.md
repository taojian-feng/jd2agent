# Live example: prior authorization review, with the healthcare rule pack

Scenario: [`resources/scenarios/prior-auth-review.md`](../../resources/scenarios/prior-auth-review.md) (fictional
health plan, no patient data). Model `anthropic:claude-sonnet-5-5`. Every review applies the general rulebook plus
the [healthcare rule pack](../../resources/review_rules_healthcare.yaml), which the scenario switches on.

## Design → review → revise

| Version | Decision | Score | Findings |
|---|---|---|---|
| v1 ([design](design.md), [review](review.md)) | conditional | 88 | SEC-04 prompt injection in notes, OPS-03 no owner for quality alerts, HC-05 no time limit on escalation, HC-06 audit trail missing tool versions |
| v2 ([design](design_v2.md), [review](review_v2.md)) | **go** | 100 | none |

[`brief.md`](brief.md) is the one-page summary of the run.

**Why the reviser sees the whole pack.** The first live attempt, before that change, did not converge: v1
conditional, v2 **no-go**, v3 conditional. Each review round found a different, real healthcare gap: escalation
timing, then patient data in the evaluation set, then tool versions missing from the audit record. The reviser fixed
only what it was shown. Now every revision prompt lists all healthcare rules and asks for any gap to be closed, not
only the reported ones. The next run reached GO after one revision.

## Does the review catch healthcare defects?

[`defects.md`](defects.md): the v2 design plus four variants, each contradicting one safeguard
([`defect_sets/prior-auth`](../../resources/defect_sets/prior-auth/defects.yaml)), reviewed twice each.

| Variant | Caught by | Decision |
|---|---|---|
| Clinical notes and full prompts kept in logs | HC-01 (and DAT-02), both passes | no-go |
| The agent records denials itself | HC-02 (and REL-01), both passes | no-go |
| Release on overall accuracy; safety failures reviewed after launch | HC-04, both passes | no-go |
| Failed cases sit in a shared work list, no owner or time limit | HC-05, both passes | conditional |
| Clean design | no findings, both passes | go |

Recall 4/4 in both passes against an 80% target; no false alarms on the clean design.

**Caveat:** four planted defects is a small set, and they are deliberately clear contradictions. Subtle gaps, like
the ones the live loop found on its own, are harder; the loop history above is the better evidence for those.
