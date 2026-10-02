# Scenario: Prior Authorization Review (fictional; mock data only)

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
