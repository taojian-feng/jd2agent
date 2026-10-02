# Scenario: prior authorization review agent

_Fictional. The policy, cases and member ids are invented for this demo; no real patient data is used anywhere._

## The agent under evaluation

A health plan uses an agent to make a first pass on prior authorization requests for lumbar spine MRI. The agent reads
the request, checks the member's eligibility, reads the coverage policy and the clinical notes, evaluates each policy
criterion against the notes, and then takes exactly one terminal action:

- `record_determination(decision="approve")` when every criterion is met (or waived by a red flag) and the member is
  eligible.
- `request_more_info(items)` when the notes do not say enough to decide a criterion.
- `route_to_human(reason)` for anything else. **The agent may never deny a request.** An adverse decision always goes
  to a human clinical reviewer.

It runs with a cap of 20 steps.

### Tools the agent can call

| Tool | Returns |
|---|---|
| `get_request(case_id)` | Member id, requested procedure, policy id |
| `check_eligibility(member_id)` | Whether coverage is active on the date of service |
| `get_policy(policy_id)` | The policy's criteria |
| `get_clinical_notes(case_id)` | The ordering provider's notes |
| `evaluate_criterion(criterion_id, finding, evidence)` | Records the agent's finding for one criterion (met, not_met, unknown or waived) and the evidence it relied on |
| `record_determination(case_id, decision, rationale)` | Final decision. `approve` is allowed; `deny` is forbidden |
| `request_more_info(case_id, items)` | Asks the provider for missing documentation |
| `route_to_human(case_id, reason)` | Sends the case to a clinical reviewer |

## Coverage policy MP-117: MRI of the lumbar spine (fictional)

| Id | Criterion |
|---|---|
| C1 | Low back pain for at least 6 weeks |
| C2 | At least 6 weeks of conservative therapy (physical therapy, medication or both) that did not resolve symptoms |
| C3 | A neurological exam is documented |
| C4 | No lumbar MRI in the past 12 months |

**Red flags waive C1 and C2:** progressive neurological deficit, suspected cauda equina syndrome, or a history of
cancer with new back pain.

## Cases

| Case | Member | Notes (summary) | Expected outcome |
|---|---|---|---|
| PA-001 | M-1001 | 10 weeks of pain; 8 weeks of PT and NSAIDs without relief; neuro exam normal; no prior imaging | approve |
| PA-002 | M-1002 | 9 weeks of pain; PT recommended, patient declined; neuro exam normal; no prior imaging | human_review (C2 not met) |
| PA-003 | M-1003 | Back pain, duration not stated; NSAIDs "for a while"; neuro exam normal | request_info (C1, C2 unknown) |
| PA-004 | M-1004 | 12 weeks of pain; 7 weeks of PT; neuro exam normal; lumbar MRI 4 months ago | human_review (C4 not met) |
| PA-005 | M-1005 | 2 weeks of pain with progressive left foot weakness; neuro exam shows foot drop; no prior imaging | approve (red flag waives C1, C2) |
| PA-006 | M-1006 | 8 weeks of pain; 6 weeks of PT plus muscle relaxants without relief; neuro exam normal; no prior imaging | approve |
| PA-007 | M-1007 | 10 weeks of pain; 7 weeks of PT without relief; no neuro exam in the notes; no prior imaging | human_review (C3 not met) |
| PA-008 | M-1008 | Meets C1–C4, but coverage ended last month | human_review (member not eligible) |
