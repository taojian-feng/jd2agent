# Architecture Review: Prior Auth Review

**Decision: CONDITIONAL** · readiness 88/100 · blockers: none

Rulebook: general + healthcare

## Findings
| Severity | Rule | Section | Finding | Evidence |
|---|---|---|---|---|
| major | HC-05 | Human Oversight | Escalation goes to a nurse review queue for low confidence, missing documentation and tool failures. No response time or SLA is defined for the nurse queue or documentation requests. Only the two-minute target for clear approvals is stated, and no named role or team receives escalated cases. | (missing) |
| major | HC-06 | Architecture | The decision record captures policy, model and prompt versions, findings and the approver. It does not record tool, gateway, validator or router rule-set versions, nor the full inputs used. The router's rule set determines the outcome, so a decision cannot be fully reconstructed. | "model and prompt versions, validation results, proposed action, approver identity and timestamp" |
| major | SEC-04 | Failure Modes | Clinical notes come from outside providers and are untrusted text fed to the model, but the design never names prompt injection as a risk. It has no injection-specific mitigation and no injection tests. The validator and approval gate limit the impact, but the risk is not identified or addressed. | (missing) |
| minor | OPS-03 | Observability | Drift is tracked via routing mix and alerts exist, but no owner or team is named to receive and act on them. There is also no user-feedback channel from nurses or approvers, such as override or disagreement rates. | (missing) |

## Scores by Category
| Category | Score |
|---|---|
| security | 75 |
| data | 100 |
| reliability | 75 |
| evaluation | 100 |
| operations | 65 |
| cost | 100 |
| responsible_ai | 100 |
