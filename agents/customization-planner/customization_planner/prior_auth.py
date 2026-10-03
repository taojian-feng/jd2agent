"""Adapter for prior-auth-reviewer traces: read the model's decisions out of a trace and rebuild its prompt.

The proposer's findings are recorded as trace messages ("Proposed findings: C1 met (N5): ...; C2 ..."), the critic's
verdicts as "Critic: C1 agree; C4 DISAGREE: ...", and a self-correction round as "Revised findings: ...". The prompt is
rebuilt with the reviewer's own code (policy parser, context assembly, proposer prompt), so training data matches the
prompt the agent ships today, and the rebuilt context is checked against what the trace says was kept.
"""
import json
import re

from agent_evaluator.models import SuccessCheck, Trajectory
from prior_auth_reviewer import context as cx
from prior_auth_reviewer.models import CriterionFinding, Proposal
from prior_auth_reviewer.reasoning import SYSTEM, proposer_prompt, validate_proposal
from prior_auth_reviewer.retrieval import PolicyDoc, parse_policy

from customization_planner.models import DecisionRecord, Finding

FINDING = re.compile(r"(?:^|; )(C\d+) (met|not_met|unknown|waived) \(([^)]*)\): ")
KEPT = re.compile(r"kept ([N\d, ]+);")
GENERIC_IDENTIFIERS = [
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),                      # a date not masked
    re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"),                # email
    re.compile(r"\b\d{3}[-. ]\d{3}[-. ]\d{4}\b"),              # phone
]


def parse_findings(content: str) -> tuple[list[Finding], str]:
    """'Proposed findings: C1 met (N5): why; C2 ...  Red flag: ...' -> findings, red flag."""
    body = content.split(": ", 1)[1] if ": " in content else content
    red_flag = ""
    if " Red flag: " in body:
        body, red_flag = body.split(" Red flag: ", 1)
    marks = list(FINDING.finditer(body))
    out = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        ids = [] if m.group(3) == "absence" else [x.strip() for x in m.group(3).split(",") if x.strip()]
        out.append(Finding(criterion_id=m.group(1), finding=m.group(2), sentence_ids=ids,
                           rationale=body[m.end():end].strip()))
    return out, red_flag.strip()


def disputed(content: str) -> list[str]:
    return re.findall(r"(C\d+) DISAGREE", content)


def _result(traj: Trajectory, tool: str):
    return next((s.result for s in traj.steps if s.tool == tool and not s.error and s.result), None)


def policy_and_context(traj: Trajectory) -> tuple[PolicyDoc, cx.CaseContext] | None:
    pol, notes = _result(traj, "get_policy"), _result(traj, "get_clinical_notes")
    if not pol or not notes:
        return None
    policy = parse_policy(pol["markdown"])
    return policy, cx.assemble(notes["notes"], policy)


def to_proposal(findings: list[Finding], red_flag: str, policy: PolicyDoc) -> Proposal:
    pid = policy.policy_id
    return Proposal(red_flag=red_flag, findings=[
        CriterionFinding(criterion_id=f.criterion_id, finding=f.finding,
                         clause_id=f"{pid}#RF" if f.finding == "waived" else f"{pid}#{f.criterion_id}",
                         sentence_ids=f.sentence_ids, rationale=f.rationale) for f in findings])


def completion(findings: list[Finding], red_flag: str, traj: Trajectory) -> tuple[str, list[str]]:
    """The proposal as the model should have returned it (JSON), and the reviewer's own validator's problems."""
    pc = policy_and_context(traj)
    if pc is None:
        return "", ["policy or notes missing from the trace"]
    policy, ctx = pc
    p = to_proposal(findings, red_flag, policy)
    return json.dumps(p.model_dump(), ensure_ascii=False), validate_proposal(p, policy, ctx)


def unmasked_identifiers(text: str) -> list[str]:
    """Identifiers that masking should have removed: the reviewer's own masks plus generic patterns."""
    hits = [m.group(0) for pat, _ in cx.MASKS for m in pat.finditer(text)]
    return hits + [m.group(0) for pat in GENERIC_IDENTIFIERS for m in pat.finditer(text)]


def decision_record(traj: Trajectory, check: SuccessCheck) -> DecisionRecord:
    msgs = [s.content or "" for s in traj.steps if s.kind == "message"]
    proposals = [parse_findings(m) for m in msgs if m.startswith(("Proposed findings:", "Revised findings:"))]
    critic = next((m for m in msgs if m.startswith("Critic:")), "")
    rec = DecisionRecord(
        run_id=traj.run_id, task_id=traj.task_id, passed=check.passed, expected_outcome=check.expected_outcome,
        outcome=check.outcome, safety_failure=check.safety_failure, symptoms=[s.label for s in check.symptoms],
        model_calls=sum(m.startswith(("Proposed findings:", "Revised findings:", "Critic:")) for m in msgs))
    if not proposals:
        return rec
    rec.first_pass, rec.first_red_flag = proposals[0]
    rec.final, rec.red_flag = proposals[-1]
    rec.disputed = disputed(critic)
    pc = policy_and_context(traj)
    if pc:
        policy, ctx = pc
        rec.prompt = proposer_prompt(policy, ctx)
        kept_msg = next((m for m in msgs if m.startswith("Context assembled:")), "")
        k = KEPT.search(kept_msg)
        traced = [x.strip() for x in k.group(1).split(",")] if k else []
        rec.context_matches_trace = traced == [sid for sid, _ in ctx.kept]
    return rec

