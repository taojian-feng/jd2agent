"""W3 trajectory evaluation as node functions + edges, and the accuracy check on the planted-failure set.

The same nodes run in LangGraph (graphs.py) or in run_sequential() below, so the logic is testable without
LangGraph installed. Nodes take (state, cfg); cfg may carry "llm" (defaults to get_llm()) and "concurrency".
"""
import asyncio
import inspect
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, TypedDict

from agent_evaluator import catalog
from agent_evaluator.llm import ValidationFailed, get_llm
from agent_evaluator.models import Diagnosis, Regression, RunResult, SuccessCheck, Trajectory
from agent_evaluator.tools import deterministic as d
from agent_evaluator.tools import llm_tools as lt

END = "__end__"


def _llm(cfg: dict):
    return cfg.get("llm") or get_llm()


def runs_dir() -> Path:
    return Path(os.environ.get("AGENT_EVALUATOR_RUNS", Path(__file__).resolve().parents[1] / "runs"))


def new_run_id(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40] or "eval"
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{slug}"


def save_run(run_id: str, name: str, content: str) -> Path:
    path = runs_dir() / run_id / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def load_run(run_id: str, name: str) -> str:
    if not re.match(r"^[0-9]{8}-[0-9]{6}-[a-z0-9-]+$", run_id) or name not in ("report.md", "accuracy.md",
                                                                                 "results.json"):
        raise FileNotFoundError(f"unknown run output: {run_id}/{name}")
    return (runs_dir() / run_id / name).read_text(encoding="utf-8")


async def diagnose_all(llm, items: list[tuple[Trajectory, SuccessCheck]], suite: dict,
                       concurrency: int = 4) -> dict[str, Diagnosis | str]:
    """classify_failures on every failing trace, a few at a time. A trace whose labels fail validation after
    retries gets the error text instead of a diagnosis (reported, never silently accepted)."""
    sem = asyncio.Semaphore(concurrency)

    async def one(t: Trajectory, c: SuccessCheck):
        async with sem:
            try:
                return t.trace_id, await asyncio.to_thread(lt.classify_failures, llm, t, c, suite)
            except ValidationFailed as e:
                return t.trace_id, f"labels rejected by the citation check: {e.problems}"

    return dict(await asyncio.gather(*(one(t, c) for t, c in items if not c.passed)))


def _run_result(run_id: str, suite: dict, trajs: list[Trajectory], checks: dict[str, SuccessCheck],
                diags: dict[str, Any]) -> RunResult:
    results = []
    for t in trajs:
        diag = diags.get(t.trace_id)
        r = d.trace_result(checks[t.trace_id], diag if isinstance(diag, Diagnosis) else None)
        if isinstance(diag, str):
            r.summary = diag
        results.append(r)
    versions = sorted({t.agent_version for t in trajs})
    return RunResult(run_id=run_id, suite_id=suite["suite_id"], agent_version=", ".join(versions), results=results)


# ------------------------------------------------------------------ W3 nodes
class EvalState(TypedDict, total=False):
    suite_id: str
    candidate_run: str
    baseline_run: str | None
    run_id: str
    suite: dict
    trajectories: dict[str, list[Trajectory]]
    checks: dict[str, dict[str, SuccessCheck]]
    diagnoses: dict[str, dict[str, Any]]
    runs: dict[str, RunResult]
    regression: Regression
    report: str


def load_traces(state: EvalState, cfg: dict) -> dict:
    names = [state["candidate_run"]] + ([state["baseline_run"]] if state.get("baseline_run") else [])
    trajs = {n: [d.load_trajectory(t) for t in catalog.run_traces(n)] for n in names}
    return {"suite": catalog.suite(state["suite_id"]), "trajectories": trajs,
            "run_id": state.get("run_id") or new_run_id(f"{state['suite_id']}-{state['candidate_run']}")}


def check_success(state: EvalState, cfg: dict) -> dict:
    return {"checks": {n: {t.trace_id: d.check_task_success(t, state["suite"]) for t in ts}
                       for n, ts in state["trajectories"].items()}}


async def classify(state: EvalState, cfg: dict) -> dict:
    llm, out = _llm(cfg), {}
    for n, ts in state["trajectories"].items():
        items = [(t, state["checks"][n][t.trace_id]) for t in ts]
        out[n] = await diagnose_all(llm, items, state["suite"], cfg.get("concurrency", 4))
    return {"diagnoses": out}


def compare(state: EvalState, cfg: dict) -> dict:
    runs = {n: _run_result(n, state["suite"], ts, state["checks"][n], state["diagnoses"][n])
            for n, ts in state["trajectories"].items()}
    base = runs.get(state.get("baseline_run") or "")
    return {"runs": runs, "regression": d.compare_runs(runs[state["candidate_run"]], base)}


def report(state: EvalState, cfg: dict) -> dict:
    cand, base = state["runs"][state["candidate_run"]], state["runs"].get(state.get("baseline_run") or "")
    md = d.write_eval_report(state["regression"], cand, base)
    save_run(state["run_id"], "report.md", md)
    save_run(state["run_id"], "results.json", json.dumps(
        {"regression": state["regression"].model_dump(),
         "runs": {n: r.model_dump() for n, r in state["runs"].items()}}, indent=1))
    return {"report": md}


W3_NODES: dict[str, Callable] = {"load_traces": load_traces, "check_success": check_success,
                                 "classify": classify, "compare": compare, "report": report}
W3_EDGES: dict[str, Any] = {"load_traces": "check_success", "check_success": "classify",
                            "classify": "compare", "compare": "report", "report": END}


async def run_sequential(nodes: dict[str, Callable], edges: dict[str, Any], start: str,
                         state: dict, cfg: dict | None = None, max_steps: int = 50) -> dict:
    cfg = cfg or {}
    state = dict(state)
    current, trace = start, []
    for _ in range(max_steps):
        out = nodes[current](state, cfg)
        if inspect.isawaitable(out):
            out = await out
        state.update(out)
        trace.append(current)
        nxt = edges[current]
        current = nxt(state) if callable(nxt) else nxt
        if current == END:
            state["_trace"] = trace
            return state
    raise RuntimeError(f"workflow exceeded {max_steps} steps: {trace}")


async def trajectory_eval(suite_id: str, candidate_run: str, baseline_run: str | None = None,
                          cfg: dict | None = None) -> dict:
    """W3 end to end without LangGraph."""
    return await run_sequential(W3_NODES, W3_EDGES, "load_traces",
                                {"suite_id": suite_id, "candidate_run": candidate_run, "baseline_run": baseline_run},
                                cfg)


# ------------------------------------------------------------------ accuracy on the planted-failure set
def score_accuracy(labels: list[dict], checks: dict[str, SuccessCheck], diags: dict[str, Any]) -> dict:
    """Compare the evaluator with the planted labels. Pure function: unit-tested with scripted diagnoses."""
    rows, n_fail = [], 0
    exact = acceptable = recall = valid = 0
    clean_false = check_right = 0
    for lab in labels:
        c, diag = checks[lab["trace_id"]], diags.get(lab["trace_id"])
        check_right += c.passed == lab["expected_pass"]
        if lab["expected_pass"]:
            clean_false += not c.passed
            rows.append({**lab, "check_passed": c.passed, "predicted": None, "labels": [], "note": ""})
            continue
        n_fail += 1
        ok = isinstance(diag, Diagnosis)
        valid += ok
        pred = diag.root_cause if ok else None
        names = [l.label for l in diag.labels] if ok else []
        exact += pred == lab["root_cause"]
        acceptable += pred in [lab["root_cause"], *lab.get("also_acceptable", [])]
        recall += lab["root_cause"] in names
        rows.append({**lab, "check_passed": c.passed, "predicted": pred, "labels": names,
                     "note": "" if ok else str(diag)})
    n = len(labels)
    return {
        "traces": n, "planted": n_fail, "clean": n - n_fail,
        "success_check_accuracy": round(check_right / n, 3),
        "root_cause_accuracy": round(exact / n_fail, 3) if n_fail else None,
        "root_cause_accuracy_incl_acceptable": round(acceptable / n_fail, 3) if n_fail else None,
        "planted_label_recall": round(recall / n_fail, 3) if n_fail else None,
        "citation_validity": round(valid / n_fail, 3) if n_fail else None,
        "clean_trace_false_failures": clean_false,
        "rows": rows,
    }


GATES = {"success_check_accuracy": ("==", 1.0), "root_cause_accuracy": (">=", 0.85),
         "citation_validity": ("==", 1.0), "clean_trace_false_failures": ("==", 0)}


def gate_results(m: dict) -> dict[str, bool]:
    return {k: (m[k] == v if op == "==" else m[k] >= v) for k, (op, v) in GATES.items()}


def accuracy_report(m: dict, model: str) -> str:
    g = gate_results(m)
    out = ["# Evaluator accuracy on planted failures", "",
           f"{m['traces']} synthetic traces: {m['planted']} with one planted root cause, {m['clean']} clean. "
           f"Model: `{model}`.", "", "| Metric | Result | Target | Pass |", "|---|---|---|---|"]
    for k, (op, v) in GATES.items():
        val = m[k]
        shown = f"{val:.0%}" if isinstance(val, float) else str(val)
        target = f"{op} {v:.0%}" if isinstance(v, float) else f"{op} {v}"
        out.append(f"| {k.replace('_', ' ')} | {shown} | {target} | {'yes' if g[k] else 'NO'} |")
    out += [f"| root cause incl. acceptable alternatives | {m['root_cause_accuracy_incl_acceptable']:.0%} | | |",
            f"| planted label anywhere in labels | {m['planted_label_recall']:.0%} | | |",
            "", "| Trace | Task | Planted | Predicted | All labels | Note |", "|---|---|---|---|---|---|"]
    for r in m["rows"]:
        mark = "" if r["root_cause"] is None or r["predicted"] == r["root_cause"] else " ✗"
        out.append(f"| {r['trace_id']} | {r['task_id']} | {r['root_cause'] or 'clean'} | "
                   f"{(r['predicted'] or ('pass' if r['check_passed'] else 'fail'))}{mark} | "
                   f"{', '.join(dict.fromkeys(r['labels']))} | {r['note'][:120]} |")
    return "\n".join(out) + "\n"


async def evaluator_accuracy(run: str = "eval-set", cfg: dict | None = None) -> dict:
    cfg = cfg or {}
    lf = catalog.labels_file(run)
    labels, suite = lf["traces"], catalog.suite(lf["suite_id"])
    trajs = {t.trace_id: t for t in (d.load_trajectory(x) for x in catalog.run_traces(run))}
    checks = {tid: d.check_task_success(t, suite) for tid, t in trajs.items()}
    diags = await diagnose_all(_llm(cfg), [(trajs[tid], checks[tid]) for tid in trajs], suite,
                               cfg.get("concurrency", 4))
    m = score_accuracy(labels, checks, diags)
    run_id = new_run_id(f"accuracy-{run}")
    md = accuracy_report(m, cfg.get("model_name", "configured model"))
    save_run(run_id, "accuracy.md", md)
    save_run(run_id, "results.json", json.dumps({k: v for k, v in m.items()}, indent=1, default=str))
    return {"run_id": run_id, "metrics": m, "gates": gate_results(m), "report": md}
