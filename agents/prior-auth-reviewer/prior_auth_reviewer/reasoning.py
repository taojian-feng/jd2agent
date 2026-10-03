"""Criteria-grounded decision: proposer (model) -> critic (model) -> judge (code).

The proposer finds each criterion met / not_met / unknown / waived, citing the policy clause and note sentences.
Code checks every citation. The critic re-reads each finding against what it cites and the whole assembled note.
The judge is code: it can approve, ask for documentation, or route to a human. It has no way to deny.
"""
from prior_auth_reviewer.context import CaseContext
from prior_auth_reviewer.llm import LLM, call_validated
from prior_auth_reviewer.models import Critique, Decision, Proposal
from prior_auth_reviewer.retrieval import PolicyDoc

SYSTEM = """You prepare prior authorization cases for a health plan's nurse reviewers. You never deny: anything that is
not a clear approval goes to a person. Be exact: a finding is only as good as the sentence it cites. Clinical
judgment calls belong to the nurse, so when the notes do not clearly establish a criterion, say unknown."""


def _criteria(policy: PolicyDoc) -> str:
    lines = [f"- {c.id.split('#')[1]} (clause {c.id}): {c.title}. {c.text}" for c in policy.criteria()]
    rf = policy.chunk(f"{policy.policy_id}#RF")
    if rf:
        lines.append(f"- Red flags (clause {rf.id}): {rf.text}")
    return "\n".join(lines)


# ------------------------------------------------------------------ proposer
def validate_proposal(p: Proposal, policy: PolicyDoc, ctx: CaseContext) -> list[str]:
    problems = []
    want = [c.id.split("#")[1] for c in policy.criteria()]
    got = [f.criterion_id for f in p.findings]
    for cid in want:
        if got.count(cid) != 1:
            problems.append(f"give exactly one finding for {cid}")
    waivable = set(policy.waives())
    rf_id = f"{policy.policy_id}#RF"
    for f in p.findings:
        if f.criterion_id not in want:
            problems.append(f"{f.criterion_id} is not a criterion of {policy.policy_id}")
            continue
        expected_clause = rf_id if f.finding == "waived" else f"{policy.policy_id}#{f.criterion_id}"
        if f.clause_id != expected_clause:
            problems.append(f"{f.criterion_id}: cite clause {expected_clause} for a '{f.finding}' finding")
        if f.finding == "waived" and f.criterion_id not in waivable:
            problems.append(f"{f.criterion_id} cannot be waived; only {sorted(waivable)} can")
        if f.finding == "waived" and not p.red_flag.strip():
            problems.append(f"{f.criterion_id} is waived but red_flag is empty")
        if f.finding in ("met", "waived") and not f.sentence_ids:
            problems.append(f"{f.criterion_id}: a '{f.finding}' finding must cite at least one note sentence")
        bad = [s for s in f.sentence_ids if s not in ctx.ids()]
        if bad:
            problems.append(f"{f.criterion_id}: sentence ids {bad} are not in the notes provided")
    return problems


def propose(llm: LLM, policy: PolicyDoc, ctx: CaseContext, memory: str = "") -> Proposal:
    user = f"""Policy {policy.policy_id}: {policy.title}
{_criteria(policy)}

Clinical notes (identifiers masked; only sentences relevant to the criteria are shown, each with an id):
{ctx.text()}
{memory}
For each criterion return one finding:
- met: the cited sentences clearly establish it.
- not_met: the notes establish that it is not satisfied, or the policy requires documentation that is absent
  (an absence may cite no sentence).
- unknown: the notes are too vague to decide (for example a duration that is not stated).
- waived: a red flag in the notes waives this criterion under the red-flag clause (only the criteria it names).
Cite the clause id exactly as given and the sentence ids you rely on. Read numbers and body regions carefully."""
    return call_validated(llm, Proposal, SYSTEM, user, lambda p: validate_proposal(p, policy, ctx), "propose",
                          retries=2)


# ------------------------------------------------------------------ critic
def validate_critique(c: Critique, proposal: Proposal) -> list[str]:
    want = [f.criterion_id for f in proposal.findings]
    got = [v.criterion_id for v in c.verdicts]
    problems = [f"give exactly one verdict for {cid}" for cid in want if got.count(cid) != 1]
    problems += [f"{v.criterion_id}: explain the problem when you disagree" for v in c.verdicts
                 if not v.agree and not v.problem.strip()]
    return problems


def critique(llm: LLM, policy: PolicyDoc, ctx: CaseContext, proposal: Proposal) -> Critique:
    by_id = dict(ctx.kept)
    rows = []
    for f in proposal.findings:
        cited = "; ".join(f"{s}: {by_id.get(s, '?')}" for s in f.sentence_ids) or "(none: absence)"
        rows.append(f"- {f.criterion_id} -> {f.finding} (clause {f.clause_id}). Cited: {cited}. Rationale: {f.rationale}")
    user = f"""Check another reviewer's findings before they reach a nurse. For each criterion, agree only if the cited
sentences really establish the finding under the clause, nothing else in the notes contradicts it, and the
finding is not more favorable than the evidence allows. Disagree otherwise and say what is wrong.

Policy {policy.policy_id}:
{_criteria(policy)}

All note sentences shown to the reviewer:
{ctx.text()}

Findings (red flag claimed: {proposal.red_flag or 'none'}):
{chr(10).join(rows)}"""
    return call_validated(llm, Critique, SYSTEM, user, lambda c: validate_critique(c, proposal), "critique")


# ------------------------------------------------------------------ judge (code)
def judge(eligible: bool, proposal: Proposal | None, crit: Critique | None, policy: PolicyDoc | None) -> Decision:
    if not eligible:
        return Decision(outcome="human_review", reason="Member coverage is not active on the date of service")
    if proposal is None or policy is None:
        return Decision(outcome="human_review", reason="The case could not be prepared")
    disputed = [v.criterion_id for v in (crit.verdicts if crit else []) if not v.agree]
    if disputed:
        return Decision(outcome="human_review", reason=f"Critic disagreed on {', '.join(disputed)}")
    f = {x.criterion_id: x.finding for x in proposal.findings}
    not_met = [c for c, v in f.items() if v == "not_met"]
    if not_met:
        return Decision(outcome="human_review", reason=f"{', '.join(not_met)} not met")
    unknown = [c for c, v in f.items() if v == "unknown"]
    if unknown:
        titles = {c.id.split("#")[1]: c.title.split(". ", 1)[-1].lower() for c in policy.criteria()}
        return Decision(outcome="request_info", reason=f"{', '.join(unknown)} cannot be decided from the notes",
                        items=[f"documentation of {titles.get(c, c)}" for c in unknown])
    if all(v in ("met", "waived") for v in f.values()):
        return Decision(outcome="approve", reason="Every criterion is met or waived by a documented red flag")
    return Decision(outcome="human_review", reason="Findings incomplete")
