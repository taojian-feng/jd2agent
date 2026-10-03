"""prior-auth-reviewer MCP server: the working agent, its retrieval, and its case memory.

Run:  uv run prior-auth-reviewer          (stdio)      uv run prior-auth-reviewer --http
It works against the fictional health plan systems in systems.py (connected over MCP, in process).
"""
import sys

try:  # MCP Python SDK 2.x
    from mcp.server.mcpserver import Context, MCPServer as FastMCP
except ImportError:  # 1.x
    from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from prior_auth_reviewer import retrieval as rt
from prior_auth_reviewer import workflows as wf
from prior_auth_reviewer.models import CaseResult
from prior_auth_reviewer.systems import HealthPlanSystems, load_cases

mcp = FastMCP(
    "prior-auth-reviewer",
    instructions=(
        "Prepares prior authorization cases (fictional health plan). It retrieves the coverage policy, assembles "
        "only the note sentences the criteria need, proposes cited findings, has a critic check them, and lets code "
        "decide: approve (after a person confirms), ask for documentation, or route to a nurse. It never denies."
    ),
)
READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)
ACTS = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True)

SYSTEMS = HealthPlanSystems()          # one shared mock environment, so a resumed case sees new documentation
LIBRARY = wf.library_from(SYSTEMS)


# ------------------------------------------------------------------ resources
@mcp.resource("policy://policies/{policy_id}", mime_type="text/markdown", description="Coverage policy text")
def policy_resource(policy_id: str) -> str:
    return SYSTEMS.get_policy(policy_id)["markdown"]


@mcp.resource("case://cases/{case_id}", mime_type="application/json",
              description="Case memory: outcome, findings and history (no clinical text)")
def case_resource(case_id: str) -> str:
    import json
    return json.dumps(wf.CaseStore().load(case_id) or {}, indent=1)


# ------------------------------------------------------------------ retrieval tools
class Clause(BaseModel):
    chunk_id: str
    policy_id: str
    title: str
    text: str
    score: float


@mcp.tool(annotations=READ_ONLY)
def search_policies(query: str, k: int = 3) -> list[dict]:
    """Rank coverage policies for a procedure description or code (hybrid retrieval + metadata rerank)."""
    return [{"policy_id": p, "title": LIBRARY.docs[p].title, "score": round(s, 4)}
            for p, s in LIBRARY.search_policies(query, k)]


@mcp.tool(annotations=READ_ONLY)
def search_clauses(query: str, k: int = 5, stage: str = "rerank") -> list[Clause]:
    """Find policy clauses, e.g. 'conservative therapy before lumbar MRI'. stage: bm25 | dense | hybrid | rerank,
    to compare retrievers."""
    if stage not in ("bm25", "dense", "hybrid", "rerank"):
        raise ValueError("stage must be bm25, dense, hybrid or rerank")
    return [Clause(chunk_id=h.chunk.id, policy_id=h.chunk.policy_id, title=h.chunk.title, text=h.chunk.text,
                   score=round(h.score, 4)) for h in LIBRARY.search_clauses(query, k, stage)]


@mcp.tool(annotations=READ_ONLY)
def retrieval_quality() -> dict:
    """Recall@1, recall@3 and MRR per retrieval stage on the labeled query set."""
    import yaml
    from prior_auth_reviewer.systems import DATA
    return rt.evaluate_retrieval(LIBRARY, yaml.safe_load((DATA / "retrieval_eval.yaml").read_text())["queries"])


# ------------------------------------------------------------------ the agent
class ConfirmApproval(BaseModel):
    approve: bool = Field(False, description="Confirm this approval")
    approver: str = Field("", description="Your name or user id, recorded with the approval")


class ReviewOutput(BaseModel):
    result: CaseResult
    trace_steps: int
    case_memory: dict


async def _run(case_id: str, critic: bool, ctx: Context | None, memory: bool, auto_approve_demo: bool) -> ReviewOutput:
    if case_id not in load_cases():
        raise ValueError(f"unknown case {case_id}")

    async def approver(cid, decision):
        if ctx is not None:
            try:
                r = await ctx.elicit(f"Approve {cid}? {decision.reason}", ConfirmApproval)
                if r.action == "accept" and r.data.approve and r.data.approver.strip():
                    return r.data.approver.strip()
                return None
            except Exception:  # client cannot ask a person
                pass
        return "demo-auto-approval" if auto_approve_demo else None

    out = await wf.run_suite(f"mcp-{case_id}", [case_id], critic=critic, approver=approver, systems=SYSTEMS,
                             memory=memory)
    return ReviewOutput(result=out["results"][case_id], trace_steps=len(out["traces"][case_id].steps),
                        case_memory=wf.CaseStore().load(case_id) or {})


@mcp.tool(annotations=ACTS)
async def review_case(case_id: str, critic: bool = True, auto_approve_demo: bool = False,
                      ctx: Context | None = None) -> ReviewOutput:
    """Review one case end to end (PA-001 ... PA-012). An approval needs a person to confirm it (asked through the
    client); without one it goes to a nurse instead, unless auto_approve_demo is set."""
    return await _run(case_id, critic, ctx, memory=False, auto_approve_demo=auto_approve_demo)


@mcp.tool(annotations=ACTS)
async def resume_case(case_id: str, addendum: str, auto_approve_demo: bool = False,
                      ctx: Context | None = None) -> ReviewOutput:
    """Continue a case after the provider sends more documentation. The agent reads its stored findings (case
    memory) and re-checks every criterion against the updated notes."""
    SYSTEMS.add_addendum(case_id, addendum)
    return await _run(case_id, True, ctx, memory=True, auto_approve_demo=auto_approve_demo)


@mcp.prompt(title="Review a prior authorization case")
def review_prior_auth_case(case_id: str) -> str:
    return f"""Review prior authorization case {case_id} with the prior-auth-reviewer tools:
1. Call review_case. If it asks you to confirm an approval, show me the findings first.
2. Show each criterion with its finding, the policy clause and the cited note sentences.
3. If the outcome is request_info, tell me what is missing; if human_review, why.
Never describe the outcome as a denial: the agent cannot deny."""


def main() -> None:
    mcp.run(transport="streamable-http") if "--http" in sys.argv else mcp.run()


if __name__ == "__main__":
    main()
