# Prior Auth Review

## Executive Summary

**The problem.** Our health plan receives about 1,200 prior authorization requests a week for outpatient imaging, such as magnetic resonance imaging (MRI) of the spine. A nurse reads each request, the member's eligibility, the coverage policy and the clinical notes. Even straightforward cases take 15–25 minutes, and providers and patients can wait up to five business days.

**What the solution does.** A fixed, step-by-step workflow prepares every case. It gathers the request, eligibility, policy and notes, and a computer model checks each policy criterion against the notes. Every finding cites the policy clause and the exact note sentence it relies on, and automated checks confirm those citations are real. Simple rules then propose one of three outcomes: approve (only if every criterion is clearly met), ask the provider for missing documentation, or send the case to a nurse with the findings. The system has no way to deny a request.

**How people stay in control.** An authorized person must confirm every approval, documentation request and routing record before anything is written to our systems. Any adverse or uncertain case goes to a licensed nurse. Clinical policy owners review each quarterly policy update before it goes live. Every decision is stored permanently with its evidence, so we can explain it to regulators years later.

**Cost.** About $0.20 per request in usage fees, plus roughly $1,500 a month in fixed platform costs. These are illustrative figures: about $3,500 a month at 10,000 cases a month. Real contract prices and volumes are needed to confirm.

**Key risks.** The model could overstate that a criterion is met; citation checks and human confirmation address this. Electronic health record (EHR) connections can fail; those cases go to a nurse and are never approved. Patient information could leak into logs; we send only the minimum necessary and keep clinical text out of logs. Please confirm that the two-minute target means the approval proposal is ready for one-click confirmation, not final human sign-off.

**Suggested pilot (12 weeks).** Weeks 1–4: build the system and run the compliance evaluation, including missing-notes and system-failure tests. Weeks 5–8: run it quietly alongside nurses, comparing its proposals with their decisions. Weeks 9–12: limited live use on clear approvals, then a go or no-go review.

## Problem Statement
A regional health plan receives about 1,200 prior authorization requests a week for outpatient imaging, such as
MRI of the lumbar spine. A nurse reviewer reads each request, checks the member's eligibility, reads the coverage
policy and the ordering provider's clinical notes, and decides whether each policy criterion is met. Straightforward
cases take 15–25 minutes; providers and patients wait up to five business days for an answer.

The plan wants an agent that prepares each case: it gathers the request, eligibility, policy and notes, evaluates
every criterion against the notes, and either approves a request that clearly meets every criterion, asks the
provider for missing documentation, or routes the case to a nurse reviewer with its findings. The agent must never
deny a request: any adverse or uncertain decision is made by a licensed clinician. Every criterion finding must cite
the policy clause and the sentence in the clinical notes it relies on, because reviewers, providers and state
regulators can ask why a decision was made, years later.

The notes contain protected health information, so the plan's privacy office requires that only the minimum
necessary information leaves the claims system, and that logs do not keep clinical text. Eligibility and
policies live in the claims system; clinical notes arrive through the provider portal and an electronic health
record gateway that sometimes times out. Coverage policies change quarterly. The plan's compliance team will not
allow a release unless it passes a documented evaluation, including runs where the notes are missing or the
gateway fails. Answers for clear approvals should be ready within two minutes.

## Requirements
| ID | Requirement | Source (brief) |
|---|---|---|
| FR-1 | The agent shall gather the prior authorization request, the member's eligibility, the applicable coverage policy and the ordering provider's clinical notes for each case. | "it gathers the request, eligibility, policy and notes" |
| FR-2 | The agent shall evaluate every policy criterion against the clinical notes and record a finding for each criterion. | "evaluates every criterion against the notes" |
| FR-3 | The agent shall approve a request only when it clearly meets every policy criterion. | "approves a request that clearly meets every criterion" |
| FR-4 | The agent shall ask the ordering provider for missing documentation when the documentation needed to evaluate a criterion is absent. | "asks the provider for missing documentation" |
| FR-5 | The agent shall route a case that is not an clear approval to a nurse reviewer together with its criterion findings. | "routes the case to a nurse reviewer with its findings" |
| FR-6 | The agent shall never deny a request; every adverse or uncertain decision shall be left to a licensed clinician. | "The agent must never deny a request: any adverse or uncertain decision is made by a licensed clinician." |
| FR-7 | Each criterion finding shall cite the specific policy clause and the specific sentence in the clinical notes on which it relies. | "Every criterion finding must cite the policy clause and the sentence in the clinical notes it relies on" |
| NFR-1 | The system shall let only the minimum necessary information leave the claims system. | "only the minimum necessary information leaves the claims system" |
| NFR-2 | System logs shall not contain clinical text. | "logs do not keep clinical text" |
| NFR-3 | Each decision and its criterion findings shall be explainable to reviewers, providers and state regulators on request, including years after the decision. | "reviewers, providers and state regulators can ask why a decision was made, years later" |
| NFR-4 | The system shall not be released unless it passes a documented evaluation that includes runs where the clinical notes are missing and runs where the EHR gateway fails. | "The plan's compliance team will not allow a release unless it passes a documented evaluation, including runs where the notes are missing or the gateway fails." |
| NFR-5 | The system shall return answers for clear approvals within two minutes. | "Answers for clear approvals should be ready within two minutes." |
| NFR-6 | The system shall accommodate quarterly changes to coverage policies. | "Coverage policies change quarterly." |

## Pattern Selection
**Selected: P2 Deterministic workflow (prompt chain / graph with fixed steps)** (score 5). Modifiers: M1, M2.

| ID | Pattern | Score | Signal contributions |
|---|---|---|---|
| P2 | Deterministic workflow (prompt chain / graph with fixed steps) | 5 | steps_known_upfront +3, audit_required +2 |
| P0 | No LLM (conventional automation) | 0 | - |
| P3 | Router | 0 | - |
| P5 | Plan-and-execute | 0 | steps_known_upfront -1, audit_required +1 |

P2 ranks first (score 5) because the steps are known upfront (+3): the process is gather, evaluate every criterion, then approve, ask for documentation, or route to a nurse. Audit is also required (+2), since reviewers, providers and regulators must be able to ask why a decision was made years later (NFR-3), and a fixed-step workflow gives a repeatable, inspectable path for each finding. The runner-up, P0 (No LLM), scores 0 because the `rules_suffice` signal is false, so conventional automation alone is not indicated for evaluating criteria against clinical notes; P3 (Router) also scores 0 because there are no distinct request types to route between. The choice would flip toward P0 if requirements showed that rules suffice, for example if criteria could be checked from structured data without reading free-text notes. It would flip toward P3 if distinct request types emerged that need different handling paths.

**Why this pattern rather than a simpler one:** The steps and routing outcomes are fully known upfront, with no open-ended reasoning or tool selection, and an audit trail is required. A fixed workflow with the LLM confined to criterion evaluation is the simplest design that gives deterministic routing and testable behavior. It also keeps the system from denying a request by construction. An autonomous agent would add unpredictability without any benefit.

## Architecture
```mermaid
flowchart LR
  workflow["Prior authorization workflow engine<br/><small>orchestration</small>"]
  identity["Workforce and service identity<br/><small>identity</small>"]
  secrets["Secrets manager<br/><small>secrets</small>"]
  ehr_gateway["Claims and EHR tool gateway<br/><small>tool_gateway</small>"]
  policy_ingest["Quarterly policy ingestion<br/><small>document_ingestion</small>"]
  policy_store["Versioned policy store<br/><small>operational_db</small>"]
  minimizer["Minimum-necessary filter and redaction<br/><small>guardrails</small>"]
  llm["Criterion evaluation model<br/><small>foundation_model</small>"]
  validator["Deterministic validation layer<br/><small>custom</small>"]
  router["Deterministic decision router<br/><small>custom</small>"]
  approval_gate["Human approval gate and nurse review queue<br/><small>custom</small>"]
  decision_store["Immutable decision record store<br/><small>operational_db</small>"]
  observability["Metadata-only observability<br/><small>observability</small>"]
  evaluation["Release evaluation harness<br/><small>evaluation</small>"]
  workflow -- "authenticate service and user context" --> identity
  ehr_gateway -- "fetch credentials" --> secrets
  workflow -- "read request, eligibility, notes (minimum necessary)" --> ehr_gateway
  ehr_gateway -- "data or typed error (notes missing, gateway failure)" --> workflow
  policy_ingest -- "publish reviewed policy version" --> policy_store
  workflow -- "load pinned policy version and criteria" --> policy_store
  workflow -- "notes and criteria for evaluation" --> minimizer
  minimizer -- "minimized prompt per criterion" --> llm
  llm -- "structured findings with citations" --> validator
  validator -- "validated findings or failure" --> router
  router -- "proposed action: approve, request documentation, or nurse review" --> approval_gate
  approval_gate -- "approved write to system of record" --> ehr_gateway
  validator -- "findings and validation results" --> decision_store
  approval_gate -- "approver, action and timestamp" --> decision_store
  workflow -- "metadata-only telemetry" --> observability
  minimizer -- "scrubbed log payloads" --> observability
  evaluation -- "pre-release test runs with injected faults" --> workflow
```

| ID | Component | Type | Responsibility | Satisfies |
|---|---|---|---|---|
| workflow | Prior authorization workflow engine | orchestration | Runs the fixed step graph per case: gather request, eligibility, policy and notes; evaluate each criterion; validate; route to approval-candidate, missing-documentation request or nurse review. The LLM only fills in the criterion-evaluation step and never chooses the next step. Steps run in parallel where possible so clear approvals are ready within two minutes. | FR-1, FR-2, FR-4, FR-5, NFR-5 |
| identity | Workforce and service identity | identity | Single sign-on for nurse reviewers and approvers with role-based access. A least-privilege service identity for the workflow, with read scopes for gathering and a separate, narrower write scope for approved actions. | NFR-1, NFR-3 |
| secrets | Secrets manager | secrets | Holds the EHR gateway and claims system credentials and the model endpoint keys. Keeps them out of code and prompts and rotates them. | NFR-1 |
| ehr_gateway | Claims and EHR tool gateway | tool_gateway | The only path to the claims/UM system and the EHR gateway. Exposes a small allow-listed set of operations: read request, read eligibility, read notes, write decision, send documentation request, route to nurse. Enforces field-level minimum-necessary retrieval, timeouts and retries, and returns explicit typed errors (notes missing, gateway unavailable) to the workflow. | FR-1, FR-4, FR-5, NFR-1 |
| policy_ingest | Quarterly policy ingestion | document_ingestion | Converts each new coverage policy version into structured criteria with stable clause ids. A clinical policy owner reviews and publishes it before activation. Notes are split into numbered sentences at case time so citations can be checked. | FR-7, NFR-6 |
| policy_store | Versioned policy store | operational_db | Stores each coverage policy version with its effective dates, criteria and clause ids. Each case is evaluated against a pinned policy version, so quarterly changes need no code change and old decisions stay reproducible. | FR-1, FR-7, NFR-3, NFR-6 |
| minimizer | Minimum-necessary filter and redaction | guardrails | Before any model call, strips fields not needed for criterion evaluation (for example direct identifiers) and sends only the relevant notes and the criterion text. Applies a clinical-text scrubber to all log and telemetry payloads. | NFR-1, NFR-2 |
| llm | Criterion evaluation model | foundation_model | For each policy criterion, returns a structured finding (met / not met / insufficient documentation) with the policy clause id and the quoted supporting sentence id from the notes. Runs on an enterprise endpoint with no training use and no retention of prompts. It cannot deny or take actions. | FR-2, FR-7 |
| validator | Deterministic validation layer | custom | On every LLM output: JSON schema check; verifies every criterion in the pinned policy has exactly one finding; verifies each cited clause id exists in the policy version and each cited sentence exists verbatim in the notes; rejects any output with a denial or an unsupported 'met'. Failed outputs are retried once, then routed to a nurse. | FR-2, FR-3, FR-6, FR-7 |
| router | Deterministic decision router | custom | Rule-based, with no LLM. Proposes 'approve' only if all criteria are 'met' with validated citations. Proposes a documentation request if any finding is 'insufficient documentation' and nothing is 'not met'. Everything else, including validation failures, missing notes, gateway errors and any not-met criterion, goes to a nurse reviewer with its findings. No deny outcome exists in the rule set. | FR-3, FR-4, FR-5, FR-6 |
| approval_gate | Human approval gate and nurse review queue | custom | Any write to a system of record (approval, outbound documentation request, routing record) needs explicit approval from an authorized user before the gateway executes it. Shows the findings with cited clauses and sentences. Nurse reviewers receive non-approvals and any adverse or uncertain decision is made only by a licensed clinician. | FR-3, FR-5, FR-6 |
| decision_store | Immutable decision record store | operational_db | Append-only record per case: pinned policy version, criterion findings with clause and sentence citations, cited note excerpts, model and prompt versions, validation results, proposed action, approver identity and timestamp. It sits inside the plan's controlled environment under the plan's retention policy so decisions can be explained to reviewers, providers and regulators years later. | NFR-3, FR-7 |
| observability | Metadata-only observability | observability | Records step latency, error codes, validation failure rates, retry counts and routing outcomes by case id only, with no clinical text. Alerts when the two-minute target for clear approvals is at risk. | NFR-2, NFR-5 |
| evaluation | Release evaluation harness | evaluation | Runs a documented, versioned test suite before every release and every policy or prompt change. It includes labelled cases with known outcomes, missing-notes runs, EHR gateway failure runs, citation-fabrication checks and a check that no deny occurs. Stores the signed-off report as release evidence for compliance. | NFR-4, NFR-6 |

## Tools and Integrations
- Claims and EHR tool gateway: The only path to the claims/UM system and the EHR gateway. Exposes a small allow-listed set of operations: read request, read eligibility, read notes, write decision, send documentation request, route to nurse. Enforces field-level minimum-necessary retrieval, timeouts and retries, and returns explicit typed errors (notes missing, gateway unavailable) to the workflow.
- Deterministic validation layer: On every LLM output: JSON schema check; verifies every criterion in the pinned policy has exactly one finding; verifies each cited clause id exists in the policy version and each cited sentence exists verbatim in the notes; rejects any output with a denial or an unsupported 'met'. Failed outputs are retried once, then routed to a nurse.
- Deterministic decision router: Rule-based, with no LLM. Proposes 'approve' only if all criteria are 'met' with validated citations. Proposes a documentation request if any finding is 'insufficient documentation' and nothing is 'not met'. Everything else, including validation failures, missing notes, gateway errors and any not-met criterion, goes to a nurse reviewer with its findings. No deny outcome exists in the rule set.
- Human approval gate and nurse review queue: Any write to a system of record (approval, outbound documentation request, routing record) needs explicit approval from an authorized user before the gateway executes it. Shows the findings with cited clauses and sentences. Nurse reviewers receive non-approvals and any adverse or uncertain decision is made only by a licensed clinician.

## Data Sources
| Source | Owner | Freshness | Sensitivity |
|---|---|---|---|
| Prior authorization request | Health plan claims/UM system | Read per case at runtime | restricted |
| Member eligibility | Health plan claims system | Read per case at runtime | restricted |
| Coverage policy (criteria and clauses) | Health plan clinical policy owner | Versioned; refreshed quarterly | internal |
| Ordering provider clinical notes | Ordering provider, via EHR gateway | Read per case at runtime | restricted |
| Decision records and approver actions | Health plan UM compliance | Written per decision; retained long term | restricted |

## Identity and Access
Reviewers and approvers sign in through SSO with roles (nurse reviewer, approver, auditor, policy owner). The workflow runs under a least-privilege service identity with read scopes for gathering and a separate write scope the gateway honors only with an approval token from the gate. The model has no direct access to systems or credentials. Secrets live in a secrets manager. Only the gateway can reach the claims and EHR systems. Decision records are read-only to auditors, and each case sees only the fields it needs.

## Human Oversight
M1 applies: every system-of-record write (approval, documentation request to the provider, routing record) needs explicit approval by an authorized user, who sees the findings with clause and sentence citations. Every non-clear case goes to a licensed nurse reviewer with findings, and the system never denies. Because of the gate, the two-minute target for clear approvals is read as time until the validated approval proposal is ready for one-click confirmation, not time until a human confirms. The business should confirm this interpretation. Policy versions are published only after clinical policy owner review.

## Failure Modes
- Notes missing or incomplete: the gateway returns a typed error and the case goes to a nurse or a documentation request. It is never approved.
- EHR or claims gateway outage or timeout: bounded retries, then the case is routed to a nurse with a 'data unavailable' reason and nothing is written.
- LLM fabricates or mis-cites a clause or sentence: the citation check fails, one retry follows, then the case goes to a nurse.
- LLM overstates a criterion as met: the router approves only if every criterion is met with validated citations, and the approver sees the cited text before confirming.
- Malformed or schema-invalid model output: rejected by the validator and handled as above.
- Wrong policy version applied after quarterly change: the version is pinned from the effective date and recorded on every decision. The evaluation suite is rerun on each new version.
- Approver backlog delays clear approvals: observability alerts on queue age against the two-minute target.
- Clinical text leaks into logs: the scrubber and metadata-only telemetry reduce the risk, and log sampling audits check for it.
- Model endpoint outage: cases are queued or routed to nurses, and there is no automatic approval without a validated model result.

## Evaluation
| ID | Test | Kind | Covers | Metric | Threshold |
|---|---|---|---|---|---|
| T1 | Criterion evaluation accuracy on labelled cases | offline_eval | llm, minimizer, policy_store | Dataset: versioned set of labelled prior-authorization cases with clinician-agreed per-criterion outcomes (met / not met / insufficient documentation), run on minimized prompts against the pinned policy version. Metrics: unsupported 'met' rate and per-criterion agreement with labels. | Proposed: 0 unsupported 'met' findings reaching an approval proposal; criterion agreement at or above a target set by the clinical policy owner before release (proposed 95%). |
| T2 | Citation fabrication and mis-citation check | offline_eval | llm, validator | Dataset: cases plus injected fabricated or mis-cited clause ids and sentence ids, and malformed or schema-invalid outputs. Metric: share of bad outputs rejected by the validator, then retried once and routed to a nurse. | 100% of injected bad citations or invalid outputs rejected; 0 reach the router as validated. |
| T3 | Validator unit tests | unit | validator, workflow | Deterministic tests: JSON schema check; exactly one finding per criterion in the pinned policy; clause id exists in the policy version; cited sentence exists verbatim in the notes; denial or unsupported 'met' rejected; one retry then nurse routing; the LLM never selects the next step. | 100% pass; blocks release on any failure. |
| T4 | Decision router rule-table tests | unit | router | Exhaustive table-driven tests over finding combinations and error states: approve only if all criteria are met with validated citations; documentation request only if some finding is insufficient and none is not met; everything else (validation failure, missing notes, gateway error, any not-met) goes to a nurse; no deny outcome exists. | 100% pass; 0 deny outcomes across all cases. |
| T5 | Fault-injection and failure-mode runs | offline_eval | workflow, ehr_gateway, llm | Injected faults: notes missing, EHR or claims gateway outage and timeout, model endpoint outage, malformed model output. Metric: share of cases routed to a nurse, a documentation request or a queue with nothing written and no automatic approval. | 100% of fault cases safely handled; 0 approvals and 0 writes produced under a fault. |
| T6 | Gateway, identity, secrets and approval-gate enforcement tests | unit | ehr_gateway, identity, secrets, approval_gate | Tests: only allow-listed operations exposed; field-level minimum-necessary retrieval; typed errors, timeouts and bounded retries; write rejected without a valid approval token from the gate; role-based access for nurse reviewer, approver, auditor and policy owner; service read scope cannot write; secret scan finds no credentials in code or prompts; credential rotation works. | 100% pass; 0 writes without an approval token; 0 secrets found in code or prompts. |
| T7 | Minimizer and log scrubber tests | unit | minimizer, observability | Tests on synthetic clinical notes with seeded identifiers: direct identifiers and unneeded fields removed from model prompts; scrubber removes clinical text from log and telemetry payloads; observability records metadata only. | 0 seeded identifiers in model prompts; 0 clinical text strings in telemetry output. |
| T8 | Policy ingestion, version pinning and release evidence check | offline_eval | policy_ingest, policy_store, evaluation | Per new policy version: extracted criteria and clause ids compared with the policy owner's reviewed version; activation blocked without owner publication; replay of earlier cases against their pinned versions reproduces the same findings inputs; the full evaluation suite is rerun on every release and every policy or prompt change, with a signed-off report stored. | 100% criteria match the reviewed version; 0 activations without owner publication; replays use the pinned version in 100% of cases; signed-off report exists before release. |
| T9 | Decision record completeness and immutability tests | unit | decision_store, approval_gate | Tests: each case record is append-only and contains pinned policy version, findings with clause and sentence citations, cited excerpts, model and prompt versions, validation results, proposed action, approver identity and timestamp; auditors have read-only access; every write has a matching approver record. | 100% of records complete; 0 successful updates or deletes; 0 writes without an approver record. |
| T10 | Clear-approval latency and approver queue age monitor | online_monitor | workflow, observability | Time from case start until the validated approval proposal is ready for one-click confirmation (p95), plus approver queue age and step latencies. | Alert when p95 approaches the two-minute target (proposed alert at 90 seconds) or queue age puts the target at risk. |
| T11 | Validation failure, retry and routing mix monitor | online_monitor | validator, router, llm, ehr_gateway | Metadata-only rates by case id: validation failure rate, retry count, gateway typed-error rate, and routing outcomes (approve proposal, documentation request, nurse review), compared with baseline from the release evaluation. | Alert on a sustained deviation from the release baseline (proposed: more than 2x baseline failure rate); any deny outcome or write without an approval record pages immediately. |
| T12 | Log leakage sampling audit | online_monitor | minimizer, observability, decision_store | Periodic sample of logs and telemetry scanned for clinical text or direct identifiers; scan of decision store access logs for unauthorized reads. | 0 clinical text or identifier findings in sampled logs; any finding opens an incident. |

## Observability
- Step latency, error codes, retry counts and validation failure rates recorded by case id only, with no clinical text
- Alert when the two-minute target for validated approval proposals is at risk, and on approver queue age
- Routing mix tracked against the release baseline to detect model or policy drift
- Model endpoint and gateway availability alerts; outages trigger nurse routing or queuing, never automatic approval
- Periodic log sampling audits for clinical text leakage
- Alert on any deny outcome or any system-of-record write without an approval record

Versioning: Prompts, model endpoint and version, tool gateway operation schemas, validator rules, router rule set and evaluation suite are versioned in source control and released together as a tagged bundle. Policy versions are versioned in the policy store with effective dates, and each case pins one version. Every decision record stores the policy version, model version and prompt version. Any change to a prompt, model, tool, rule set or policy version reruns the evaluation suite, and the signed-off report is stored as release evidence. Rollback means redeploying the previous tagged bundle.

Governance:
- Every system-of-record write needs explicit approval from an authorized user; the gateway honors writes only with an approval token from the gate
- The system never denies; adverse or uncertain outcomes are decided only by a licensed nurse reviewer or clinician
- Policy versions are activated only after clinical policy owner review and publication
- Release requires a signed-off evaluation report; the business is asked to confirm that the two-minute target means time until the validated approval proposal is ready
- Role-based access via SSO for nurse reviewer, approver, auditor and policy owner; least-privilege service identity with separate narrower write scope
- Credentials and model keys held in the secrets manager and rotated; never in code or prompts
- Minimum-necessary data sent to the model, with an enterprise model endpoint with no training use and no prompt retention
- Decision records append-only, read-only for auditors, retained under the plan's retention policy

## Cost
Assumptions (illustrative, to be replaced with actual contract prices and volumes): 10,000 cases per month, about 8 criteria per case, one model call per criterion with about 5k input and 0.5k output tokens, and a mid-tier model at roughly $3 per million input and $15 per million output tokens. Model cost is about 40k input plus 4k output tokens per case, or about $0.18 per case. Gateway, storage, validation and observability add about $0.02 per case. Total is about $0.20 per request, or about $2,000 per month for the variable portion. Fixed platform costs (orchestration, databases, observability, evaluation runs) add roughly $1,500 per month. Estimated total is about $3,500 per month at 10,000 cases.

## Platform Mapping
Cloud: **aws**

| Component | Service |
|---|---|
| workflow | LangGraph or Strands on Bedrock AgentCore / ECS |
| identity | AWS IAM Identity Center + Amazon Cognito |
| secrets | AWS Secrets Manager |
| ehr_gateway | Amazon Bedrock AgentCore Gateway / API Gateway |
| policy_ingest | Amazon Textract |
| policy_store | Amazon DynamoDB |
| minimizer | Amazon Bedrock Guardrails |
| llm | Amazon Bedrock |
| validator | Custom service on Amazon ECS (Fargate) or AWS Lambda |
| router | Custom service on Amazon ECS (Fargate) or AWS Lambda |
| approval_gate | Custom service on Amazon ECS (Fargate) or AWS Lambda |
| decision_store | Amazon DynamoDB |
| observability | Amazon CloudWatch + AgentCore Observability |
| evaluation | Amazon Bedrock evaluations |

## Decisions (ADRs)
### ADR-1: Use a deterministic workflow with the LLM confined to criterion evaluation

- **Context:** The steps are known upfront: gather the request, eligibility, policy and notes; evaluate every criterion; then approve, request documentation or route to a nurse. The system must never deny a request, and decisions must be explainable years later. The signals show steps_known_upfront and audit_required are true, while open_ended_reasoning, many_tools and rules_suffice are false. Pattern ranking scores P2 (deterministic workflow) at 5 and P0 (no LLM) and P3 (router) at 0.
- **Options:** P0: conventional automation with no LLM, using rules or keyword matching on the clinical notes (simplest alternative); P2: fixed step graph where the LLM only fills in the criterion-evaluation step and never chooses the next step; Autonomous agent that plans its own steps and picks tools
- **Decision:** Adopt P2. A workflow engine runs the fixed step graph. The LLM returns a structured finding (met / not met / insufficient documentation) per criterion, and a rule-based router chooses the outcome. No deny outcome exists in the rule set. An autonomous agent is rejected because the steps are already known and it would add unpredictability. P0 is the simplest option but is not chosen because rules_suffice is false: evaluating each criterion against free-text clinical notes needs language understanding.
- **Consequences:** Routing is deterministic and testable, and the system cannot deny by construction. Behavior is easy to audit and to cover in the release evaluation. Any new step or outcome needs a design change rather than agent improvisation. The design still depends on an LLM to read free-text notes, so output must be validated (see ADR 2).
- **Requirements:** FR-1, FR-2, FR-3, FR-4, FR-5, FR-6, NFR-3, NFR-5

### ADR-2: Validate every LLM output deterministically, including citation checks

- **Context:** Each criterion finding must cite the policy clause and the sentence in the notes it relies on. A fabricated or overstated 'met' could lead to a wrong approval proposal. The LLM must not be able to deny or act.
- **Options:** Accept the structured LLM output as-is, relying on schema-constrained generation and prompt instructions (simplest alternative); Deterministic validation layer: schema check, exactly one finding per criterion in the pinned policy, cited clause ids exist, cited sentences exist verbatim in the notes, no denials or unsupported 'met'; one retry, then route to a nurse; Second LLM acting as a judge to review the first model's findings
- **Decision:** Use the deterministic validation layer. The workflow numbers note sentences at case time so citations can be checked mechanically. A failed output is retried once and then routed to a nurse. An LLM judge is not used, because it would add a second non-deterministic component where a mechanical check suffices.
- **Consequences:** Fabricated or mis-cited findings cannot reach the router. Clinicians see only citations that are verified to exist. Some cases will go to nurses because of validation failures, which is the safe direction. The validator must be maintained alongside schema and policy changes, and it needs its own tests in the release evaluation. The check proves a citation exists, not that it semantically supports the finding, so the approver still reviews the cited text.
- **Requirements:** FR-2, FR-3, FR-6, FR-7, NFR-3, NFR-4

### ADR-3: Require explicit human approval for every system-of-record write

- **Context:** The workflow writes to the claims/UM system: approvals, documentation requests to providers and routing records. Only clear approvals may be approved, and adverse or uncertain decisions belong to licensed clinicians. The two-minute target for clear approvals applies, and the design reads it as time until a validated proposal is ready for one-click confirmation. The business should confirm this interpretation.
- **Options:** Auto-execute writes for validated clear approvals and documentation requests, with sampled after-the-fact review (simplest alternative); Approval gate: the gateway executes a write only with an approval token from an authorized user who sees the findings with clause and sentence citations; nurse review for all non-clear cases
- **Decision:** Use the approval gate for all writes. The write scope of the service identity is separate and narrower, and the gateway honors it only with a valid approval token. The two-minute target is measured to the point where the validated proposal is ready, and queue age is alerted on.
- **Consequences:** A human confirms every outward action, and the approver identity and timestamp are recorded for audit. Approver backlog can delay clear approvals, so observability alerts on queue age. If the business requires the two-minute target to include human confirmation, the gate design and staffing must be revisited.
- **Requirements:** FR-3, FR-4, FR-5, FR-6, NFR-3, NFR-5

### ADR-4: Store coverage policies as versioned structured criteria pinned per case

- **Context:** Coverage policies change quarterly, each finding must cite a specific clause, and old decisions must be explainable years later. Decisions must be evaluated against the policy in force.
- **Options:** Embed policy text in prompts or code and redeploy at each change (simplest alternative); Versioned policy store with structured criteria and stable clause ids, reviewed and published by a clinical policy owner, with a policy version pinned per case and recorded in the decision record
- **Decision:** Use the versioned policy store, fed by a policy ingestion step with clinical owner review before activation. The release evaluation suite is rerun for each new policy version.
- **Consequences:** Quarterly changes need no code change, clause ids give stable citation targets, and past decisions stay reproducible. Ingestion and review add an operational step each quarter, and a mistake in conversion could affect all cases, so owner review and the evaluation rerun are mandatory gates.
- **Requirements:** FR-1, FR-7, NFR-3, NFR-4, NFR-6

## Traceability
Requirement coverage 100% · component test coverage 100% · PASSED

| Requirement | Components |
|---|---|
| FR-1 | workflow, ehr_gateway, policy_store |
| FR-2 | workflow, llm, validator |
| FR-3 | validator, router, approval_gate |
| FR-4 | workflow, ehr_gateway, router |
| FR-5 | workflow, ehr_gateway, router, approval_gate |
| FR-6 | validator, router, approval_gate |
| FR-7 | policy_ingest, policy_store, llm, validator, decision_store |
| NFR-1 | identity, secrets, ehr_gateway, minimizer |
| NFR-2 | minimizer, observability |
| NFR-3 | identity, policy_store, decision_store |
| NFR-4 | evaluation |
| NFR-5 | workflow, observability |
| NFR-6 | policy_ingest, policy_store, evaluation |

## Open Questions
_None._
