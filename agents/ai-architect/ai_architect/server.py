"""ai-architect-agent MCP server: Resources (knowledge), Tools (actions), Prompts (workflows).

Run:  uv run ai-architect                 (stdio, for Claude Desktop / IDEs)
      uv run ai-architect --http          (streamable HTTP on :8000)
"""
import sys
import uuid
from typing import Literal

try:  # MCP Python SDK 2.x: FastMCP was renamed MCPServer
    from mcp.server.mcpserver import Context, MCPServer as FastMCP
except ImportError:  # MCP Python SDK 1.x
    from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from ai_architect import catalog, workflows as wf
from ai_architect.llm import get_llm
from ai_architect.models import (
    ADR, ComponentDesign, DesignDoc, Finding, LLMOpsPlan, PatternFit, PlatformMapping,
    Readiness, Requirements, TraceReport,
)
from ai_architect.tools import deterministic as d
from ai_architect.tools import llm_tools as lt

mcp = FastMCP(
    "ai-architect-agent",
    instructions=(
        "Designs agentic AI solutions from business briefs (W1) and reviews AI architecture designs (W2). "
        "Every LLM output is checked deterministically (traceability, verbatim citations) before it is returned. "
        "Start with the 'design-agentic-solution' or 'review-ai-architecture' prompt, or call "
        "run_solution_design / run_architecture_review for the full workflow."
    ),
)

READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)
LLM_CALL = ToolAnnotations(readOnlyHint=True, idempotentHint=False, openWorldHint=True)

# ------------------------------------------------------------------ resources
@mcp.resource("architect://catalog/patterns", mime_type="text/yaml",
              description="Agent patterns, selection signals and weights, modifiers")
def patterns_resource() -> str:
    return catalog.text("patterns.yaml")


@mcp.resource("architect://catalog/platforms", mime_type="text/yaml",
              description="Component type -> Azure / AWS / GCP service mapping")
def platforms_resource() -> str:
    return catalog.text("platforms.yaml")


@mcp.resource("architect://rules/review", mime_type="text/yaml",
              description="Architecture review rulebook: ids, severity, deterministic vs judged")
def rules_resource() -> str:
    return catalog.text("review_rules.yaml")


@mcp.resource("architect://rules/{pack}", mime_type="text/yaml",
              description="Rule packs that add to the general rulebook, e.g. architect://rules/healthcare")
def rule_pack_resource(pack: str) -> str:
    if pack == "review":
        return catalog.text("review_rules.yaml")
    catalog.pack(pack)  # validates the name
    return catalog.text(f"review_rules_{pack}.yaml")


@mcp.tool(annotations=READ_ONLY)
def list_rule_packs() -> dict[str, str]:
    """Available rule packs (name -> title). Pass names as rule_packs to the review tools."""
    return {p: catalog.pack(p).get("title", p) for p in catalog.available_packs()}


@mcp.resource("architect://templates/design-doc", mime_type="text/markdown")
def design_template() -> str:
    return catalog.text("templates/design_doc.md")


@mcp.resource("architect://templates/adr", mime_type="text/markdown")
def adr_template() -> str:
    return catalog.text("templates/adr.md")


@mcp.resource("architect://scenarios/{scenario_id}", mime_type="text/markdown",
              description="Demo business briefs, e.g. dealer-fault-diagnosis")
def scenario_resource(scenario_id: str) -> str:
    return catalog.scenario(scenario_id)


@mcp.resource("architect://runs/{run_id}/{name}", mime_type="text/markdown",
              description="Generated outputs: design.md, review.md")
def run_resource(run_id: str, name: str) -> str:
    return wf.load_run(run_id, name)


# ------------------------------------------------------------------ deterministic tools
@mcp.tool(annotations=READ_ONLY)
def assess_pattern_fit(requirements: Requirements) -> PatternFit:
    """Rank agent patterns deterministically from the requirement signals (no LLM)."""
    return d.assess_pattern_fit(requirements)


@mcp.tool(annotations=READ_ONLY)
def map_platform(design: ComponentDesign, cloud: Literal["azure", "aws", "gcp"]) -> PlatformMapping:
    """Map each component to a cloud service by catalog lookup. Unknown types are reported, never invented."""
    return d.map_platform(design, cloud)


@mcp.tool(annotations=READ_ONLY)
def check_traceability(requirements: Requirements, design: ComponentDesign, llmops: LLMOpsPlan) -> TraceReport:
    """Verify every requirement maps to a component and every component has a test."""
    return d.check_traceability(requirements, design, llmops)


@mcp.tool(annotations=READ_ONLY)
def render_diagram(design: ComponentDesign) -> str:
    """Render the component design as a Mermaid flowchart."""
    return d.render_diagram(design)


def _packs(rule_packs: list[str] | None, run_id: str | None) -> list[str]:
    """Explicit packs win; otherwise a W1 run reuses the packs it was designed with."""
    if rule_packs is not None:
        for p in rule_packs:
            catalog.pack(p)
        return list(rule_packs)
    return wf.load_meta(run_id).get("rule_packs", []) if run_id else []


def _markdown(document: str | None, run_id: str | None) -> str:
    if run_id:
        return wf.load_run(run_id, "design.md")
    if document:
        return document
    raise ValueError("provide document (markdown) or run_id")


@mcp.tool(annotations=READ_ONLY)
def load_design(document: str | None = None, run_id: str | None = None) -> DesignDoc:
    """Parse a markdown design doc (or a W1 run) into sections used as citation anchors."""
    return d.load_design(_markdown(document, run_id))


@mcp.tool(annotations=READ_ONLY)
def run_rule_checks(document: str | None = None, run_id: str | None = None,
                    rule_packs: list[str] | None = None) -> list[Finding]:
    """Run the deterministic review rules (required sections present and filled), plus any rule packs."""
    return d.run_rule_checks(d.load_design(_markdown(document, run_id)), _packs(rule_packs, run_id))


@mcp.tool(annotations=READ_ONLY)
def score_readiness(findings: list[Finding]) -> Readiness:
    """Score findings by category and decide go / conditional / no-go."""
    return d.score_readiness(findings)


# ------------------------------------------------------------------ LLM-backed tools
@mcp.tool(annotations=LLM_CALL)
def extract_requirements(brief: str) -> Requirements:
    """Extract FR/NFR requirements and pattern signals; every item carries a verbatim quote from the brief."""
    return lt.extract_requirements(get_llm(), brief)


@mcp.tool(annotations=LLM_CALL)
def design_components(requirements: Requirements, pattern_fit: PatternFit) -> ComponentDesign:
    """Design components for the top-ranked pattern; every requirement must be satisfied by a component."""
    return lt.design_components(get_llm(), requirements, pattern_fit)


@mcp.tool(annotations=LLM_CALL)
def plan_llmops(design: ComponentDesign) -> LLMOpsPlan:
    """Evals, monitors, versioning and governance; every component gets a test or metric."""
    return lt.plan_llmops(get_llm(), design)


@mcp.tool(annotations=LLM_CALL)
def draft_adrs(requirements: Requirements, pattern_fit: PatternFit, design: ComponentDesign) -> list[ADR]:
    """Architecture decision records, each with at least two options and requirement references."""
    return lt.draft_adrs(get_llm(), requirements, pattern_fit, design)


@mcp.tool(annotations=LLM_CALL)
def write_exec_summary(design: ComponentDesign, brief: str) -> str:
    """One-page, jargon-free executive summary (under 400 words, acronyms expanded)."""
    return lt.write_exec_summary(get_llm(), design, brief)


@mcp.tool(annotations=LLM_CALL)
def judge_rules(document: str | None = None, run_id: str | None = None,
                rule_ids: list[str] | None = None, rule_packs: list[str] | None = None) -> list[Finding]:
    """Apply the judged review rules; each failing finding must quote the section it cites."""
    return lt.judge_rules(get_llm(), d.load_design(_markdown(document, run_id)), rule_ids, _packs(rule_packs, run_id))


# ------------------------------------------------------------------ full workflows
class ConfirmRequirements(BaseModel):
    approve: bool = Field(True, description="Approve these requirements and continue")
    additional_context: str = Field("", description="Anything missing or wrong? Add context and the agent will re-extract")


def _engine():
    try:
        from ai_architect import graphs
        return graphs
    except ImportError:
        return None


class DesignResult(BaseModel):
    run_id: str
    engine: str
    traceability_passed: bool
    selected_pattern: str
    design_doc: str


@mcp.tool(annotations=LLM_CALL)
async def run_solution_design(brief: str, cloud: Literal["azure", "aws", "gcp"] = "aws",
                              title: str = "Agentic Solution Design", ctx: Context | None = None) -> DesignResult:
    """W1 end to end: requirements -> (you confirm) -> pattern fit -> components -> platform -> LLMOps ->
    traceability gate -> diagram, ADRs, executive summary. Saves to architect://runs/<run_id>/design.md."""

    async def confirm(reqs: Requirements) -> str | None:
        if ctx is None:
            return None
        listing = "\n".join(f"{r.id}: {r.text}" for r in reqs.items)
        try:
            res = await ctx.elicit(f"Confirm the extracted requirements:\n{listing}", ConfirmRequirements)
        except Exception:  # client does not support elicitation: continue with what we have
            return None
        if res.action == "accept" and res.data.additional_context.strip():
            return res.data.additional_context.strip()
        return None

    cfg = {"confirm": confirm, "llm": get_llm()}
    state = {"brief": brief, "cloud": cloud, "title": title}
    graphs = _engine()
    if graphs:
        out = await graphs.solution_design_graph().ainvoke(
            state, {"configurable": {**cfg, "thread_id": str(uuid.uuid4())}, "recursion_limit": 50})
    else:
        out = await wf.solution_design(brief, cloud, title, cfg)
    return DesignResult(run_id=out["run_id"], engine="langgraph" if graphs else "sequential",
                        traceability_passed=out["trace"].passed,
                        selected_pattern=f"{out['fit'].ranked[0].id} {out['fit'].ranked[0].name}",
                        design_doc=out["design_doc"])


class ReviewResult(BaseModel):
    run_id: str
    engine: str
    decision: str
    readiness: float
    blockers: list[str]
    review: str


@mcp.tool(annotations=LLM_CALL)
async def run_architecture_review(document: str | None = None, run_id: str | None = None,
                                  rule_packs: list[str] | None = None) -> ReviewResult:
    """W2 end to end: rule checks + judged rules -> citation validation (re-judge once) -> readiness score.
    Pass a markdown design doc, or the run_id of a W1 design to review it. rule_packs adds domain rules
    (see list_rule_packs), e.g. ["healthcare"]."""
    markdown = _markdown(document, run_id)
    cfg = {"llm": get_llm(), "rule_packs": _packs(rule_packs, run_id)}
    graphs = _engine()
    if graphs:
        state = {"markdown": markdown, **({"run_id": run_id} if run_id else {})}
        out = await graphs.architecture_review_graph().ainvoke(
            state, {"configurable": {**cfg, "thread_id": str(uuid.uuid4())}, "recursion_limit": 30})
    else:
        out = await wf.architecture_review(markdown, run_id, cfg)
    r = out["readiness"]
    return ReviewResult(run_id=out["run_id"], engine="langgraph" if graphs else "sequential",
                        decision=r.decision, readiness=r.score, blockers=r.blockers, review=out["review"])


class LoopResult(BaseModel):
    run_id: str
    engine: str
    rounds: int
    history: list[dict] = Field(description="Per version: decision, readiness score, findings")
    final_decision: str
    brief: str = Field(description="One-page brief (also saved as brief.md)")


@mcp.tool(annotations=LLM_CALL)
async def run_design_review_revise(brief: str, cloud: Literal["azure", "aws", "gcp"] = "aws",
                                   title: str = "Agentic Solution Design", max_rounds: int = 2,
                                   rule_packs: list[str] | None = None) -> LoopResult:
    """Full demo loop: design (W1) -> review (W2) -> revise the design against the findings -> re-review,
    until the review says go or max_rounds is reached. Saves design*.md, review*.md and a one-page brief.md.
    rule_packs adds domain rules to every review, e.g. ["healthcare"]."""
    cfg = {"llm": get_llm(), "rule_packs": _packs(rule_packs or [], None)}
    graphs = _engine()

    async def design_fn(b, c, t, cfg_):
        if not graphs:
            return await wf.solution_design(b, c, t, cfg_)
        return await graphs.solution_design_graph().ainvoke(
            {"brief": b, "cloud": c, "title": t},
            {"configurable": {**cfg_, "thread_id": str(uuid.uuid4())}, "recursion_limit": 50})

    async def review_fn(md, run_id, cfg_, review_file):
        if not graphs:
            return await wf.architecture_review(md, run_id, cfg_, review_file)
        return await graphs.architecture_review_graph().ainvoke(
            {"markdown": md, "run_id": run_id, "review_file": review_file},
            {"configurable": {**cfg_, "thread_id": str(uuid.uuid4())}, "recursion_limit": 30})

    out = await wf.design_review_revise(brief, cloud, title, cfg, max_rounds, design_fn, review_fn)
    return LoopResult(run_id=out["run_id"], engine="langgraph" if graphs else "sequential",
                      rounds=len(out["history"]) - 1, history=out["history"],
                      final_decision=out["review"]["readiness"].decision, brief=out["brief"])


# ------------------------------------------------------------------ prompts
@mcp.prompt(title="Design an agentic AI solution")
def design_agentic_solution(brief: str, cloud: str = "aws") -> str:
    return f"""Act as a principal AI architect using the ai-architect-agent tools, step by step:
1. extract_requirements on the brief. Show me the requirements and signals; wait for my OK or corrections.
2. assess_pattern_fit. Explain the top two patterns and whether an agent is needed at all.
3. design_components with the top pattern, then map_platform for {cloud}.
4. plan_llmops, then check_traceability. If it fails, fix the design and re-check.
5. render_diagram and draft_adrs. Finish with write_exec_summary.
Read architect://catalog/patterns and architect://templates/design-doc first.

Brief:
{brief}"""


@mcp.prompt(title="Review an AI architecture")
def review_ai_architecture(document: str) -> str:
    return f"""Review this AI solution design with the ai-architect-agent tools:
1. Read architect://rules/review.
2. run_rule_checks, then judge_rules. Every finding must cite a section; quotes must be verbatim.
3. score_readiness and give me go / conditional / no-go with the blockers first, then required changes.

Design:
{document}"""


@mcp.prompt(title="Design, then review (demo)")
def design_then_review(brief: str, cloud: str = "aws") -> str:
    return f"""Demo flow:
1. run_design_review_revise with this brief on {cloud}.
2. Show me the one-page brief it returns.
3. Then explain: which pattern was selected and why, what the first review found, what the agent changed
   in response, and whether the final review reached go. Point out anything a human architect should still own.

Brief:
{brief}"""


def main() -> None:
    if "--http" in sys.argv:
        mcp.run(transport="streamable-http")
    else:
        mcp.run()


if __name__ == "__main__":
    main()
