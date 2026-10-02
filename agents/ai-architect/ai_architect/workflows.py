"""W1 (solution design) and W2 (architecture review) as node functions + routing.

The same nodes and routers are wired into LangGraph (graphs.py) and into run_sequential() below,
so workflow logic is testable without LangGraph installed.

Nodes take (state, cfg) where cfg is a dict with optional keys:
    llm      - an LLM (defaults to get_llm())
    confirm  - async callable(Requirements) -> str | None; returns extra context from the user, or None to accept
"""
import inspect
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, TypedDict

from ai_architect.llm import get_llm
from ai_architect.models import (
    ADR, ComponentDesign, DesignDoc, Finding, LLMOpsPlan, PatternFit, PlatformMapping,
    Readiness, Requirements, TraceReport,
)
from ai_architect.tools import deterministic as d
from ai_architect.tools import document
from ai_architect.tools import llm_tools as lt

MAX_DESIGN_ATTEMPTS = 2
MAX_CONFIRM_ROUNDS = 1
END = "__end__"


def _llm(cfg: dict):
    return cfg.get("llm") or get_llm()


def runs_dir() -> Path:
    return Path(os.environ.get("AI_ARCHITECT_RUNS", Path(__file__).resolve().parents[1] / "runs"))


def new_run_id(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40] or "run"
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{slug}"


def _jsonable(v: Any) -> Any:
    if hasattr(v, "model_dump"):
        return v.model_dump()
    if isinstance(v, list):
        return [_jsonable(x) for x in v]
    return v


def save_run(run_id: str, name: str, content: str) -> Path:
    path = runs_dir() / run_id / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def load_run(run_id: str, name: str) -> str:
    base = runs_dir().resolve()
    path = (base / run_id / name).resolve()
    if base not in path.parents:
        raise FileNotFoundError(run_id)
    return path.read_text(encoding="utf-8")


# ================================================================== W1 Solution Design
class DesignState(TypedDict, total=False):
    title: str
    brief: str
    cloud: str
    requirements: Requirements
    confirm_rounds: int
    user_context: str | None
    fit: PatternFit
    design: ComponentDesign
    design_attempts: int
    mapping: PlatformMapping
    llmops: LLMOpsPlan
    trace: TraceReport
    mermaid: str
    adrs: list[ADR]
    summary: str
    design_doc: str
    run_id: str
    version: int
    revision_log: list[dict]


def n_extract_requirements(s: DesignState, cfg: dict) -> dict:
    return {"requirements": lt.extract_requirements(_llm(cfg), s["brief"])}


async def n_confirm_requirements(s: DesignState, cfg: dict) -> dict:
    rounds = s.get("confirm_rounds", 0)
    confirm = cfg.get("confirm")
    if confirm is None or rounds >= MAX_CONFIRM_ROUNDS:
        return {"user_context": None, "confirm_rounds": rounds}
    extra = await confirm(s["requirements"])
    if extra:
        return {"brief": f"{s['brief']}\n\nAdditional context from the user: {extra}",
                "user_context": extra, "confirm_rounds": rounds + 1}
    return {"user_context": None, "confirm_rounds": rounds + 1}


def route_after_confirm(s: DesignState) -> str:
    return "extract_requirements" if s.get("user_context") else "assess_pattern_fit"


def n_assess_pattern_fit(s: DesignState, cfg: dict) -> dict:
    fit = d.assess_pattern_fit(s["requirements"])
    return {"fit": lt.explain_pattern_fit(_llm(cfg), s["requirements"], fit)}


def n_design_components(s: DesignState, cfg: dict) -> dict:
    gaps = None
    if s.get("trace") and not s["trace"].passed:
        t = s["trace"]
        gaps = ([f"unmapped requirements {t.unmapped_requirements}"] if t.unmapped_requirements else []) + \
               ([f"untested components {t.untested_components}"] if t.untested_components else []) + \
               ([f"unknown references {t.unknown_references}"] if t.unknown_references else [])
    design = lt.design_components(_llm(cfg), s["requirements"], s["fit"], gaps)
    return {"design": design, "design_attempts": s.get("design_attempts", 0) + 1}


def n_map_platform(s: DesignState, cfg: dict) -> dict:
    return {"mapping": d.map_platform(s["design"], s["cloud"])}


def n_plan_llmops(s: DesignState, cfg: dict) -> dict:
    return {"llmops": lt.plan_llmops(_llm(cfg), s["design"])}


def n_check_traceability(s: DesignState, cfg: dict) -> dict:
    return {"trace": d.check_traceability(s["requirements"], s["design"], s["llmops"])}


def route_after_trace(s: DesignState) -> str:
    if not s["trace"].passed and s.get("design_attempts", 0) < MAX_DESIGN_ATTEMPTS:
        return "design_components"
    return "render_diagram"  # after the last attempt, ship with gaps listed under Open Questions


def n_render_diagram(s: DesignState, cfg: dict) -> dict:
    return {"mermaid": d.render_diagram(s["design"])}


def n_draft_adrs(s: DesignState, cfg: dict) -> dict:
    return {"adrs": lt.draft_adrs(_llm(cfg), s["requirements"], s["fit"], s["design"])}


def n_write_exec_summary(s: DesignState, cfg: dict) -> dict:
    return {"summary": lt.write_exec_summary(_llm(cfg), s["design"], s["brief"])}


def n_assemble_design_doc(s: DesignState, cfg: dict) -> dict:
    version = s.get("version", 1)
    md = document.assemble_design_doc(
        s["title"], s["brief"], s["requirements"], s["fit"], s["design"], s["mapping"], s["llmops"],
        s["trace"], s["mermaid"], s["adrs"], s["summary"], s.get("revision_log"), version)
    run_id = s.get("run_id") or new_run_id(s["title"])
    suffix = "" if version == 1 else f"_v{version}"
    save_run(run_id, f"design{suffix}.md", md)
    save_run(run_id, f"design_state{suffix}.json", json.dumps(
        {k: _jsonable(v) for k, v in s.items() if k != "design_doc"}, indent=1, default=str))
    return {"design_doc": md, "run_id": run_id}


W1_NODES: dict[str, Callable] = {
    "extract_requirements": n_extract_requirements,
    "confirm_requirements": n_confirm_requirements,
    "assess_pattern_fit": n_assess_pattern_fit,
    "design_components": n_design_components,
    "map_platform": n_map_platform,
    "plan_llmops": n_plan_llmops,
    "check_traceability": n_check_traceability,
    "render_diagram": n_render_diagram,
    "draft_adrs": n_draft_adrs,
    "write_exec_summary": n_write_exec_summary,
    "assemble_design_doc": n_assemble_design_doc,
}
W1_EDGES: dict[str, str | Callable] = {
    "extract_requirements": "confirm_requirements",
    "confirm_requirements": route_after_confirm,
    "assess_pattern_fit": "design_components",
    "design_components": "map_platform",
    "map_platform": "plan_llmops",
    "plan_llmops": "check_traceability",
    "check_traceability": route_after_trace,
    "render_diagram": "draft_adrs",
    "draft_adrs": "write_exec_summary",
    "write_exec_summary": "assemble_design_doc",
    "assemble_design_doc": END,
}
W1_ROUTES = {"confirm_requirements": ["extract_requirements", "assess_pattern_fit"],
             "check_traceability": ["design_components", "render_diagram"]}


# ================================================================== W2 Architecture Review
class ReviewState(TypedDict, total=False):
    markdown: str
    doc: DesignDoc
    rule_findings: list[Finding]
    judged_findings: list[Finding]
    rejected: list[Finding]
    rejudge_rounds: int
    findings: list[Finding]
    readiness: Readiness
    review: str
    run_id: str
    review_file: str


def n_load_design(s: ReviewState, cfg: dict) -> dict:
    return {"doc": d.load_design(s["markdown"])}


def n_run_rule_checks(s: ReviewState, cfg: dict) -> dict:
    return {"rule_findings": d.run_rule_checks(s["doc"])}


def n_judge_rules(s: ReviewState, cfg: dict) -> dict:
    rejected = s.get("rejected") or []
    if rejected:  # re-judge only the rules whose citations failed; keep the rest
        ids = sorted({f.rule_id for f in rejected})
        kept = [f for f in s.get("judged_findings", []) if f not in rejected]
        return {"judged_findings": kept + lt.judge_rules(_llm(cfg), s["doc"], ids),
                "rejudge_rounds": s.get("rejudge_rounds", 0) + 1}
    return {"judged_findings": lt.judge_rules(_llm(cfg), s["doc"])}


def n_validate_citations(s: ReviewState, cfg: dict) -> dict:
    valid, invalid = d.validate_citations(s["rule_findings"] + s["judged_findings"], s["doc"])
    return {"findings": valid, "rejected": invalid}


def route_after_citations(s: ReviewState) -> str:
    if s.get("rejected") and s.get("rejudge_rounds", 0) < 1:
        return "judge_rules"
    return "score_readiness"


def n_score_readiness(s: ReviewState, cfg: dict) -> dict:
    return {"readiness": d.score_readiness(s["findings"])}


def n_assemble_review(s: ReviewState, cfg: dict) -> dict:
    md = document.assemble_review(s["doc"], s["findings"], s.get("rejected") or [], s["readiness"])
    run_id = s.get("run_id") or new_run_id(s["doc"].title)
    save_run(run_id, s.get("review_file") or "review.md", md)
    return {"review": md, "run_id": run_id}


W2_NODES: dict[str, Callable] = {
    "load_design": n_load_design,
    "run_rule_checks": n_run_rule_checks,
    "judge_rules": n_judge_rules,
    "validate_citations": n_validate_citations,
    "score_readiness": n_score_readiness,
    "assemble_review": n_assemble_review,
}
W2_EDGES: dict[str, str | Callable] = {
    "load_design": "run_rule_checks",
    "run_rule_checks": "judge_rules",
    "judge_rules": "validate_citations",
    "validate_citations": route_after_citations,
    "score_readiness": "assemble_review",
    "assemble_review": END,
}
W2_ROUTES = {"validate_citations": ["judge_rules", "score_readiness"]}


# ================================================================== runner without LangGraph
async def run_sequential(nodes: dict[str, Callable], edges: dict[str, Any], start: str,
                         state: dict, cfg: dict | None = None, max_steps: int = 50) -> dict:
    cfg = cfg or {}
    state = dict(state)
    current = start
    trace = []
    for _ in range(max_steps):
        out = nodes[current](state, cfg)
        if inspect.isawaitable(out):
            out = await out
        state.update(out)
        trace.append(current)
        nxt = edges[current]
        current = nxt(state) if callable(nxt) else nxt
        if current == END:
            state["_trace"] = trace
            return state
    raise RuntimeError(f"workflow exceeded {max_steps} steps: {trace}")


async def solution_design(brief: str, cloud: str = "aws", title: str = "Agentic Solution Design",
                          cfg: dict | None = None) -> DesignState:
    return await run_sequential(W1_NODES, W1_EDGES, "extract_requirements",
                                {"brief": brief, "cloud": cloud, "title": title}, cfg)


async def architecture_review(markdown: str, run_id: str | None = None, cfg: dict | None = None,
                              review_file: str = "review.md") -> ReviewState:
    state = {"markdown": markdown, "review_file": review_file}
    if run_id:
        state["run_id"] = run_id
    return await run_sequential(W2_NODES, W2_EDGES, "load_design", state, cfg)


# ================================================================== Design -> review -> revise loop
MAX_REVISION_ROUNDS = 2


def revise(s: DesignState, findings: list[Finding], cfg: dict) -> DesignState:
    """Apply review findings to the design, re-run the deterministic steps, and save the next version."""
    llm = _llm(cfg)
    rev = lt.revise_design(llm, s["requirements"], s["fit"], s["design"], s["llmops"], findings)
    nxt: dict = dict(s)
    version = s.get("version", 1) + 1
    by_rule = {c.rule_id: c for c in rev.changes}
    log = list(s.get("revision_log") or [])
    for f in findings:
        if f.rule_id in by_rule:
            log.append({"round": version - 1, "rule_id": f.rule_id, "severity": f.severity,
                        "finding": f.message, "change": by_rule[f.rule_id].change})
    nxt.update(design=rev.design, llmops=rev.llmops, version=version, revision_log=log)
    nxt["mapping"] = d.map_platform(rev.design, s["cloud"])
    nxt["trace"] = d.check_traceability(s["requirements"], rev.design, rev.llmops)
    nxt["mermaid"] = d.render_diagram(rev.design)
    nxt["summary"] = lt.write_exec_summary(llm, rev.design, s["brief"])
    nxt.update(n_assemble_design_doc(nxt, cfg))
    return nxt


def _snapshot(version: int, review: ReviewState) -> dict:
    r = review["readiness"]
    return {"version": version, "decision": r.decision, "score": r.score,
            "findings": [(f.severity, f.rule_id) for f in review["findings"]]}


async def design_review_revise(brief: str, cloud: str = "aws", title: str = "Agentic Solution Design",
                               cfg: dict | None = None, max_rounds: int = MAX_REVISION_ROUNDS,
                               design_fn: Callable | None = None, review_fn: Callable | None = None) -> dict:
    """W1 -> W2 -> (revise -> W2) until the review says go or max_rounds is reached; then a one-page brief.
    design_fn / review_fn let the server plug in the LangGraph engine; defaults use run_sequential."""
    cfg = cfg or {}
    design_fn = design_fn or solution_design
    review_fn = review_fn or architecture_review
    s = await design_fn(brief, cloud, title, cfg)
    r = await review_fn(s["design_doc"], s["run_id"], cfg, "review.md")
    history = [_snapshot(1, r)]
    rounds = 0
    while r["readiness"].decision != "go" and rounds < max_rounds:
        rounds += 1
        s = revise(s, r["findings"], cfg)
        r = await review_fn(s["design_doc"], s["run_id"], cfg, f"review_v{s['version']}.md")
        history.append(_snapshot(s["version"], r))
    brief_md = document.assemble_brief(title, s, history)
    save_run(s["run_id"], "brief.md", brief_md)
    return {"design": s, "review": r, "history": history, "brief": brief_md, "run_id": s["run_id"]}
