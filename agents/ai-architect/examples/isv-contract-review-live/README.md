# Live example: ISV contract review agent, with the agent-platform rule pack

Scenario: [`resources/scenarios/isv-contract-review.md`](../../resources/scenarios/isv-contract-review.md) (a
fictional software vendor shipping a contract review agent to many customers). One live run through the job runner,
with the model configured in the runner (the run does not record the model id). Every review applies the general
rulebook plus the [agent-platform rule pack](../../resources/review_rules_agent-platform.yaml), which the scenario
switches on.

## Design → review → revise

| Version | Decision | Score | Findings |
|---|---|---|---|
| v1 ([design](design.md), [review](review.md)) | **no-go** | 74 | blocker AP-04 (code tool not sandboxed); major AP-01 (no per-step latency budget), AP-02 (no serving plan; platform mapping named a hosted model service, not the self-hosted cluster), AP-05 (guardrail rates not measured), DAT-02; minor OPS-03, CST-02, AP-08 |
| v2 ([design](design_v2.md), [review](review_v2.md)) | conditional | 96 | major RAI-01 (users not told redlines are AI-generated) |
| v3 ([design](design_v3.md), [review](review_v3.md)) | **go** | 100 | none |

[`brief.md`](brief.md) is the one-page summary of the run.

**What the pack added.** Five of the eight v1 findings come from the pack, including the only blocker: the
agent's own design ran Python on uploaded Word files with egress blocked "toward counterparties" rather than by
default, and no resource limits. Without the pack the general rulebook has no rule for sandboxed execution.

**What this run does not show.** One run, so no variance yet; the first agent's four live runs showed that
borderline rules flip between runs. The pack's planted-defect set is still planned, so recall on known defects is not measured.
The v2 finding (RAI-01) is a general rule the reviser had not been shown; it closed it in one more round.
