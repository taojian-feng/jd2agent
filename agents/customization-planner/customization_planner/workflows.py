"""W3 end to end: plan from recorded runs, write the outputs, optionally draft the partner memo."""
import json
from datetime import datetime

import yaml

from customization_planner import catalog, planner, report
from customization_planner.models import Plan

LIVE_RUNS = ["pa-live-nocritic", "pa-live-full", "pa-live-full-2", "pa-live-full-3", "pa-live-full-4"]


def run_plan(run_ids: list[str], suite_id: str = "prior-auth", plan_id: str | None = None,
             write: bool = True) -> tuple[Plan, dict[str, str]]:
    plan_id = plan_id or datetime.now().strftime("%Y%m%d-%H%M%S") + "-plan"
    traces = {r: catalog.run_traces(r) for r in run_ids}
    plan = planner.make_plan(plan_id, run_ids, catalog.suite(suite_id), traces, catalog.routes())
    files = {
        "plan.md": report.write_plan(plan),
        "sft.jsonl": planner.jsonl(plan.sft),
        "dpo.jsonl": planner.jsonl(plan.pairs),
        "recipe.yaml": yaml.safe_dump(planner.recipe(plan), sort_keys=False, width=110),
        "stats.json": json.dumps({"verdict": plan.verdict, **plan.stats,
                                  "gates": [g.model_dump() for g in plan.gates], "split": plan.split}, indent=1),
    }
    if write:
        out = catalog.plan_dir(plan_id)
        out.mkdir(parents=True, exist_ok=True)
        for name, content in files.items():
            (out / name).write_text(content, encoding="utf-8")
    return plan, files


def load_output(plan_id: str, name: str) -> str:
    if name not in ("plan.md", "sft.jsonl", "dpo.jsonl", "recipe.yaml", "stats.json", "memo.md"):
        raise ValueError(f"unknown output {name!r}")
    return (catalog.plan_dir(plan_id) / name).read_text(encoding="utf-8")
