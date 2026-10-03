"""Command line. The last output line is "RESULT <json>" for the job runner.

    python -m prior_auth_reviewer.cli retrieval-eval            (no model: retrieval and context quality)
    python -m prior_auth_reviewer.cli run-suite --name pa-live --faults transient [--no-critic] [--export]
    python -m prior_auth_reviewer.cli review --case PA-009
    python -m prior_auth_reviewer.cli resume --case PA-003 --addendum "Back pain for 9 weeks. ..."
    python -m prior_auth_reviewer.cli probe
"""
import argparse
import asyncio
import json
import re
from pathlib import Path

import yaml

from prior_auth_reviewer import context as cx
from prior_auth_reviewer import retrieval as rt
from prior_auth_reviewer import workflows as wf
from prior_auth_reviewer.systems import DATA, TRANSIENT_FAULTS, HealthPlanSystems, load_cases

EVALUATOR_TRACES = Path(__file__).resolve().parents[2] / "agent-evaluator" / "traces"


def retrieval_and_context() -> dict:
    systems = HealthPlanSystems()
    lib = wf.library_from(systems)
    queries = yaml.safe_load((DATA / "retrieval_eval.yaml").read_text())["queries"]
    retrieval = rt.evaluate_retrieval(lib, queries)
    policy = lib.docs["MP-117"]
    kept = total = masked = dropped = sents = 0
    for c in load_cases().values():
        ctx = cx.assemble(c["notes"], policy)
        k, t = cx.gold_retention(ctx, c["gold"])
        kept, total, masked = kept + k, total + t, masked + ctx.masked_identifiers
        dropped, sents = dropped + len(ctx.dropped), sents + len(ctx.kept) + len(ctx.dropped)
    return {"retrieval": retrieval, "context": {"gold_phrases_kept": kept, "gold_phrases": total,
                                                "context_recall": round(kept / total, 3),
                                                "sentences_dropped": dropped, "sentences": sents,
                                                "identifiers_masked": masked}}


def table(m: dict) -> str:
    out = ["| Stage | Policy recall@1 | Policy MRR | Clause recall@1 | Clause recall@3 | Clause MRR |",
           "|---|---|---|---|---|---|"]
    for stage, r in m["retrieval"].items():
        p, c = r["policy"], r["clause"]
        out.append(f"| {stage} | {p['recall@1']:.0%} | {p['mrr']:.2f} | {c['recall@1']:.0%} | {c['recall@3']:.0%} | "
                   f"{c['mrr']:.2f} |")
    cxm = m["context"]
    out.append(f"\nContext assembly: {cxm['gold_phrases_kept']}/{cxm['gold_phrases']} gold evidence phrases kept; "
               f"{cxm['sentences_dropped']} of {cxm['sentences']} note sentences dropped; "
               f"{cxm['identifiers_masked']} identifiers masked.")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="prior_auth_reviewer.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("retrieval-eval")
    p = sub.add_parser("run-suite")
    p.add_argument("--name", required=True)
    p.add_argument("--no-critic", action="store_true")
    p.add_argument("--faults", choices=["none", "transient"], default="transient")
    p.add_argument("--export", action="store_true", help="write traces to agent-evaluator/traces/<name>")
    p = sub.add_parser("review")
    p.add_argument("--case", required=True)
    p.add_argument("--no-critic", action="store_true")
    p = sub.add_parser("resume")
    p.add_argument("--case", required=True)
    p.add_argument("--addendum", required=True)
    sub.add_parser("probe")
    a = ap.parse_args(argv)

    if a.cmd == "retrieval-eval":
        m = retrieval_and_context()
        print(table(m))
        print("RESULT " + json.dumps(m))
        return 0

    if a.cmd == "probe":
        from prior_auth_reviewer.llm import get_llm
        from prior_auth_reviewer.models import Critique, Proposal
        ok = {}
        for schema in (Proposal, Critique):
            try:
                get_llm().structured(schema, "Return a minimal valid example.", "Example please.")
                ok[schema.__name__] = "ok"
            except Exception as e:  # noqa: BLE001
                ok[schema.__name__] = f"FAIL: {str(e)[:200]}"
        print("RESULT " + json.dumps(ok))
        return 0 if all(v == "ok" for v in ok.values()) else 1

    if a.cmd == "run-suite":
        if not re.match(r"^[a-z0-9][a-z0-9-]{0,60}$", a.name):
            raise SystemExit("--name must be lowercase letters, digits and dashes")
        out = asyncio.run(wf.run_suite(a.name, critic=not a.no_critic,
                                       faults=TRANSIENT_FAULTS if a.faults == "transient" else None))
        run_dir = wf.runs_dir() / "suites" / a.name
        wf.write_traces(out, run_dir / "traces")
        if a.export:
            wf.write_traces(out, EVALUATOR_TRACES / a.name)
        for r in out["rows"]:
            print(f"{r['case_id']} {r['outcome']:<13} expected {r['expected']:<13} "
                  f"{'ok' if r['correct'] else 'WRONG'}  {r['reason']} {r['error']}")
        summary = {k: out[k] for k in ("run_name", "critic", "accuracy", "llm_calls", "unsafe_approvals")}
        summary["wrong"] = [r["case_id"] for r in out["rows"] if not r["correct"]]
        (run_dir / "summary.json").write_text(json.dumps({**summary, "rows": out["rows"]}, indent=1))
        print("RESULT " + json.dumps(summary))
        return 0

    systems = HealthPlanSystems()
    memory = a.cmd == "resume"
    if memory:
        systems.add_addendum(a.case, a.addendum)
    out = asyncio.run(wf.run_suite(f"{a.cmd}-{a.case.lower()}", [a.case], critic=not getattr(a, "no_critic", False),
                                   systems=systems, memory=memory))
    r = out["results"][a.case]
    print(out["traces"][a.case].dumps())
    print("RESULT " + json.dumps({"case": a.case, "outcome": r.outcome, "reason": r.reason,
                                  "findings": [(f.criterion_id, f.finding, f.sentence_ids) for f in r.findings]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
