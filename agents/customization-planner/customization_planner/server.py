"""customization-planner MCP server: Resources (fix routes, plan outputs), Tools (W3 steps), Prompts.

Run:  uv run customization-planner                 (stdio, for Claude Desktop / IDEs)
      uv run customization-planner --http          (streamable HTTP on :8000)
"""
import sys

try:  # MCP Python SDK 2.x: FastMCP was renamed MCPServer
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:  # MCP Python SDK 1.x
    from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from customization_planner import catalog, planner, workflows as wf
from customization_planner.models import DecisionRecord, FailureRoute, Gate

mcp = FastMCP(
    "customization-planner",
    instructions=(
        "Answers 'should we fine-tune this agent's model?' from its recorded runs (W3). Code grades every trace, "
        "routes each failure to the cheapest fix that can hold it, builds SFT and preference data only where it can "
        "verify the target, and checks readiness gates. Start with the 'plan_model_customization' prompt or call "
        "plan_customization."
    ),
)

READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)
LLM_CALL = ToolAnnotations(readOnlyHint=True, idempotentHint=False, openWorldHint=True)


@mcp.resource("cp://routes", mime_type="text/yaml",
              description="Fix routes in order (code, workflow, tool interface, retrieval, model judgment) and readiness gates")
def routes_resource() -> str:
    return catalog.text("fix_routes.yaml")


@mcp.resource("cp://plans/{plan_id}/{name}", mime_type="text/markdown",
              description="Plan outputs: plan.md, sft.jsonl, dpo.jsonl, recipe.yaml, stats.json, memo.md")
def plan_resource(plan_id: str, name: str) -> str:
    return wf.load_output(plan_id, name)


@mcp.tool(annotations=READ_ONLY)
def list_trace_runs() -> list[str]:
    """Recorded runs available (from agent-evaluator/traces)."""
    return catalog.list_runs()


@mcp.tool(annotations=READ_ONLY)
def grade_runs(run_ids: list[str], suite_id: str = "prior-auth") -> list[DecisionRecord]:
    """Grade every trace with the evaluator's success check and read the model's decisions out of it."""
    graded = planner.grade(run_ids, catalog.suite(suite_id), {r: catalog.run_traces(r) for r in run_ids})
    return [r for r, _ in graded]


@mcp.tool(annotations=READ_ONLY)
def route_failures(run_ids: list[str], suite_id: str = "prior-auth") -> list[FailureRoute]:
    """Route each failing run to its fix: code guardrail, workflow, tool interface, retrieval/context or model judgment."""
    plan, _ = wf.run_plan(run_ids, suite_id, plan_id="routes-preview", write=False)
    return plan.routes


@mcp.tool(annotations=READ_ONLY)
def build_datasets(run_ids: list[str], suite_id: str = "prior-auth") -> dict:
    """SFT examples and preference pairs the runs can support, with what was dropped and why."""
    plan, _ = wf.run_plan(run_ids, suite_id, plan_id="data-preview", write=False)
    return {"sft": [e.model_dump() for e in plan.sft], "pairs": [p.model_dump() for p in plan.pairs],
            "dropped": plan.stats["dropped"], "split": plan.split}


@mcp.tool(annotations=READ_ONLY)
def write_recipe(run_ids: list[str], suite_id: str = "prior-auth") -> dict:
    """Training recipe (blocked unless every readiness gate passes) and the regression gate the tuned model must pass."""
    plan, _ = wf.run_plan(run_ids, suite_id, plan_id="recipe-preview", write=False)
    return planner.recipe(plan)


@mcp.tool(annotations=READ_ONLY)
def check_readiness(run_ids: list[str], suite_id: str = "prior-auth") -> list[Gate]:
    """Readiness gates for post-training on the data these runs can support."""
    plan, _ = wf.run_plan(run_ids, suite_id, plan_id="gates-preview", write=False)
    return plan.gates


@mcp.tool()
def plan_customization(run_ids: list[str], suite_id: str = "prior-auth", plan_id: str | None = None) -> dict:
    """Full W3: grade, route, build SFT/DPO data, check gates; writes plan.md, sft.jsonl, dpo.jsonl, recipe.yaml."""
    plan, files = wf.run_plan(run_ids, suite_id, plan_id)
    return {"plan_id": plan.plan_id, "verdict": plan.verdict, "recommendation": plan.recommendation,
            "plan_md": files["plan.md"], "resources": [f"cp://plans/{plan.plan_id}/{n}" for n in files]}


@mcp.tool(annotations=LLM_CALL)
def draft_partner_memo(plan_id: str, run_ids: list[str], suite_id: str = "prior-auth") -> dict:
    """Model drafts the answer to 'should we fine-tune?'; code rejects any number not in the plan."""
    from agent_evaluator.llm import get_llm
    from customization_planner.memo import draft_memo
    plan, files = wf.run_plan(run_ids, suite_id, plan_id)
    memo = draft_memo(get_llm(), plan, files["plan.md"])
    return memo.model_dump()


@mcp.prompt()
def plan_model_customization(run_ids: str = ",".join(wf.LIVE_RUNS)) -> str:
    """Should we fine-tune? Plan from recorded runs and explain the answer."""
    return (f"Call plan_customization with run_ids {run_ids.split(',')}. Lead with the verdict. Then explain which "
            "failures are fixed in code or workflow, which are model judgment, how much verified training data the "
            "runs support, and which readiness gates fail. Quote numbers only from the plan.")


def main() -> None:
    if "--http" in sys.argv:
        mcp.run(transport="streamable-http")
    else:
        mcp.run()


if __name__ == "__main__":
    main()
