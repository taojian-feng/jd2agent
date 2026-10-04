# Isv Contract Review

## Executive Summary

**Problem.** Our roughly 300 customers' legal teams check incoming supplier contracts against their own rules ("playbooks"). A first review takes a paralegal 1 to 3 hours, and volume reaches about 4,000 contracts a day at quarter end.

**Solution.** A contract review assistant inside the product. It finds each clause the playbook covers, compares it with the playbook position, and proposes a marked-up change (a "redline"). Every change cites the playbook rule and the contract clause behind it. Clauses needing a lawyer are listed separately. A first redline is targeted within 60 seconds for a 20-page contract. It uses a fixed series of steps, not open-ended automation, so cost and speed are predictable.

**How people stay in control.** A member of the customer's legal team must accept or reject every redline, and each decision is recorded under a named user. Automatic checks confirm that each cited rule and quoted clause really exists; anything failing goes to a lawyer. The system never sends anything to the other party.

**Confidentiality.** Each customer's data, storage, encryption keys and model calls are kept strictly separate, including between competitors. Models run on our own graphics processing unit (GPU) servers in our cloud. Fine-tuning on customers' accepted redlines is not part of this design, because it could blend competitors' data.

**Cost (estimates, not yet measured).** About $0.15 to $0.35 per contract, or roughly $4,500 to $10,500 a month at 30,000 contracts. A 4,000-contract peak day would cost about $600 to $1,400. Reserving GPU capacity for the peak is the main fixed cost and needs separate modeling.

**Key risks.**
- Contracts containing hidden instructions aimed at the assistant.
- Wrong or missed clauses.
- Data leaking between customers.
- Slowdowns at quarter end if capacity is not ready.
- Reviewers approving without real scrutiny.

Each has a safeguard, and all are covered by testing.

**Suggested pilot (about 12 weeks).**
- **Weeks 1–4:** Build the test set with lawyer-labeled contracts and measure quality, citation accuracy and speed.
- **Weeks 5–8:** Run the documented security evaluation, including hidden-instruction and cross-customer leakage tests, and close the gaps found.
- **Weeks 9–12:** Limited pilot with a few volunteer customers, tracking cost per contract and reviewer decisions.

Timing should avoid a quarter-end peak until capacity is proven. Release depends on security approval and meeting the agreed thresholds.

## Problem Statement
An enterprise software vendor sells a contract lifecycle management product to about 300 corporate customers. Its
customers' legal teams review incoming supplier contracts against their own playbooks: which clauses are acceptable,
which need a fallback position, and which must go to a lawyer. A first review takes a paralegal 1–3 hours per
contract, and volume spikes to about 4,000 contracts a day across all customers at quarter end.

The vendor wants to ship a contract review agent inside the product. Given a contract and the customer's playbook,
it finds each clause the playbook covers, compares it with the playbook position, proposes a redline with the
playbook rule it applies, and lists clauses that need a lawyer. A comparison tool runs Python on the uploaded Word
files to produce the redlined document. The agent never sends anything to the counterparty; a person on the
customer's legal team accepts or rejects every redline. Every proposed change must cite the playbook rule and the
contract clause it relies on.

Each customer's contracts and playbooks are confidential to that customer, and several customers compete with each
other. The vendor wants to serve open-weight models on its own GPU cluster to control cost and keep data in its
cloud, and its machine learning team proposes fine-tuning a model on redlines that customers accepted. Product
management wants the first redline back within 60 seconds for a 20-page contract, and a cost per contract the
pricing team can plan around. The vendor's security team will not approve release without a documented evaluation,
including adversarial contracts that try to instruct the agent.

## Requirements
| ID | Requirement | Source (brief) |
|---|---|---|
| FR-1 | The agent shall accept a contract and the customer's playbook as inputs for review. | "Given a contract and the customer's playbook," |
| FR-2 | The agent shall identify each clause in the contract that the playbook covers. | "it finds each clause the playbook covers" |
| FR-3 | The agent shall compare each identified clause with the corresponding playbook position. | "compares it with the playbook position" |
| FR-4 | The agent shall propose a redline for each clause that departs from the playbook, stating the playbook rule applied. | "proposes a redline with the" |
| FR-5 | The agent shall list the clauses that need a lawyer. | "lists clauses that need a lawyer" |
| FR-6 | The system shall use a comparison tool that runs Python on the uploaded Word files to produce the redlined document. | "A comparison tool runs Python on the uploaded Word" |
| FR-7 | The agent shall not send any content to the counterparty. | "The agent never sends anything to the counterparty" |
| FR-8 | The system shall require a person on the customer's legal team to accept or reject every redline. | "accepts or rejects every redline" |
| FR-9 | Every proposed change shall cite both the playbook rule and the contract clause it relies on. | "Every proposed change must cite the playbook rule and the" |
| NFR-1 | The system shall keep each customer's contracts and playbooks confidential to that customer, including isolation between customers that compete with each other. | "Each customer's contracts and playbooks are confidential to that customer" |
| NFR-2 | The agent shall return the first redline within 60 seconds for a 20-page contract. | "the first redline back within 60 seconds for a 20-page contract" |
| NFR-3 | The system shall handle quarter-end peak volume of about 4,000 contracts a day across all customers. | "volume spikes to about 4,000 contracts a day across all customers at quarter end" |
| NFR-4 | The system shall serve open-weight models on the vendor's own GPU cluster, keeping data in the vendor's cloud. | "The vendor wants to serve open-weight models on its own GPU cluster to control cost and keep data in its" |
| NFR-5 | The system shall have a cost per contract that is predictable enough for the pricing team to plan around. | "a cost per contract the" |
| NFR-6 | A documented evaluation shall be completed before release, as required by the security team for approval. | "will not approve release without a documented evaluation," |
| NFR-7 | The evaluation shall include adversarial contracts that try to instruct the agent, and the agent shall resist such instructions. | "including adversarial contracts that try to instruct the agent." |

## Pattern Selection
**Selected: P2 Deterministic workflow (prompt chain / graph with fixed steps)** (score 5). Modifiers: M1, M2.

| ID | Pattern | Score | Signal contributions |
|---|---|---|---|
| P2 | Deterministic workflow (prompt chain / graph with fixed steps) | 5 | steps_known_upfront +3, audit_required +2 |
| P0 | No LLM (conventional automation) | 0 | - |
| P3 | Router | 0 | - |
| P5 | Plan-and-execute | 0 | steps_known_upfront -1, audit_required +1 |

P2 ranks first (score 5) because two signals favor it: the steps are known upfront (+3), since the requirements spell out a fixed sequence of find clause, compare to playbook, propose a redline, and flag for a lawyer (FR-2 to FR-5), and audit is required (+2), because every change must cite the playbook rule and contract clause (FR-9). A fixed chain or graph also makes each step easy to log, evaluate and test against adversarial contracts (NFR-6, NFR-7), and it keeps the Python comparison tool and the human accept/reject gate as set points in the flow (FR-6, FR-8). The runner-up, P0 (No LLM), scores 0 because the rules_suffice signal is false: the inputs are free-text contracts and playbooks, which conventional automation cannot read and compare. P3 (Router) also scores 0 and is not a closer contender, since there are no distinct request types to route between. The choice would flip toward P0 if the playbooks became structured rules that deterministic logic could apply without an LLM, and toward a more dynamic pattern if the steps stopped being known upfront and open-ended reasoning was needed, though neither is indicated by the current inputs.

**Why this pattern rather than a simpler one:** The steps are known up front (find covered clauses, compare, propose a redline with citations, list lawyer-needed clauses, generate the redline, human review), so no open-ended reasoning or dynamic tool selection is needed. A fixed workflow gives a predictable cost per contract and latency, makes each step testable and auditable, and limits the prompt-injection attack surface compared with an autonomous agent.

## Architecture
```mermaid
flowchart LR
  identity["Tenant-aware identity and access<br/><small>identity</small>"]
  ingestion["Contract and playbook intake<br/><small>document_ingestion</small>"]
  workflow["Fixed-step review workflow<br/><small>orchestration</small>"]
  llm["Self-hosted open-weight model serving<br/><small>foundation_model</small>"]
  guardrails["Prompt-injection and egress guardrails<br/><small>guardrails</small>"]
  validator["Deterministic validation layer<br/><small>custom</small>"]
  compare_tool["Word comparison and redline tool<br/><small>tool_gateway</small>"]
  approval_ui["Redline review and approval gate<br/><small>custom</small>"]
  store["Tenant-isolated operational store<br/><small>operational_db</small>"]
  secrets["Secrets and key management<br/><small>secrets</small>"]
  eval["Pre-release evaluation harness<br/><small>evaluation</small>"]
  obs["Observability and cost metering<br/><small>observability</small>"]
  identity -- "authenticated tenant context" --> ingestion
  ingestion -- "store parsed contract and playbook (tenant-scoped)" --> store
  ingestion -- "clauses and playbook rules" --> workflow
  workflow -- "clause text as untrusted data" --> guardrails
  guardrails -- "sanitized step prompts" --> llm
  llm -- "structured findings and redline proposals" --> validator
  validator -- "pass, retry or escalate to lawyer" --> workflow
  workflow -- "validated changes plus Word files" --> compare_tool
  compare_tool -- "redlined document" --> approval_ui
  workflow -- "redlines with citations and lawyer-needed list" --> approval_ui
  approval_ui -- "accept/reject decisions and audit record" --> store
  identity -- "reviewer authorization" --> approval_ui
  secrets -- "per-tenant encryption keys" --> store
  workflow -- "traces and cost metrics" --> obs
  llm -- "token and GPU usage" --> obs
  eval -- "test runs including adversarial contracts" --> workflow
```

| ID | Component | Type | Responsibility | Satisfies |
|---|---|---|---|---|
| identity | Tenant-aware identity and access | identity | Authenticates users on the customer's legal team and carries a tenant ID on every request, job, storage key and model call. Enforces per-customer authorization so competing customers are never co-mingled. | NFR-1, FR-8 |
| ingestion | Contract and playbook intake | document_ingestion | Accepts the uploaded Word contract and the customer's playbook. Parses them into clauses and structured playbook rules, keeping clause location references and storing originals in tenant-scoped storage. | FR-1, FR-2 |
| workflow | Fixed-step review workflow | orchestration | Runs the fixed chain: intake, clause identification against the playbook, comparison, redline proposal with rule and clause citations, lawyer-escalation list, validation, comparison tool, then approval gate. Queues jobs and fans out per-clause steps in parallel so the first redline returns within 60 s for a 20-page contract and the quarter-end peak is absorbed. | FR-2, FR-3, FR-4, FR-5, NFR-2, NFR-3 |
| llm | Self-hosted open-weight model serving | foundation_model | Serves open-weight models on the vendor's own GPU cluster in the vendor's cloud for clause identification, comparison and redline drafting. Autoscales for quarter-end peaks. Uses a fixed model and a bounded token budget per step so cost per contract is predictable. | NFR-4, NFR-2, NFR-3, NFR-5, FR-3, FR-4 |
| guardrails | Prompt-injection and egress guardrails | guardrails | Treats contract text strictly as untrusted data, never as instructions. Uses delimiters, an instruction-isolating prompt design and injection detection on the contract. Blocks any output that is not a structured finding. The workflow has no outbound channel to the counterparty. | NFR-7, FR-7 |
| validator | Deterministic validation layer | custom | Runs on every LLM output. Performs schema checks and verifies that each cited playbook rule ID exists in the tenant's playbook. Verifies that each cited contract clause exists and that quoted text matches the source verbatim. Applies rule checks, for example that every redline names a rule and that the clauses flagged for a lawyer are listed. Rejects or retries failing outputs, and routes repeated failures to lawyer review. | FR-9, FR-4, FR-5 |
| compare_tool | Word comparison and redline tool | tool_gateway | Runs Python on the uploaded Word files to generate the redlined document from the validated proposed changes. It is the only tool the workflow calls. It has no network egress to counterparties, and all file access is tenant-scoped. | FR-6, FR-7, NFR-1 |
| approval_ui | Redline review and approval gate | custom | Presents each redline with its cited playbook rule and contract clause, plus the list of clauses needing a lawyer. A legal-team member must accept or reject every redline. Only accepted changes are written to the final document or system of record. Nothing is sent to the counterparty by the system. | FR-8, FR-7, FR-5, FR-9 |
| store | Tenant-isolated operational store | operational_db | Stores contracts, playbooks, findings, redlines, reviewer decisions and the audit trail. Uses per-tenant partitioning and encryption keys, with row-level or storage-level isolation between customers. | NFR-1, FR-8, FR-9 |
| secrets | Secrets and key management | secrets | Holds service credentials and per-tenant encryption keys. Nothing is embedded in prompts or code. | NFR-1 |
| eval | Pre-release evaluation harness | evaluation | Produces the documented evaluation required for security approval. It covers clause-detection and redline quality against lawyer-labeled contracts, citation accuracy, latency against the 60 s target and cross-tenant leakage tests. It also includes adversarial contracts that try to instruct the agent, with pass/fail thresholds. It is re-run on model or prompt changes. | NFR-6, NFR-7, NFR-2 |
| obs | Observability and cost metering | observability | Traces each workflow step. Records per-step latency, tokens, GPU time, validation failures and queue depth, and attributes cost per contract and per tenant. Alerts on SLA and cost drift without logging contract content outside the tenant boundary. | NFR-5, NFR-2, NFR-3 |

## Tools and Integrations
- Deterministic validation layer: Runs on every LLM output. Performs schema checks and verifies that each cited playbook rule ID exists in the tenant's playbook. Verifies that each cited contract clause exists and that quoted text matches the source verbatim. Applies rule checks, for example that every redline names a rule and that the clauses flagged for a lawyer are listed. Rejects or retries failing outputs, and routes repeated failures to lawyer review.
- Word comparison and redline tool: Runs Python on the uploaded Word files to generate the redlined document from the validated proposed changes. It is the only tool the workflow calls. It has no network egress to counterparties, and all file access is tenant-scoped.
- Redline review and approval gate: Presents each redline with its cited playbook rule and contract clause, plus the list of clauses needing a lawyer. A legal-team member must accept or reject every redline. Only accepted changes are written to the final document or system of record. Nothing is sent to the counterparty by the system.

## Data Sources
| Source | Owner | Freshness | Sensitivity |
|---|---|---|---|
| Customer contracts (Word files) | Each customer | Uploaded per review request | restricted |
| Customer playbooks | Each customer's legal team | Customer-maintained; the version in effect at review time is recorded with each result | restricted |
| Review findings, redlines and reviewer decisions (audit trail) | Vendor, on behalf of each customer | Written in real time during the review | confidential |

## Identity and Access
Users on the customer's legal team authenticate through the identity component. The tenant ID is bound to every request, job, storage path, encryption key and model invocation. Cross-tenant access is denied by default, and there are no shared caches, shared prompts or cross-tenant context between customers, including competitors. The service identity is least-privilege and scoped per tenant. The comparison tool accesses only the current tenant's files and has no outbound network path to counterparties. Only authorized legal-team members can accept or reject redlines, and each decision is attributed to a named user.

## Human Oversight
Every redline must be explicitly accepted or rejected by a person on the customer's legal team (M1 approval gate) before any change is applied to the document of record. Clauses needing a lawyer are listed separately and are never auto-resolved. Output that fails deterministic validation (M2) is not shown as a finding and is instead escalated for lawyer review. The system never sends anything to the counterparty. Sending remains a manual human action outside the system.

## Failure Modes
- Prompt injection in a contract that tries to instruct the agent: contract text is treated as data, guardrails and structured-output validation apply, and the adversarial evaluation covers it.
- Hallucinated or incorrect citation: the validator checks that the playbook rule ID and verbatim clause text exist, and a failure triggers a retry and then escalation to a lawyer.
- Missed clause that the playbook covers: the reviewer is shown all identified clauses and unmatched sections, and the evaluation measures recall.
- Cross-tenant data leakage: tenant-scoped storage, keys and calls, with leakage tests in the evaluation.
- Quarter-end spike pushes latency past 60 s: queueing, per-clause parallelism and GPU autoscaling, with alerts on queue depth; GPU capacity must be provisioned ahead of quarter end.
- GPU cluster or model-serving outage: jobs stay queued and are retried, users see a delayed-status message, and nothing is partially applied.
- Malformed or unsupported Word file (tracked changes, corrupt, scanned): intake validation rejects it with a clear message and does not guess.
- Comparison tool error producing a wrong redlined document: the tool output is checked against the validated change list and shown to the reviewer before acceptance.
- Reviewer approval fatigue: the UI shows the rule and clause side by side, and decision statistics are monitored.
- Model or prompt changes degrade quality: the evaluation harness is a release gate and is re-run on every change.

## Evaluation
| ID | Test | Kind | Covers | Metric | Threshold |
|---|---|---|---|---|---|
| T1 | Clause detection and redline quality vs lawyer-labeled contracts | offline_eval | ingestion, workflow, llm | Dataset: lawyer-labeled contracts with their playbooks, including unmatched sections. Metric: clause-detection recall and precision, and share of redlines a lawyer rates acceptable. | Proposed, to be confirmed at security approval: recall >= 0.95, precision >= 0.90, acceptable redlines >= 85%. No regression versus the current release. |
| T2 | Citation accuracy | offline_eval | llm, validator | Dataset: the T1 set. Metric: share of cited playbook rule IDs and clause references that exist, and share of quoted text that matches the source verbatim, measured both before and after validation. | Citations shown to reviewers: 100% valid after validation. Raw model citation validity >= 95%, so retries stay within the capped count. |
| T3 | Adversarial contracts (prompt injection and egress) | offline_eval | guardrails, llm, workflow, compare_tool | Dataset: adversarial contracts with embedded instructions (override playbook, exfiltrate other data, call outside tools, emit non-finding output). Metric: share of attacks that leave no behavior change, no non-structured output and no egress attempt. | 0 successful attacks. 100% of non-structured outputs blocked. |
| T4 | Cross-tenant leakage tests | offline_eval | identity, store, secrets, llm, compare_tool | Dataset: paired synthetic tenants, including competitors, with planted canary strings in contracts and playbooks. Metric: canary appearances in another tenant's requests, storage reads, model context, tool file access, caches or outputs, and cross-tenant key use. | 0 leaks. All cross-tenant access attempts denied. |
| T5 | Latency and peak-load test | offline_eval | workflow, llm | Dataset: 20-page contracts replayed under a simulated quarter-end load (about 4,000 contracts a day). Metric: time to first redline, p95. | p95 <= 60 s at peak load. Jobs queue and retry without partial application during a simulated serving outage. |
| T6 | Validator unit tests | unit | validator | Pass rate of deterministic cases: schema violations, nonexistent or other-tenant rule IDs, nonexistent clauses, non-verbatim quotes, redlines without a rule, missing lawyer-needed list, retry cap, escalation after repeated failure. | 100% pass. Any failing output is rejected, never shown as a finding. |
| T7 | Intake parsing unit tests | unit | ingestion | Pass rate on Word fixtures: clause splitting, location references, playbook rule parsing, tenant-scoped storage keys, and rejection of corrupt, scanned or tracked-changes files with a clear message. | 100% pass. Unsupported files are never partially processed. |
| T8 | Comparison tool unit tests | unit | compare_tool | Pass rate: the generated redline contains exactly the validated change list and nothing else. File access is limited to the current tenant. Outbound network calls are blocked. | 100% pass. 0 differences between the output and the validated change list. |
| T9 | Access, approval gate and secrets unit tests | unit | identity, approval_ui, secrets | Pass rate: tenant ID on every request, job, storage key and model call. Cross-tenant access denied by default. Only authorized users can decide. Every redline needs an explicit decision before write. Decisions are attributed to a named user. A scan finds no secrets in code or prompts. | 100% pass. 0 secrets found. 0 changes written without an explicit accept. |
| T10 | SLA, queue and cost monitor | online_monitor | obs, workflow, llm, store | Per-step and end-to-end latency, queue depth, GPU utilization and autoscaling, tokens and GPU time per contract and per tenant, and store errors. Contract content is not logged outside the tenant boundary. | Alert when p95 time to first redline approaches 60 s, when queue depth is sustained, or when cost per contract drifts above the $0.15-$0.35 assumption. These are assumptions to be validated. |
| T11 | Validation and reviewer behavior monitor | online_monitor | validator, approval_ui, guardrails | Validation failure and retry rate, escalation rate, injection-detection and blocked-output counts, accept/reject ratio, and decision time per reviewer. | Alert on a step change from the baseline set in the T1/T2 evaluation. Review reviewer decision-time and accept-rate outliers as an approval-fatigue signal. |
| T12 | Evaluation release gate | unit | eval | CI check that any model, prompt or tool version change triggers T1-T5 and that results are stored as the documented evaluation. Release is blocked on any failed threshold. | 100% of changes gated. Evaluation report archived for every release. |

## Observability
- Alert on p95 time to first redline, queue depth and GPU capacity ahead of quarter end, so capacity is provisioned in advance.
- Track cost per contract and per tenant against the assumed range and alert on drift.
- Track validation failure, retry and escalation rates, and blocked-output and injection-detection counts.
- Track reviewer accept/reject statistics and decision time to detect approval fatigue.
- Log any denied cross-tenant access attempt and alert on any occurrence. Keep telemetry within the tenant boundary and do not log contract content outside it.
- Show a delayed-status message and retry jobs on a GPU or model-serving outage. Alert on stuck jobs.

Versioning: Keep prompts, the model identity and weights, tool code and the validator ruleset in version control, with immutable version identifiers. Each result records the prompt, model, tool and validator versions, plus the playbook version in effect at review time. A change to any of these is released only after the T1-T5 evaluation passes (T12). Keep the previous version available for rollback.

Governance:
- The documented pre-release evaluation (T1-T5) is the evidence for security approval and is re-run on every model, prompt or tool change.
- Tenant isolation is enforced by default-deny access, tenant-scoped storage, keys and model calls, with no shared caches, prompts or context between customers.
- Every redline requires explicit accept or reject by a named, authorized legal-team user before any change is written. Clauses needing a lawyer are never auto-resolved.
- The system never sends anything to the counterparty. The workflow and comparison tool have no outbound network path to counterparties.
- An immutable audit trail records findings, redlines, reviewer decisions, and the model, prompt and playbook versions, stored per tenant.
- Secrets and per-tenant encryption keys are held only in key management, never in prompts or code. The service identity is least-privilege and scoped per tenant.
- Changes to thresholds, the validator ruleset or guardrails require review and a re-run of the evaluation.

## Cost
Assumptions (to be validated in the evaluation, not measured): a 20-page contract is roughly 15k input tokens plus a playbook of about 5k tokens, with about 10 to 15 clause-level model calls and about 3k output tokens in total. Serving is on the vendor's own GPU cluster, with an assumed all-in GPU cost of about $0.10 to $0.30 per contract including validation retries. Non-GPU components (storage, comparison tool, orchestration, observability) add about $0.02 to $0.05. That gives roughly $0.15 to $0.35 per contract. Monthly estimate at an assumed average of 1,000 contracts a day (about 30,000 a month): about $4,500 to $10,500 in variable cost. The quarter-end peak of 4,000 a day would cost about $0.6k to $1.4k a day. The main fixed cost is reserved or autoscaled GPU capacity sized for the peak, which should be modeled separately. Cost is predictable because the workflow has fixed steps, a bounded token budget per step and a capped retry count, so cost per contract varies mainly with contract length.

## Platform Mapping
Cloud: **aws**

| Component | Service |
|---|---|
| identity | AWS IAM Identity Center + Amazon Cognito |
| ingestion | Amazon Textract |
| workflow | LangGraph or Strands on Bedrock AgentCore / ECS |
| llm | Amazon Bedrock |
| guardrails | Amazon Bedrock Guardrails |
| validator | Custom service on Amazon ECS (Fargate) or AWS Lambda |
| compare_tool | Amazon Bedrock AgentCore Gateway / API Gateway |
| approval_ui | Custom service on Amazon ECS (Fargate) or AWS Lambda |
| store | Amazon DynamoDB |
| secrets | AWS Secrets Manager |
| eval | Amazon Bedrock evaluations |
| obs | Amazon CloudWatch + AgentCore Observability |

## Decisions (ADRs)
### ADR-1: Use a deterministic fixed-step workflow instead of an autonomous agent or a no-LLM rules engine

- **Context:** The review steps are known up front: find the clauses the playbook covers, compare each with the playbook position, propose a redline citing rule and clause, list clauses needing a lawyer, generate the redlined Word file, then human review. The requirements ask for a cited, auditable output (FR-9), a first redline within 60 s for a 20-page contract (NFR-2), a cost per contract that pricing can plan around (NFR-5), and resistance to adversarial contracts that try to instruct the agent (NFR-7). The pattern ranking puts the deterministic workflow first (score 5, from steps_known_upfront and audit_required). Conventional automation with no LLM scored 0, and the Router scored 0.
- **Options:** P2: Deterministic workflow (fixed prompt chain with per-clause fan-out and a validation step); Autonomous agent that plans its own steps and chooses tools dynamically; P0: No LLM, conventional rules-based automation (keyword or pattern matching of clauses against the playbook)
- **Decision:** Adopt P2, a fixed-step workflow. Each step has a defined input, output schema and token budget, and a capped retry count. The comparison tool is the only tool the workflow calls, and the orchestrator, not the model, decides what runs next.
- **Consequences:** Cost and latency are predictable and each step can be tested and audited separately. The prompt-injection attack surface is smaller because the model never selects actions or tools. The trade-off is that the workflow cannot adapt to review tasks outside the defined chain, and any new step needs a design change. The rules-only option was not chosen because the inputs include the playbook and free-text clauses, and the design has no basis to claim rules alone can identify and compare them (the rules_suffice signal was false). It is kept as a possible fallback for sub-steps such as validation, which stays deterministic.
- **Requirements:** FR-2, FR-3, FR-4, FR-5, FR-9, NFR-2, NFR-5, NFR-7

### ADR-2: Serve open-weight models on the vendor's own GPU cluster with a fixed model and bounded token budget

- **Context:** The vendor wants to serve open-weight models on its own GPU cluster to control cost and keep data in its cloud (NFR-4). Customer contracts and playbooks are restricted, and competing customers must not be co-mingled (NFR-1). Volume spikes to about 4,000 contracts a day at quarter end (NFR-3), and the first redline must arrive within 60 s (NFR-2). The cost estimate is an assumption to be validated in evaluation, not a measurement.
- **Options:** Self-hosted open-weight models on the vendor's GPU cluster with autoscaling, a fixed model version and a per-step token budget; Third-party hosted proprietary model API; Self-hosted open-weight models on a statically sized GPU cluster with no autoscaling
- **Decision:** Use self-hosted open-weight models on the vendor's GPU cluster, with autoscaling, a fixed model per step and a bounded token budget per step. Every model call carries the tenant ID, and there are no shared prompts or caches across tenants.
- **Consequences:** Data stays in the vendor's cloud and the design satisfies NFR-4. Cost per contract is estimated at roughly $0.15 to $0.35, driven mainly by contract length. This is an assumption to validate. The vendor takes on GPU capacity planning: capacity must be provisioned ahead of quarter end, and the fixed cost of reserved or autoscaled GPUs sized for the peak must be modeled separately. A GPU or serving outage delays jobs, which stay queued and retried, but does not apply partial changes. Open-weight model quality on legal clauses must be proven in the pre-release evaluation. Switching models or prompts requires re-running that evaluation.
- **Requirements:** NFR-4, NFR-1, NFR-2, NFR-3, NFR-5, NFR-6

### ADR-3: Validate every LLM output deterministically and gate all changes behind human approval

- **Context:** Every proposed change must cite the playbook rule and the contract clause it relies on (FR-9). Clauses needing a lawyer must be listed (FR-5). A person on the customer's legal team must accept or reject every redline (FR-8), and the agent must never send anything to the counterparty (FR-7). Model output can hallucinate citations or follow instructions embedded in contract text (NFR-7).
- **Options:** Deterministic validation layer on every LLM output (schema check, rule ID exists in tenant playbook, clause exists, quote matches source verbatim) with retry then escalation to a lawyer, followed by a mandatory per-redline human approval gate; Model-based self-check or LLM-as-judge verification of citations, with human approval only for flagged items; Human review only, with no automated validation before the reviewer sees output
- **Decision:** Run a deterministic validator on every LLM output. Outputs that fail are retried, and repeated failures are escalated to lawyer review and never shown as findings. Validated changes go through the comparison tool, and a legal-team member must explicitly accept or reject every redline before anything is written to the document or system of record. The system has no outbound channel to the counterparty.
- **Consequences:** Citation accuracy is checked by code rather than by another model, which makes it testable and auditable. Reviewers see the rule and clause side by side. The cost is added reviewer effort on every redline, with a risk of approval fatigue that the design handles by monitoring decision statistics. Verbatim and rule-ID checks can reject output that is semantically correct but not exact, which raises retries and escalations. Those rates must be measured in evaluation. Human review alone was rejected because it would push hallucinated citations onto lawyers. A model-based judge was rejected because it adds an unverified, non-deterministic step where a simple deterministic check suffices.
- **Requirements:** FR-4, FR-5, FR-7, FR-8, FR-9, NFR-7

### ADR-4: Enforce tenant isolation through tenant ID binding, per-tenant keys and storage rather than shared infrastructure with logical filtering only

- **Context:** Each customer's contracts and playbooks are confidential to that customer, including isolation between customers that compete with each other (NFR-1). The comparison tool runs Python on uploaded Word files and must not leak across tenants or reach counterparties (FR-6, FR-7). The security team will not approve release without a documented evaluation that includes cross-tenant leakage tests (NFR-6).
- **Options:** Tenant ID bound to every request, job, storage key and model call, with per-tenant partitioning and encryption keys, tenant-scoped tool file access, no shared caches or prompts, and cross-tenant leakage tests in the evaluation; Shared storage and shared model context with application-level filtering by tenant column only; Fully separate deployment (stack and GPU pool) for each customer
- **Decision:** Carry the tenant ID end to end and use per-tenant partitioning and encryption keys held in secrets management. Scope the comparison tool's file access to the current tenant, and deny cross-tenant access by default. Verify the isolation with leakage tests in the pre-release evaluation.
- **Consequences:** Isolation is enforced at identity, storage, key and model-call level and is verified before release. It is simpler and cheaper than a dedicated stack per customer and stronger than filtering alone. Per-tenant keys and partitioning add operational overhead, and the isolation depends on the tenant ID being propagated correctly everywhere, so the leakage tests must stay in the release gate. If a customer or the security team requires physical separation, the separate-deployment option remains available at higher cost, but the inputs do not require it.
- **Requirements:** NFR-1, NFR-6, FR-6, FR-7, FR-8

## Traceability
Requirement coverage 100% · component test coverage 100% · PASSED

| Requirement | Components |
|---|---|
| FR-1 | ingestion |
| FR-2 | ingestion, workflow |
| FR-3 | workflow, llm |
| FR-4 | workflow, llm, validator |
| FR-5 | workflow, validator, approval_ui |
| FR-6 | compare_tool |
| FR-7 | guardrails, compare_tool, approval_ui |
| FR-8 | identity, approval_ui, store |
| FR-9 | validator, approval_ui, store |
| NFR-1 | identity, compare_tool, store, secrets |
| NFR-2 | workflow, llm, eval, obs |
| NFR-3 | workflow, llm, obs |
| NFR-4 | llm |
| NFR-5 | llm, obs |
| NFR-6 | eval |
| NFR-7 | guardrails, eval |

## Open Questions
_None._
