# Architecture Review: Isv Contract Review

**Decision: NO-GO** · readiness 74/100 · blockers: AP-04

Rulebook: general + agent-platform

## Findings
| Severity | Rule | Section | Finding | Evidence |
|---|---|---|---|---|
| blocker | AP-04 | Tools and Integrations | The Python comparison tool runs on uploaded Word files, but the design does not describe an isolated sandbox. Egress is blocked only toward counterparties rather than by default, and there are no CPU, memory or time limits and no runtime-enforced allow-list. | "It has no network egress to counterparties, and all file access is tenant-scoped." |
| major | AP-01 | Architecture | Only an end-to-end p95 target of 60 s is given (T5). There are no per-step latency budgets and no p50 target, and the design does not say which model size serves each step. Per-clause fan-out is mentioned but not tied to a budget. | (missing) |
| major | AP-02 | Cost | Self-hosting on the vendor's GPU cluster is stated, but peak load is given only as 4,000 contracts a day, with no requests or tokens per second. Batching, concurrency and quantization are not covered, GPU capacity is 'modeled separately', and Platform Mapping lists Amazon Bedrock instead of the self-hosted cluster. Cost per contract is estimated but not tied to a sized serving plan. | (missing) |
| major | AP-05 | Evaluation | A separate guardrails layer exists for injection and non-structured output, and blocked counts are monitored (T11). But personal-data, topic and safety checks are not covered, and neither block rate nor false-block rate is measured on the evaluation set. | (missing) |
| major | DAT-02 | Observability | Data is classified restricted and confidential, and logging stays inside the tenant boundary. But no retention period, deletion policy or prompt/output log retention rule is stated for restricted contract content, traces or the audit trail. | (missing) |
| minor | AP-08 | Architecture | Nothing in the design decouples the agent from the orchestration framework or the model provider, such as tools behind MCP or a model adapter. Platform Mapping binds the workflow to LangGraph or Strands and the model to Bedrock. | (missing) |
| minor | CST-02 | Architecture | Clause identification, comparison and redline drafting run on a single 'fixed model per step' with no per-step justification. The design never says why a smaller model would or would not suffice for the simpler steps. | (missing) |
| minor | OPS-03 | Observability | Escalation rate, reviewer accept/reject statistics and cost drift are monitored, but no named owner or team is responsible for production quality or for acting on the alerts. | (missing) |

## Scores by Category
| Category | Score |
|---|---|
| security | 50 |
| data | 75 |
| reliability | 100 |
| evaluation | 100 |
| operations | 55 |
| cost | 65 |
| responsible_ai | 75 |
