"""Loads the evaluator's knowledge files (taxonomy, task suites, scenarios) and recorded traces."""
import json
import os
import re
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
RESOURCES = Path(os.environ.get("AGENT_EVALUATOR_RESOURCES", ROOT / "resources"))
TRACES = Path(os.environ.get("AGENT_EVALUATOR_TRACES", ROOT / "traces"))
SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")


@lru_cache
def load(name: str) -> dict:
    return yaml.safe_load((RESOURCES / name).read_text(encoding="utf-8"))


def text(name: str) -> str:
    return (RESOURCES / name).read_text(encoding="utf-8")


def taxonomy() -> dict:
    return load("failure_taxonomy.yaml")


def label_ids() -> list[str]:
    return [l["id"] for l in taxonomy()["labels"]]


def _safe(base: Path, name: str, suffix: str = "") -> Path:
    if not SLUG.match(name):
        raise FileNotFoundError(f"bad name: {name!r}")
    path = (base / f"{name}{suffix}").resolve()
    if path.parent != base.resolve() or not path.exists():
        raise FileNotFoundError(f"not found: {name}")
    return path


def suite(suite_id: str) -> dict:
    return yaml.safe_load(_safe(RESOURCES / "task_suites", suite_id, ".yaml").read_text(encoding="utf-8"))


def scenario(scenario_id: str) -> str:
    return _safe(RESOURCES / "scenarios", scenario_id, ".md").read_text(encoding="utf-8")


def run_traces(run_id: str) -> list[dict]:
    """All traces of a recorded run: traces/<run_id>/*.json, sorted by file name."""
    d = _safe(TRACES, run_id)
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.glob("*.json"))]


def labels_file(run_id: str = "eval-set") -> dict:
    """Planted labels for a labeled run: {suite_id, traces: [{trace_id, task_id, expected_pass, root_cause, ...}]}."""
    return yaml.safe_load((_safe(TRACES, run_id) / "labels.yaml").read_text(encoding="utf-8"))


def eval_labels(run_id: str = "eval-set") -> list[dict]:
    return labels_file(run_id)["traces"]


def list_runs() -> list[str]:
    return sorted(p.name for p in TRACES.iterdir() if p.is_dir()) if TRACES.exists() else []
