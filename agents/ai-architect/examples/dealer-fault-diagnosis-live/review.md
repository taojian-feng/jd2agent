# Architecture Review: Dealer Fault Diagnosis

**Decision: CONDITIONAL** · readiness 94/100 · blockers: none

## Findings
| Severity | Rule | Section | Finding | Evidence |
|---|---|---|---|---|
| major | DAT-02 | Observability | Repair history and work orders are classified confidential, and the audit log records plans, tool calls and evidence. The design gives no retention period, no statement on whether prompt and output content is stored or redacted, and no deletion policy. Saying confidential data is 'handled accordingly' does not show that logging complies with the classification. | (missing) |
| minor | CST-02 | Cost | One 'mid-tier' foundation model is assumed for planning, synthesis and revision calls. No per-step model choice is justified, for example a smaller model for planning or input checks, so the design does not show where smaller models would suffice. | (missing) |
| minor | OPS-03 | Observability | Latency, validation rates and cost are monitored, and a monthly sample review exists. However, there is no user feedback channel, no escalation-rate metric, and no named owner for production quality monitoring. Only data-source owners and a security on-call route for leakage alerts are named. | (missing) |

## Scores by Category
| Category | Score |
|---|---|
| security | 100 |
| data | 75 |
| reliability | 100 |
| evaluation | 100 |
| operations | 90 |
| cost | 90 |
| responsible_ai | 100 |
