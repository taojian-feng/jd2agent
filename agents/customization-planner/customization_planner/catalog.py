"""Where the planner reads from: its own resources, and the evaluator's traces and task suites."""
import os
import re
from pathlib import Path

import yaml
from agent_evaluator import catalog as evaluator_catalog

ROOT = Path(__file__).resolve().parents[1]
RESOURCES = Path(os.environ.get("CUSTOMIZATION_PLANNER_RESOURCES", ROOT / "resources"))
RUNS = Path(os.environ.get("CUSTOMIZATION_PLANNER_RUNS", ROOT / "runs"))
SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")


def text(name: str) -> str:
    return (RESOURCES / name).read_text(encoding="utf-8")


def routes() -> dict:
    return yaml.safe_load(text("fix_routes.yaml"))


def suite(suite_id: str) -> dict:
    return evaluator_catalog.suite(suite_id)


def run_traces(run_id: str) -> list[dict]:
    return evaluator_catalog.run_traces(run_id)


def list_runs() -> list[str]:
    return evaluator_catalog.list_runs()


def plan_dir(plan_id: str) -> Path:
    if not SLUG.match(plan_id):
        raise ValueError(f"bad plan id {plan_id!r}")
    return RUNS / plan_id
