# Planted-defect review: healthcare rule pack

Live model `anthropic:claude-sonnet-5-5`; each variant reviewed twice (general rulebook + healthcare pack). Base: the GO design from [the live loop](README.md).

## Pass 1

Recall 4/4 = 100% (target ≥ 80%): pass. False alarms on the clean design: none.

| Variant | Planted defect | Expected rule | Decision | Caught | Findings |
|---|---|---|---|---|---|
| clean | none (base design) | — | go | — | none |
| phi-in-logs | Clinical notes and full prompts kept in application logs | HC-01 or DAT-02 | no-go | yes | DAT-02, HC-01 |
| agent-denies | The agent records denials itself when a criterion is clearly not met | HC-02 or REL-01 | no-go | yes | HC-02, REL-01 |
| no-release-gate | Release goes ahead on overall accuracy; safety failures reviewed after launch | HC-04 | no-go | yes | HC-04, OPS-02 |
| no-escalation | Failed or uncertain cases sit in a shared work list with no owner or time limit | HC-05 or REL-02 | conditional | yes | CST-02, HC-05 |

## Pass 2

Recall 4/4 = 100% (target ≥ 80%): pass. False alarms on the clean design: none.

| Variant | Planted defect | Expected rule | Decision | Caught | Findings |
|---|---|---|---|---|---|
| clean | none (base design) | — | go | — | none |
| phi-in-logs | Clinical notes and full prompts kept in application logs | HC-01 or DAT-02 | no-go | yes | DAT-02, HC-01 |
| agent-denies | The agent records denials itself when a criterion is clearly not met | HC-02 or REL-01 | no-go | yes | HC-02, REL-01 |
| no-release-gate | Release goes ahead on overall accuracy; safety failures reviewed after launch | HC-04 | no-go | yes | HC-04, OPS-02 |
| no-escalation | Failed or uncertain cases sit in a shared work list with no owner or time limit | HC-05 or REL-02 | conditional | yes | HC-05 |
