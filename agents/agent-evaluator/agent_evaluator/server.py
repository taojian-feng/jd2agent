"""agent-evaluator MCP server: Resources (taxonomy, suites, traces), Tools (W3 steps), Prompts.

Run:  uv run agent-evaluator                 (stdio, for Claude Desktop / IDEs)
      uv run agent-evaluator --http          (streamable HTTP on :8000)
"""
import json
import sys
import uuid

try:  # MCP Python SDK 2.x: FastMCP was renamed MCPServer
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:  # MCP Python SDK 1.x
    from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from agent_evaluator import catalog, workflows as wf
from agent_evaluator.llm import get_llm
from agent_evaluator.models import Diagnosis, Regression, RunResult, SuccessCheck, Trajectory
from agent_evaluator.tools import deterministic as d
from agent_evaluator.tools import llm_tools as lt

mcp = FastMCP(
    "agent-evaluator",
    instructions=(
        "Evaluates AI agents from their recorded trajectories (W3). Code decides pass/fail against a task spec and "
        "finds symptoms; the model names the root cause from a fixed failure taxonomy, and every label must cite "
        "trace steps that exist and quote them verbatim. Start with the 'evaluate_agent_change' prompt or call "
        "run_trajectory_eval with a candidate run and, optionally, a baseline run."
    ),
)

READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)
LLM_CALL = ToolAnnotations(readOnlyHint=True, idempotentHint=False, openWorldHint=True)


# ------------------------------------------------------------------ resources
@mcp.resource("eval://taxonomy/failures", mime_type="text/yaml",
              description="Fixed failure labels, which ones code detects, and the root cause rule")
def taxonomy_resource() -> str:
    return catalog.text("failure_taxonomy.yaml")


@mcp.resource("eval://suites/{suite_id}", mime_type="text/yaml",
              description="Task suite: expected outcome, required steps and forbidden actions per task")
def suite_resource(suite_id: str) -> str:
    catalog.suite(suite_id)  # validates the name
    return catalog.text(f"task_suites/{suite_id}.yaml")


@mcp.resource("eval://scenarios/{scenario_id}", mime_type="text/markdown",
              description="What the agent under evaluation is supposed to do, e.g. prior-auth (fictional, no PHI)")
def scenario_resource(scenario_id: str) -> str:
    return catalog.scenario(scenario_id)


@mcp.resource("eval://traces/{run_id}", mime_type="application/json",
              description="All recorded traces of a run, e.g. prior-auth-v1, prior-auth-v2, eval-set")
def traces_resource(run_id: str) -> str:
    return json.dumps(catalog.run_traces(run_id), indent=1)


@mcp.resource("eval://runs/{run_id}/{name}", mime_type="text/markdown",
              description="Evaluation outputs: report.md, accuracy.md, results.json")
def run_resource(run_id: str, name: str) -> str:
    return wf.load_run(run_id, name)


# ------------------------------------------------------------------ deterministic tools
@mcp.tool(annotations=READ_ONLY)
def list_trace_runs() -> list[str]:
    """Recorded runs available to evaluate."""
    return catalog.list_runs()


@mcp.tool(annotations=READ_ONLY)
def load_trajectory(trace_json: str | None = None, run_id: str | None = None,
                    trace_id: str | None = None) -> Trajectory:
    """Parse one exported trace: pass the JSON text, or run_id + trace_id of a recorded run."""
    if trace_json:
        return d.load_trajectory(trace_json)
    for t in catalog.run_traces(run_id or ""):
        if t["trace_id"] == trace_id:
            return d.load_trajectory(t)
    raise ValueError(f"trace {trace_id!r} not found in run {run_id!r}")


@mcp.tool(annotations=READ_ONLY)
def check_task_success(trajectory: Trajectory, suite_id: str = "prior-auth") -> SuccessCheck:
    """Code-only check against the task spec: outcome, required steps, forbidden actions, unhandled errors,
    loops and the step cap. The outcome is derived from the terminal action, never from the agent's own claim."""
    return d.check_task_success(trajectory, catalog.suite(suite_id))


@mcp.tool(annotations=READ_ONLY)
def compare_runs(candidate: RunResult, baseline: RunResult | None = None) -> Regression:
    """Success rate, tasks fixed / broken / still failing, root-cause mix, and the release gate
    (no-go on any safety failure or a lower success rate)."""
    return d.compare_runs(candidate, baseline)


@mcp.tool(annotations=READ_ONLY)
def write_eval_report(regression: Regression, candidate: RunResult, baseline: RunResult | None = None) -> str:
    """Markdown report: decision, summary, root causes, per-task table, failures with cited steps."""
    return d.write_eval_report(regression, candidate, baseline)


# ------------------------------------------------------------------ LLM-backed tool
@mcp.tool(annotations=LLM_CALL)
def classify_failures(trajectory: Trajectory, suite_id: str = "prior-auth") -> Diagnosis:
    """Root cause and failure labels for a failing trace. Labels come from the taxonomy, cite step ids that
    exist, and quote a cited step verbatim, checked by code; code-found symptoms are always kept."""
    suite = catalog.suite(suite_id)
    check = d.check_task_success(trajectory, suite)
    if check.passed:
        raise ValueError("this trace passes the task check; there is nothing to classify")
    return lt.classify_failures(get_llm(), trajectory, check, suite)


# ------------------------------------------------------------------ full workflow
def _engine():
    try:
        from agent_evaluator import graphs
        return graphs
    except ImportError:
        return None


class EvalResult(BaseModel):
    run_id: str
    engine: str
    decision: str
    candidate_rate: float
    baseline_rate: float | None
    fixed: list[str]
    broken: list[str]
    safety_failures: list[str]
    report: str = Field(description="Markdown report (also saved as eval://runs/<run_id>/report.md)")


@mcp.tool(annotations=LLM_CALL)
async def run_trajectory_eval(candidate_run: str, baseline_run: str | None = None,
                              suite_id: str = "prior-auth") -> EvalResult:
    """W3 end to end: load traces -> code check per task -> root cause per failing trace (model, citation-checked)
    -> compare with the baseline -> release gate and report."""
    cfg = {"llm": get_llm()}
    state = {"suite_id": suite_id, "candidate_run": candidate_run, "baseline_run": baseline_run}
    graphs = _engine()
    if graphs:
        out = await graphs.trajectory_eval_graph().ainvoke(
            state, {"configurable": {**cfg, "thread_id": str(uuid.uuid4())}, "recursion_limit": 20})
    else:
        out = await wf.trajectory_eval(suite_id, candidate_run, baseline_run, cfg)
    g = out["regression"]
    return EvalResult(run_id=out["run_id"], engine="langgraph" if graphs else "sequential", decision=g.decision,
                      candidate_rate=g.candidate_rate, baseline_rate=g.baseline_rate, fixed=g.fixed,
                      broken=g.broken, safety_failures=g.safety_failures, report=out["report"])


# ------------------------------------------------------------------ prompts
@mcp.prompt(title="Evaluate an agent change")
def evaluate_agent_change(candidate_run: str, baseline_run: str = "", suite_id: str = "prior-auth") -> str:
    base = f" against the baseline run {baseline_run}" if baseline_run else ""
    return f"""Evaluate the agent run {candidate_run}{base} on suite {suite_id} with the agent-evaluator tools:
1. Read eval://taxonomy/failures and eval://suites/{suite_id}.
2. Call run_trajectory_eval.
3. Tell me the release decision first, with the reasons. Then: what got better, what broke, and for each failure
   the root cause and the trace steps that show it (quote them). Flag any safety failure at the top.
4. Say what a human reviewer should still check that code and the model cannot."""


def main() -> None:
    if "--http" in sys.argv:
        mcp.run(transport="streamable-http")
    else:
        mcp.run()


if __name__ == "__main__":
    main()
