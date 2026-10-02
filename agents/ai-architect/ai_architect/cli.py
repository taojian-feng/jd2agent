"""Command line for the agent's workflows.

    python -m ai_architect.cli design --scenario dealer-fault-diagnosis --cloud aws
    python -m ai_architect.cli loop   --scenario dealer-fault-diagnosis --cloud aws --max-rounds 2
    python -m ai_architect.cli review --run-id <run_id>
    python -m ai_architect.cli review-set --set prior-auth      (planted-defect recall for a rule pack)
"""
import argparse
import asyncio
import json

from ai_architect import catalog, workflows as wf


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ai_architect.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("design", "loop"):
        p = sub.add_parser(name)
        p.add_argument("--scenario", default="dealer-fault-diagnosis")
        p.add_argument("--cloud", choices=["azure", "aws", "gcp"], default="aws")
        p.add_argument("--title", default=None)
        if name == "loop":
            p.add_argument("--max-rounds", type=int, default=wf.MAX_REVISION_ROUNDS)
        p.add_argument("--rule-pack", action="append", default=None,
                       help="add a review rule pack (repeatable); default: the packs the scenario lists")
    p = sub.add_parser("review")
    p.add_argument("--run-id", required=True)
    p.add_argument("--rule-pack", action="append", default=None,
                   help="default: the packs the design run used (meta.json)")
    p = sub.add_parser("review-set")
    p.add_argument("--set", required=True)
    sub.add_parser("probe", help="check the model accepts every structured-output schema (a few cents)")
    a = ap.parse_args(argv)

    if a.cmd == "probe":
        from ai_architect import models as m
        from ai_architect.llm import get_llm
        llm, ok = get_llm(), {}
        for schema in (m.Requirements, m.ExecSummary, m.ComponentDesign, m.LLMOpsPlan, m.ADRList,
                       m.RuleVerdicts, m.RevisionPatch):
            try:
                llm.structured(schema, "Return a minimal valid example. Use empty lists where allowed.", "Example please.")
                ok[schema.__name__] = "ok"
            except Exception as e:
                ok[schema.__name__] = f"FAIL: {str(e)[:200]}"
            print(schema.__name__, ok[schema.__name__], flush=True)
        print("RESULT " + json.dumps(ok))
        return 0 if all(v == "ok" for v in ok.values()) else 1

    if a.cmd == "review-set":
        from ai_architect import defects
        spec = defects.load_set(a.set)
        cfg = {"rule_packs": spec.get("rule_packs", [])}
        found, decisions = {}, {}
        for vid, md in defects.variants(spec).items():
            run_id = wf.new_run_id(f"{a.set}-{vid}")
            wf.save_run(run_id, "design.md", md)
            out = asyncio.run(wf.architecture_review(md, run_id, cfg))
            found[vid] = sorted({f.rule_id for f in out["findings"]})
            decisions[vid] = out["readiness"].decision
            print(vid, decisions[vid], found[vid], flush=True)
        res = defects.score_set(spec, found, decisions)
        md = defects.report(res, spec.get("target_recall", 0.8))
        rid = wf.new_run_id(f"defect-set-{a.set}")
        wf.save_run(rid, "defects.md", md)
        print(md)
        print("RESULT " + json.dumps({"run_id": rid, **{k: v for k, v in res.items() if k != "rows"},
                                      "decisions": decisions}))
        return 0

    if a.cmd == "review":
        packs = a.rule_pack if a.rule_pack is not None else wf.load_meta(a.run_id).get("rule_packs", [])
        out = asyncio.run(wf.architecture_review(wf.load_run(a.run_id, "design.md"), a.run_id,
                                                 {"rule_packs": packs}))
        r = out["readiness"]
        result = {"run_id": out["run_id"], "rule_packs": packs, "decision": r.decision, "score": r.score,
                  "findings": [(f.severity, f.rule_id) for f in out["findings"]]}
    else:
        brief = catalog.scenario(a.scenario)
        title = a.title or a.scenario.replace("-", " ").title()
        packs = a.rule_pack if a.rule_pack is not None else catalog.packs_for_scenario(a.scenario)
        cfg = {"rule_packs": packs}
        if a.cmd == "design":
            out = asyncio.run(wf.solution_design(brief, a.cloud, title, cfg))
            result = {"run_id": out["run_id"], "pattern": out["fit"].ranked[0].id,
                      "traceability_passed": out["trace"].passed}
        else:
            out = asyncio.run(wf.design_review_revise(brief, a.cloud, title, cfg, max_rounds=a.max_rounds))
            result = {"run_id": out["run_id"], "rule_packs": packs, "history": out["history"]}
    print("RESULT " + json.dumps(result, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
