"""Command line for the planner.

    python -m customization_planner.cli plan                      (the five live prior-auth runs, no model)
    python -m customization_planner.cli plan --runs pa-live-full,pa-live-full-2 --plan-id my-plan
    python -m customization_planner.cli memo --plan-id <id>       (model drafts the partner memo, code checks it)
    python -m customization_planner.cli probe                     (model accepts the memo schema)

The last line of output is "RESULT <json>" for the job runner.
"""
import argparse
import json

from customization_planner import catalog, workflows as wf


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="customization_planner.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--runs", default=",".join(wf.LIVE_RUNS))
    p.add_argument("--suite", default="prior-auth")
    p.add_argument("--plan-id", default=None)
    p = sub.add_parser("memo")
    p.add_argument("--plan-id", required=True)
    p.add_argument("--runs", default=",".join(wf.LIVE_RUNS))
    p.add_argument("--suite", default="prior-auth")
    sub.add_parser("probe")
    a = ap.parse_args(argv)

    if a.cmd == "plan":
        plan, files = wf.run_plan([r for r in a.runs.split(",") if r], a.suite, a.plan_id)
        print(files["plan.md"])
        print(f"outputs: {catalog.plan_dir(plan.plan_id)}")
        print("RESULT " + json.dumps({"plan_id": plan.plan_id, "verdict": plan.verdict,
                                      "pairs": len(plan.pairs), "sft": len(plan.sft),
                                      "failed_gates": [g.name for g in plan.gates if not g.passed]}))
        return 0
    from agent_evaluator.llm import get_llm
    from customization_planner.memo import draft_memo
    if a.cmd == "memo":
        plan, files = wf.run_plan([r for r in a.runs.split(",") if r], a.suite, a.plan_id)
        memo = draft_memo(get_llm(), plan, files["plan.md"])
        text = f"# {memo.headline}\n\n{memo.body}\n\n---\nDrafted by a model from plan `{plan.plan_id}`; every " \
               "number was checked against the plan by code.\n"
        (catalog.plan_dir(plan.plan_id) / "memo.md").write_text(text, encoding="utf-8")
        print(text)
        print("RESULT " + json.dumps({"plan_id": plan.plan_id, "memo": "ok"}))
        return 0
    if a.cmd == "probe":
        from customization_planner.models import Memo
        m = get_llm().structured(Memo, "Reply briefly.", "Headline: 'Probe ok'. Body: 'ok'. numbers_used: [].")
        print("RESULT " + json.dumps({"Memo": bool(m.headline)}))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
