"""Command line for the evaluator.

    python -m agent_evaluator.cli eval     --candidate prior-auth-v2 --baseline prior-auth-v1
    python -m agent_evaluator.cli accuracy --run eval-set
    python -m agent_evaluator.cli check    --run prior-auth-v2          (code check only, no model)
    python -m agent_evaluator.cli probe                                 (model accepts the schema)

The last line of output is "RESULT <json>" for the job runner.
"""
import argparse
import asyncio
import json

from agent_evaluator import catalog, workflows as wf
from agent_evaluator.llm import env
from agent_evaluator.tools import deterministic as d


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="agent_evaluator.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("eval")
    p.add_argument("--suite", default="prior-auth")
    p.add_argument("--candidate", required=True)
    p.add_argument("--baseline", default=None)
    p = sub.add_parser("accuracy")
    p.add_argument("--run", default="eval-set")
    p = sub.add_parser("check")
    p.add_argument("--suite", default="prior-auth")
    p.add_argument("--run", required=True)
    sub.add_parser("probe")
    a = ap.parse_args(argv)

    if a.cmd == "check":
        suite = catalog.suite(a.suite)
        rows = []
        for t in catalog.run_traces(a.run):
            c = d.check_task_success(d.load_trajectory(t), suite)
            rows.append({"trace": c.trace_id, "passed": c.passed, "outcome": c.outcome,
                         "safety": c.safety_failure, "symptoms": [s.label for s in c.symptoms]})
            print(json.dumps(rows[-1]))
        print("RESULT " + json.dumps({"passed": sum(r["passed"] for r in rows), "total": len(rows)}))
        return 0

    if a.cmd == "probe":
        from agent_evaluator.llm import get_llm
        from agent_evaluator.models import FailureAnalysis
        try:
            get_llm().structured(FailureAnalysis, "Return a minimal valid example.", "Example please.")
            ok = "ok"
        except Exception as e:  # noqa: BLE001
            ok = f"FAIL: {str(e)[:300]}"
        print("RESULT " + json.dumps({"FailureAnalysis": ok}))
        return 0 if ok == "ok" else 1

    if a.cmd == "accuracy":
        out = asyncio.run(wf.evaluator_accuracy(a.run, {"model_name": env("MODEL", "unset")}))
        print(out["report"])
        m = {k: v for k, v in out["metrics"].items() if k != "rows"}
        print("RESULT " + json.dumps({"run_id": out["run_id"], **m, "gates": out["gates"]}))
        return 0 if all(out["gates"].values()) else 1

    try:
        from agent_evaluator import graphs
        out = asyncio.run(graphs.trajectory_eval_graph().ainvoke(
            {"suite_id": a.suite, "candidate_run": a.candidate, "baseline_run": a.baseline},
            {"configurable": {"thread_id": "cli"}, "recursion_limit": 20}))
        engine = "langgraph"
    except ImportError:
        out = asyncio.run(wf.trajectory_eval(a.suite, a.candidate, a.baseline))
        engine = "sequential"
    print(out["report"])
    g = out["regression"]
    print("RESULT " + json.dumps({"run_id": out["run_id"], "engine": engine, "decision": g.decision,
                                  "candidate_rate": g.candidate_rate, "baseline_rate": g.baseline_rate,
                                  "fixed": g.fixed, "broken": g.broken, "safety": g.safety_failures,
                                  "root_causes": {r.task_id: r.root_cause for r in
                                                  out["runs"][a.candidate].results if not r.passed}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
