"""Plan report (Markdown), written by code from the plan. The optional memo is the only model-written text."""
from customization_planner.models import Plan

VERDICT = {"ready": "READY TO TRAIN", "not_ready": "NOT READY TO TRAIN", "fix_first": "FIX IN CODE FIRST"}


def write_plan(plan: Plan) -> str:
    s = plan.stats
    L = [f"# Customization plan: {plan.plan_id}", "",
         f"Runs: {', '.join(f'`{r}`' for r in plan.runs)} · {plan.traces} traces · {plan.passed} passed",
         "", f"## Verdict: {VERDICT[plan.verdict]}", ""]
    L += [f"- {line}" for line in plan.recommendation]
    L += ["", "## Runs", "", "| Run | Passed | Model calls |", "|---|---|---|"]
    L += [f"| `{run}` | {v['passed']}/{v['traces']} | {v['model_calls']} |" for run, v in s["runs"].items()]
    L += ["", "## Failures and fix routes", ""]
    if plan.routes:
        L += ["| Run | Task | Label | Route |", "|---|---|---|---|"]
        L += [f"| `{r.run_id}` | {r.task_id} | `{r.label}` | {r.route} |" for r in plan.routes]
    else:
        L.append("No failing runs.")
    L += ["", "## Model decisions that differ from the verified answer", ""]
    if plan.changes:
        L += ["| Task | Criterion | Run | Where | Model said | Verified | Evidence in context | Route |",
              "|---|---|---|---|---|---|---|---|"]
        L += [f"| {c.task_id} | {c.criterion_id} | `{c.run_id}` | {c.source.replace('_', ' ')} | {c.got} | "
              f"{c.verified} | {'yes' if c.evidence_in_context else 'no'} | {c.route} |" for c in plan.changes]
    else:
        L.append("None.")
    L += ["", f"Changed decisions code cannot verify (the task's outcome does not pin the criterion down): "
          f"{plan.unverifiable_changes}.", "", "## Training data", "",
          "| | Raw | Kept |", "|---|---|---|",
          f"| SFT examples | {s['sft_raw']} | {s['sft_unique']} |",
          f"| Preference pairs | {s['pairs_raw']} | {s['pairs_unique']} |", ""]
    if s["dropped"]:
        L += ["Dropped:", ""] + [f"- {k}: {v}" for k, v in sorted(s["dropped"].items())] + [""]
    L += [f"Split by task. Train: {', '.join(plan.split['train'])}. Eval: {', '.join(plan.split['eval'])}.", "",
          "## Readiness gates", "", "| Gate | Target | Actual | |", "|---|---|---|---|"]
    L += [f"| {g.name} | {g.target} | {g.actual} | {'pass' if g.passed else '**fail**'} |" for g in plan.gates]
    L += ["", "---", "Everything above is computed by code from the recorded traces: pass/fail by the evaluator's "
          "success check, verified answers from passing runs on approve tasks, targets checked by the reviewer's "
          "own citation validator, identifiers checked for masking. Gate thresholds are starting points in "
          "`resources/fix_routes.yaml`."]
    return "\n".join(L) + "\n"
