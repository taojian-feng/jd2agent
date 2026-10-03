"""The reviewer workflow for one case, as node functions + routing (wired into LangGraph in graphs.py, or run by
run_sequential here), plus suite runs and the case store (memory).

cfg keys: client (SystemsClient), rec (Recorder), library (PolicyLibrary), llm, critic (bool),
          approver (async (case_id, decision) -> approver id or None), memory (str, prior findings on resume)
"""
import asyncio
import inspect
import json
import os
import time
from pathlib import Path
from typing import Any, Callable, TypedDict

from prior_auth_reviewer import context as cx
from prior_auth_reviewer import reasoning as rs
from prior_auth_reviewer.client import SystemsClient, ToolFailed, connect
from prior_auth_reviewer.llm import ValidationFailed, get_llm
from prior_auth_reviewer.models import CaseResult, Critique, Decision, Proposal
from prior_auth_reviewer.retrieval import PolicyDoc, PolicyLibrary, parse_policy
from prior_auth_reviewer.systems import HealthPlanSystems, build_server, load_cases, load_policy_texts
from prior_auth_reviewer.trace import Recorder

END = "__end__"
AGENT_VERSION = "prior-auth-reviewer 0.1"


class CaseState(TypedDict, total=False):
    case_id: str
    request: dict
    eligible: bool
    policy: PolicyDoc
    notes: str
    ctx: cx.CaseContext
    proposal: Proposal
    critique: Critique
    decision: Decision
    approved_by: str
    llm_calls: int
    revisions: int


def _redact_notes(result: dict) -> dict:
    return {**result, "notes": cx.mask(result.get("notes", ""))[0]}


# ------------------------------------------------------------------ nodes
async def intake(s: CaseState, cfg: dict) -> dict:
    c: SystemsClient = cfg["client"]
    req = await c.call("get_request", {"case_id": s["case_id"]}, "Read the request.")
    try:
        el = await c.call("check_eligibility", {"member_id": req["member_id"], "case_id": s["case_id"]},
                          "Confirm coverage is active on the date of service.")
    except ToolFailed as e:
        return {"request": req, "decision": Decision(outcome="human_review",
                                                     reason=f"Eligibility could not be confirmed: {e.error}")}
    out = {"request": req, "eligible": bool(el["active"])}
    if not el["active"]:
        out["decision"] = rs.judge(False, None, None, None)
    return out


async def route_policy(s: CaseState, cfg: dict) -> dict:
    lib: PolicyLibrary = cfg["library"]
    q = f"{s['request']['procedure']} {s['request']['procedure_code']}"
    hits = lib.search_policies(q, k=3)
    cfg["rec"].tool("search_policies", {"query": q}, [{"policy_id": p, "score": round(sc, 4)} for p, sc in hits],
                    None, "Find the coverage policy for the requested procedure (hybrid retrieval + rerank).")
    if not hits:
        return {"decision": Decision(outcome="human_review", reason="No coverage policy found for the procedure")}
    doc = await cfg["client"].call("get_policy", {"policy_id": hits[0][0]}, "Read the coverage policy.")
    return {"policy": parse_policy(doc["markdown"])}


async def gather_notes(s: CaseState, cfg: dict) -> dict:
    try:
        r = await cfg["client"].call("get_clinical_notes", {"case_id": s["case_id"]},
                                     "Get the clinical notes for the case.", redact=_redact_notes)
    except ToolFailed as e:
        return {"decision": Decision(outcome="human_review",
                                     reason=f"Clinical notes unavailable after {e.attempts} attempts: {e.error}")}
    return {"notes": r["notes"]}


def assemble_context(s: CaseState, cfg: dict) -> dict:
    ctx = cx.assemble(s["notes"], s["policy"])
    cfg["rec"].message(
        f"Context assembled: kept {', '.join(sid for sid, _ in ctx.kept)}; dropped {', '.join(ctx.dropped) or 'none'}; "
        f"masked {ctx.masked_identifiers} identifiers.",
        "Keep only the note sentences the criteria need (minimum necessary).")
    return {"ctx": ctx}


def _count(s: CaseState, n: int = 1) -> int:
    return s.get("llm_calls", 0) + n


MAX_REVISIONS = 1


def _feedback(s: CaseState) -> str:
    """The critic's objections, handed back to the proposer for one self-correction round."""
    if not s.get("critique"):
        return ""
    objections = "\n".join(f"- {v.criterion_id}: {v.problem}" for v in s["critique"].verdicts if not v.agree)
    return ("\nA second reviewer checked your previous findings and disagreed:\n" + objections +
            "\nRe-evaluate every criterion against the notes. Change a finding only where the objection holds; "
            "keep it where the notes support you.\n")


async def propose(s: CaseState, cfg: dict) -> dict:
    try:
        p = await asyncio.to_thread(rs.propose, cfg.get("llm") or get_llm(), s["policy"], s["ctx"],
                                    cfg.get("memory", "") + _feedback(s))
    except ValidationFailed as e:
        cfg["rec"].message(f"Findings rejected by the citation check: {e.problems}", "Propose findings.")
        return {"llm_calls": _count(s), "decision": Decision(outcome="human_review",
                                                            reason="Findings failed the citation check")}
    revising = bool(s.get("critique"))
    cfg["rec"].message(("Revised findings: " if revising else "Proposed findings: ") + "; ".join(
        f"{f.criterion_id} {f.finding} ({', '.join(f.sentence_ids) or 'absence'}): {f.rationale}" for f in p.findings)
        + (f" Red flag: {p.red_flag}" if p.red_flag else ""),
        "Re-evaluate after the critic's objections." if revising else "Evaluate each criterion against the notes.")
    out = {"proposal": p, "llm_calls": _count(s)}
    if revising:
        out.update(revisions=s.get("revisions", 0) + 1, critique=None)
    return out


async def critique(s: CaseState, cfg: dict) -> dict:
    try:
        c = await asyncio.to_thread(rs.critique, cfg.get("llm") or get_llm(), s["policy"], s["ctx"], s["proposal"])
    except ValidationFailed as e:
        return {"llm_calls": _count(s), "decision": Decision(outcome="human_review",
                                                            reason=f"Critic output invalid: {e.problems}")}
    cfg["rec"].message("Critic: " + "; ".join(
        f"{v.criterion_id} {'agree' if v.agree else 'DISAGREE: ' + v.problem}" for v in c.verdicts),
        "Check each finding against what it cites.")
    return {"critique": c, "llm_calls": _count(s)}


async def record_findings(s: CaseState, cfg: dict) -> dict:
    sent = dict(s["ctx"].kept)
    for f in s["proposal"].findings:
        evidence = " ".join(sent[x] for x in f.sentence_ids if x in sent) or "No supporting sentence in the notes."
        await cfg["client"].call("evaluate_criterion", {"case_id": s["case_id"], "criterion_id": f.criterion_id,
                                                        "finding": f.finding, "evidence": evidence},
                                 f"Record the finding for {f.criterion_id}.")
    return {}


def judge(s: CaseState, cfg: dict) -> dict:
    return {"decision": rs.judge(s.get("eligible", False), s.get("proposal"), s.get("critique"), s.get("policy"))}


async def approval(s: CaseState, cfg: dict) -> dict:
    """Human-in-the-loop checkpoint: an approval is written only after a person confirms it."""
    approver = cfg.get("approver")
    who = await approver(s["case_id"], s["decision"]) if approver else "batch-approver (demo)"
    cfg["rec"].message(f"Approval checkpoint: {'confirmed by ' + who if who else 'declined'}.",
                       "A person confirms every approval before it is written.")
    if not who:
        return {"decision": Decision(outcome="human_review", reason="Approval declined at the checkpoint")}
    return {"approved_by": who}


async def act(s: CaseState, cfg: dict) -> dict:
    d, c, cid = s["decision"], cfg["client"], s["case_id"]
    try:
        if d.outcome == "approve":
            await c.call("record_determination", {"case_id": cid, "decision": "approve", "rationale": d.reason,
                                                  "approved_by": s["approved_by"]}, "Record the approval.")
        elif d.outcome == "request_info":
            await c.call("request_more_info", {"case_id": cid, "items": d.items},
                         "Ask the provider for the missing documentation.")
        else:
            await c.call("route_to_human", {"case_id": cid, "reason": d.reason},
                         "Send the case to a clinical reviewer.")
    except ToolFailed as e:  # last resort: a person must see it
        cfg["rec"].message(f"Terminal action failed ({e.error}); the case stays open for a person.")
    return {}


def _after_critique(s: CaseState) -> str:
    """Self-correction: one revision round when the critic disagrees; a disagreement that survives goes to a nurse."""
    if s.get("decision") is not None:
        return "act"
    disputed = any(not v.agree for v in s["critique"].verdicts)
    return "propose" if disputed and s.get("revisions", 0) < MAX_REVISIONS else "record_findings"


def _next(default: str):
    def route(s: CaseState) -> str:
        return "act" if s.get("decision") is not None else default
    route.__name__ = f"to_{default}"
    return route


def _after_judge(s: CaseState) -> str:
    return "approval" if s["decision"].outcome == "approve" else "act"


NODES: dict[str, Callable] = {"intake": intake, "route_policy": route_policy, "gather_notes": gather_notes,
                              "assemble_context": assemble_context, "propose": propose, "critique": critique,
                              "record_findings": record_findings, "judge": judge, "approval": approval, "act": act}


def edges(with_critic: bool) -> dict[str, Any]:
    return {"intake": _next("route_policy"), "route_policy": _next("gather_notes"),
            "gather_notes": _next("assemble_context"), "assemble_context": "propose",
            "propose": _next("critique" if with_critic else "record_findings"),
            "critique": _after_critique, "record_findings": "judge", "judge": _after_judge,
            "approval": "act", "act": END}


ROUTES = {"intake": ["route_policy", "act"], "route_policy": ["gather_notes", "act"],
          "gather_notes": ["assemble_context", "act"], "propose": ["critique", "record_findings", "act"],
          "critique": ["propose", "record_findings", "act"], "judge": ["approval", "act"]}


async def run_sequential(nodes, edge_map, start: str, state: dict, cfg: dict, max_steps: int = 30) -> dict:
    state, current = dict(state), start
    for _ in range(max_steps):
        out = nodes[current](state, cfg)
        if inspect.isawaitable(out):
            out = await out
        state.update(out)
        nxt = edge_map[current]
        current = nxt(state) if callable(nxt) else nxt
        if current == END:
            return state
    raise RuntimeError("workflow exceeded its step limit")


async def review_case(case_id: str, cfg: dict, engine: str = "auto") -> dict:
    """Run one case. Returns the final state (decision, findings, ...)."""
    critic = cfg.get("critic", True)
    graphs = None
    if engine != "sequential":
        try:
            from prior_auth_reviewer import graphs
        except ImportError:
            graphs = None
    if graphs:
        return await graphs.case_graph(critic).ainvoke({"case_id": case_id}, {"configurable": cfg,
                                                                              "recursion_limit": 30})
    return await run_sequential(NODES, edges(critic), "intake", {"case_id": case_id}, cfg)


def to_result(s: dict) -> CaseResult:
    ctx = s.get("ctx")
    return CaseResult(case_id=s["case_id"], outcome=s["decision"].outcome, reason=s["decision"].reason,
                      findings=s["proposal"].findings if s.get("proposal") else [],
                      critique=s["critique"].verdicts if s.get("critique") else [],
                      context_kept=len(ctx.kept) if ctx else 0, context_dropped=len(ctx.dropped) if ctx else 0,
                      llm_calls=s.get("llm_calls", 0))


# ------------------------------------------------------------------ memory: case store
def runs_dir() -> Path:
    return Path(os.environ.get("PRIOR_AUTH_RUNS", Path(__file__).resolve().parents[1] / "runs"))


class CaseStore:
    """Persistent case memory: findings, outcome and history per case. No clinical text is stored."""

    def __init__(self, root: Path | None = None):
        self.root = (root or runs_dir() / "cases")

    def load(self, case_id: str) -> dict | None:
        p = self.root / f"{case_id}.json"
        return json.loads(p.read_text()) if p.exists() else None

    def save(self, result: CaseResult, run_name: str) -> dict:
        prev = self.load(result.case_id) or {"case_id": result.case_id, "history": []}
        rec = {"case_id": result.case_id, "outcome": result.outcome, "reason": result.reason,
               "findings": [f.model_dump() for f in result.findings],
               "history": prev["history"] + [{"run": run_name, "outcome": result.outcome,
                                              "at": time.strftime("%Y-%m-%dT%H:%M:%S")}]}
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / f"{result.case_id}.json").write_text(json.dumps(rec, indent=1))
        return rec

    def memory_prompt(self, case_id: str) -> str:
        rec = self.load(case_id)
        if not rec or not rec.get("findings"):
            return ""
        lines = "; ".join(f"{f['criterion_id']} {f['finding']}" for f in rec["findings"])
        return (f"\nEarlier review of this case (outcome {rec['outcome']}: {rec['reason']}). Earlier findings: {lines}. "
                "Sentence ids may have changed; re-check every criterion against the current notes, which may "
                "include new documentation from the provider.\n")


# ------------------------------------------------------------------ suite runs
class CountingLLM:
    def __init__(self, inner):
        self.inner, self.calls = inner, 0

    def structured(self, schema, system, user):
        self.calls += 1
        return self.inner.structured(schema, system, user)


def library_from(systems: HealthPlanSystems) -> PolicyLibrary:
    """Ingestion: pull every policy from the policy store and index its chunks."""
    return PolicyLibrary([parse_policy(t) for t in systems.policies.values()])


async def run_suite(run_name: str, case_ids: list[str] | None = None, critic: bool = True,
                    faults: dict | None = None, llm=None, concurrency: int = 4, sleep=asyncio.sleep,
                    approver=None, store: CaseStore | None = None, systems: HealthPlanSystems | None = None,
                    memory: bool = False) -> dict:
    systems = systems or HealthPlanSystems(faults)
    lib = library_from(systems)
    cases = load_cases()
    ids = case_ids or list(cases)
    llm = CountingLLM(llm or get_llm())
    store = store or CaseStore()
    sem = asyncio.Semaphore(concurrency)
    traces, results = {}, {}
    async with connect(build_server(systems)) as session:
        async def one(cid: str):
            async with sem:
                rec = Recorder(run_name, cid, AGENT_VERSION + ("" if critic else " (no critic)"))
                cfg = {"client": SystemsClient(session, rec, sleep=sleep), "rec": rec, "library": lib, "llm": llm,
                       "critic": critic, "approver": approver,
                       "memory": store.memory_prompt(cid) if memory else ""}
                try:
                    res = to_result(await review_case(cid, cfg))
                except Exception as e:  # noqa: BLE001  report, don't lose the other cases
                    res = CaseResult(case_id=cid, outcome="error", reason="", error=f"{type(e).__name__}: {e}")
                store.save(res, run_name)
                traces[cid], results[cid] = rec, res
        await asyncio.gather(*(one(c) for c in ids))
    rows = [{"case_id": c, "outcome": results[c].outcome, "expected": cases[c]["expected_outcome"],
             "correct": results[c].outcome == cases[c]["expected_outcome"], "reason": results[c].reason,
             "error": results[c].error} for c in ids]
    return {"run_name": run_name, "critic": critic, "rows": rows, "results": results, "traces": traces,
            "accuracy": round(sum(r["correct"] for r in rows) / len(rows), 3), "llm_calls": llm.calls,
            "unsafe_approvals": [r["case_id"] for r in rows if r["outcome"] == "approve" and r["expected"] != "approve"],
            "records": systems.records}


def write_traces(out: dict, directory: Path) -> int:
    directory.mkdir(parents=True, exist_ok=True)
    for old in directory.glob("*.json"):
        old.unlink()
    for cid, rec in out["traces"].items():
        (directory / f"{cid}.json").write_text(rec.dumps(), encoding="utf-8")
    return len(out["traces"])
