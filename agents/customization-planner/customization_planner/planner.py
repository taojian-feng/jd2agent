"""W3: grade traces, route failures, build checked training data, and decide whether post-training is ready.

Everything here is code. A training target is used only where code can verify it:
- the run passed the evaluator's check (outcome derived from the terminal action, never from the agent's claim);
- the task's expected outcome pins the criterion down. An approval needs every criterion met or waived, so on an
  approve task a criterion finding is verified when every passing run agrees on it. On other tasks one criterion's
  finding does not decide the outcome, so a changed finding there is counted as unverifiable and not trained on.
"""
import hashlib
import json
from collections import Counter, defaultdict

from agent_evaluator.tools import deterministic as ev

from customization_planner import prior_auth as pa
from customization_planner.models import (DecisionChange, DecisionRecord, FailureRoute, Gate, Plan, PreferencePair,
                                          SFTExample)


# ------------------------------------------------------------------ grade
def grade(run_ids: list[str], suite: dict, traces_by_run: dict[str, list[dict]]) -> list[tuple[DecisionRecord, object]]:
    """Every trace -> (decision record, trajectory), graded by the evaluator's own success check."""
    out = []
    for run_id in run_ids:
        for t in traces_by_run[run_id]:
            traj = ev.load_trajectory(t)
            out.append((pa.decision_record(traj, ev.check_task_success(traj, suite)), traj))
    return out


# ------------------------------------------------------------------ verified answers
def verified_findings(records: list[DecisionRecord]) -> dict[tuple[str, str], str]:
    """(task, criterion) -> the finding every passing run on an approve task agrees on."""
    seen: dict[tuple[str, str], set[str]] = defaultdict(set)
    for r in records:
        if r.passed and r.expected_outcome == "approve":
            for f in r.final:
                seen[(r.task_id, f.criterion_id)].add(f.finding)
    return {k: next(iter(v)) for k, v in seen.items() if len(v) == 1 and next(iter(v)) in ("met", "waived")}


def _evidence_in_context(rec: DecisionRecord, criterion: str, verified_by: list[DecisionRecord]) -> bool:
    """The sentences the verified answer cites were in this run's context (so the model had the evidence)."""
    cited = {s for r in verified_by for f in r.final if f.criterion_id == criterion for s in f.sentence_ids}
    return bool(cited) and all(f"{sid}:" in rec.prompt for sid in cited)


def decision_changes(records: list[DecisionRecord], verified: dict) -> tuple[list[DecisionChange], int]:
    """Model decisions that differ from the verified answer, plus a count of differences code cannot verify."""
    passing = defaultdict(list)
    for r in records:
        if r.passed:
            passing[r.task_id].append(r)
    changes, unverifiable = [], 0
    for r in records:
        candidates = [("first_pass", r.first_pass)] if r.first_pass != r.final else []
        if not r.passed:
            candidates.append(("failing_run", r.final))
        for source, findings in candidates:
            for f in findings:
                key = (r.task_id, f.criterion_id)
                if key in verified:
                    if f.finding != verified[key]:
                        ok = _evidence_in_context(r, f.criterion_id, passing[r.task_id])
                        changes.append(DecisionChange(task_id=r.task_id, criterion_id=f.criterion_id, run_id=r.run_id,
                                                      source=source, got=f.finding, verified=verified[key],
                                                      evidence_in_context=ok,
                                                      route="model_judgment" if ok else "retrieval_context"))
                elif source == "first_pass" and f.finding != _final(r, f.criterion_id):
                    unverifiable += 1
    return changes, unverifiable


def _final(r: DecisionRecord, criterion: str) -> str | None:
    return next((f.finding for f in r.final if f.criterion_id == criterion), None)


# ------------------------------------------------------------------ route
def route_failures(records: list[DecisionRecord], changes: list[DecisionChange], routes_cfg: dict) -> list[FailureRoute]:
    """One route per failing run: the earliest route (in fix order) among its symptoms and decision changes."""
    by_label: dict[str, list[dict]] = defaultdict(list)
    for r in routes_cfg["routes"]:
        for label in r["labels"]:
            by_label[label].append(r)
    by_id = {r["id"]: r for r in routes_cfg["routes"]}
    out = []
    for rec in records:
        if rec.passed:
            continue
        found = [c.route for c in changes if c.run_id == rec.run_id and c.task_id == rec.task_id
                 and c.source == "failing_run"]
        for label in rec.symptoms:
            if label in ("wrong_final_answer", "ungrounded_claim") and found:
                continue  # explained by the decision change found above
            options = [r for r in by_label.get(label, []) if "when" not in r] or by_label.get(label, [])
            if options:
                found.append(min(options, key=lambda r: r["order"])["id"])
        if rec.safety_failure:
            found.append("code_guardrail")  # an approval that should have gone to a person: block it in code
        if not found:
            found = ["model_judgment"]
        rid = min(found, key=lambda x: by_id[x]["order"])
        label = next((s for s in rec.symptoms if rid in [r["id"] for r in by_label.get(s, [])]),
                     "unsafe_approval" if rid == "code_guardrail" else
                     rec.symptoms[0] if rec.symptoms else "wrong_final_answer")
        out.append(FailureRoute(run_id=rec.run_id, task_id=rec.task_id, label=label, route=rid,
                                fix=" ".join(by_id[rid]["fix"].split())))
    return out


# ------------------------------------------------------------------ build data
def _id(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:10]


def _tuple(findings) -> tuple:
    return tuple((f.criterion_id, f.finding) for f in findings)


def build_sft(graded, problems: Counter) -> tuple[list[SFTExample], int]:
    """Final proposals of passing runs. Same task with different finding sets across runs -> conflict, dropped."""
    by_task: dict[str, list] = defaultdict(list)
    for rec, traj in graded:
        if rec.passed and rec.final:
            by_task[rec.task_id].append((rec, traj))
    out, raw = [], 0
    for task, items in sorted(by_task.items()):
        raw += len(items)
        if len({_tuple(r.final) for r, _ in items}) > 1:
            problems["sft: conflicting targets across passing runs (task dropped)"] += 1
            continue
        rec, traj = items[0]
        text, issues = pa.completion(rec.final, rec.red_flag, traj)
        if not _usable(rec, text, issues, problems, "sft"):
            continue
        out.append(SFTExample(id=_id("sft", task), task_id=task, expected_outcome=rec.expected_outcome,
                              runs=sorted(r.run_id for r, _ in items), system=pa.SYSTEM, prompt=rec.prompt,
                              completion=text))
    return out, raw


def build_pairs(graded, changes: list[DecisionChange], problems: Counter) -> tuple[list[PreferencePair], int]:
    """chosen = a verified final proposal; rejected = the first pass the critic corrected, or a failing run's final."""
    passing = defaultdict(list)
    for rec, traj in graded:
        if rec.passed and rec.final:
            passing[rec.task_id].append((rec, traj))
    keyed = {(c.run_id, c.task_id, c.source) for c in changes if c.route == "model_judgment"}
    out, raw, seen = [], 0, set()
    for rec, traj in graded:
        for source in ("first_pass", "failing_run"):
            if (rec.run_id, rec.task_id, source) not in keyed:
                continue
            raw += 1
            rejected_f, rejected_flag = ((rec.first_pass, rec.first_red_flag) if source == "first_pass"
                                         else (rec.final, rec.red_flag))
            if source == "first_pass" and rec.passed:
                chosen_rec, chosen_traj = rec, traj
            else:
                if not passing[rec.task_id]:
                    problems["pairs: no passing run to take the chosen answer from"] += 1
                    continue
                chosen_rec, chosen_traj = sorted(passing[rec.task_id], key=lambda x: x[0].run_id)[0]
            if chosen_rec.prompt != rec.prompt:
                problems["pairs: chosen and rejected have different prompts"] += 1
                continue
            diff = [a[0] for a, b in zip(_tuple(chosen_rec.final), _tuple(rejected_f)) if a != b]
            key = (rec.task_id, _tuple(chosen_rec.final), _tuple(rejected_f))
            if key in seen:
                problems["pairs: duplicate of a pair already kept"] += 1
                continue
            chosen, c_issues = pa.completion(chosen_rec.final, chosen_rec.red_flag, chosen_traj)
            rejected, r_issues = pa.completion(rejected_f, rejected_flag, traj)
            if not _usable(rec, chosen, c_issues, problems, "pairs") or not _usable(rec, rejected, r_issues,
                                                                                    problems, "pairs"):
                continue
            seen.add(key)
            out.append(PreferencePair(id=_id("dpo", rec.run_id, rec.task_id, source), task_id=rec.task_id,
                                      criteria=diff, source=source, runs=sorted({rec.run_id, chosen_rec.run_id}),
                                      system=pa.SYSTEM, prompt=rec.prompt, chosen=chosen, rejected=rejected))
    return out, raw


def _usable(rec: DecisionRecord, text: str, issues: list[str], problems: Counter, kind: str) -> bool:
    if issues:
        problems[f"{kind}: target fails the reviewer's citation check"] += 1
        return False
    if not rec.context_matches_trace:
        problems[f"{kind}: rebuilt context differs from the traced one"] += 1
        return False
    if pa.unmasked_identifiers(rec.prompt + text):
        problems[f"{kind}: unmasked identifier"] += 1
        return False
    return True


# ------------------------------------------------------------------ split and gates
def split_tasks(records: list[DecisionRecord], n_heldout: int) -> dict[str, list[str]]:
    """Hold out one task per expected outcome (stable hash order), then more until n_heldout. No task in both."""
    by_outcome: dict[str, list[str]] = defaultdict(list)
    for r in records:
        if r.final and r.task_id not in by_outcome[r.expected_outcome]:
            by_outcome[r.expected_outcome].append(r.task_id)
    order = lambda t: hashlib.sha1(t.encode()).hexdigest()  # noqa: E731
    heldout = [sorted(ts, key=order)[0] for _, ts in sorted(by_outcome.items())]
    rest = sorted({t for ts in by_outcome.values() for t in ts} - set(heldout), key=order)
    heldout += rest[:max(0, n_heldout - len(heldout))]
    tasks = sorted({t for ts in by_outcome.values() for t in ts})
    return {"train": [t for t in tasks if t not in heldout], "eval": sorted(heldout)}


def gates(sft: list[SFTExample], pairs: list[PreferencePair], split: dict, cfg: dict) -> list[Gate]:
    train = set(split["train"])
    sft_t = [e for e in sft if e.task_id in train]
    pairs_t = [p for p in pairs if p.task_id in train]
    shares = Counter(e.expected_outcome for e in sft_t)
    top = max(shares.values()) / len(sft_t) if sft_t else 1.0
    outcomes = {e.expected_outcome for e in sft}
    held = {e.expected_outcome for e in sft if e.task_id in split["eval"]}
    g = [
        Gate(name="preference pairs (train)", target=f">= {cfg['min_preference_pairs']}", actual=str(len(pairs_t)),
             passed=len(pairs_t) >= cfg["min_preference_pairs"]),
        Gate(name="SFT examples (train)", target=f">= {cfg['min_sft_examples']}", actual=str(len(sft_t)),
             passed=len(sft_t) >= cfg["min_sft_examples"]),
        Gate(name="distinct tasks behind the pairs", target=f">= {cfg['min_distinct_tasks']}",
             actual=str(len({p.task_id for p in pairs_t})),
             passed=len({p.task_id for p in pairs_t}) >= cfg["min_distinct_tasks"]),
        Gate(name="held-out tasks", target=f">= {cfg['min_heldout_tasks']}", actual=str(len(split["eval"])),
             passed=len(split["eval"]) >= cfg["min_heldout_tasks"]),
        Gate(name="largest expected-outcome share in SFT", target=f"<= {cfg['max_outcome_share']:.0%}",
             actual=f"{top:.0%}", passed=top <= cfg["max_outcome_share"]),
        Gate(name="no task in both train and eval", target="0", actual=str(len(train & set(split["eval"]))),
             passed=not (train & set(split["eval"]))),
    ]
    if cfg.get("heldout_covers_every_outcome"):
        missing = sorted(outcomes - held)
        g.append(Gate(name="every expected outcome held out", target="none missing",
                      actual=", ".join(missing) or "none missing", passed=not missing))
    return g


# ------------------------------------------------------------------ plan
def make_plan(plan_id: str, run_ids: list[str], suite: dict, traces_by_run: dict, routes_cfg: dict) -> Plan:
    graded = grade(run_ids, suite, traces_by_run)
    records = [r for r, _ in graded]
    verified = verified_findings(records)
    changes, unverifiable = decision_changes(records, verified)
    routes = route_failures(records, changes, routes_cfg)
    problems: Counter = Counter()
    sft, sft_raw = build_sft(graded, problems)
    pairs, pairs_raw = build_pairs(graded, changes, problems)
    split = split_tasks(records, routes_cfg["readiness"]["min_heldout_tasks"])
    g = gates(sft, pairs, split, routes_cfg["readiness"])

    calls = defaultdict(lambda: [0, 0])
    for r in records:
        calls[r.run_id][0] += r.model_calls
        calls[r.run_id][1] += 1
    stats = {
        "traces": len(records),
        "passed": sum(r.passed for r in records),
        "safety_failures": sum(r.safety_failure for r in records),
        "runs": {run: {"passed": sum(r.passed for r in records if r.run_id == run),
                       "traces": calls[run][1], "model_calls": calls[run][0]} for run in run_ids},
        "traces_with_a_proposal": sum(bool(r.final) for r in records),
        "context_rebuilt_matches_trace": sum(r.context_matches_trace for r in records if r.final),
        "critic_disputes": sum(bool(r.disputed) for r in records),
        "self_corrections": sum(r.first_pass != r.final for r in records),
        "verified_criteria": len(verified),
        "decision_changes": len(changes),
        "decision_changes_by_source": dict(Counter(c.source for c in changes)),
        "decision_changes_by_criterion": dict(Counter(f"{c.task_id} {c.criterion_id} {c.got}->{c.verified}"
                                                      for c in changes)),
        "unverifiable_changes": unverifiable,
        "routes": dict(Counter(r.route for r in routes)),
        "sft_raw": sft_raw, "sft_unique": len(sft),
        "pairs_raw": pairs_raw, "pairs_unique": len(pairs),
        "dropped": dict(problems),
    }
    hard = [r for r in routes if not _trainable(r.route, routes_cfg)]
    verdict = "fix_first" if hard else ("ready" if all(x.passed for x in g) else "not_ready")
    plan = Plan(plan_id=plan_id, runs=run_ids, traces=len(records), passed=stats["passed"], routes=routes,
                changes=changes, unverifiable_changes=unverifiable, sft=sft, pairs=pairs, stats=stats, split=split,
                gates=g, verdict=verdict, recommendation=[])
    plan.recommendation = recommend(plan, routes_cfg)
    return plan


def _trainable(route: str, cfg: dict) -> bool:
    return next(r["trainable"] for r in cfg["routes"] if r["id"] == route)


def recommend(plan: Plan, cfg: dict) -> list[str]:
    s, out = plan.stats, []
    hard = Counter(r.route for r in plan.routes if not _trainable(r.route, cfg))
    if hard:
        out.append("Fix in code first: " + ", ".join(f"{n} failing run(s) routed to {k}" for k, n in hard.items())
                   + ". A model cannot be trained out of a failure that code can prevent.")
    mj = [c for c in plan.changes if c.route == "model_judgment"]
    if mj:
        tasks = sorted({c.task_id for c in mj})
        out.append(f"{len(mj)} model decisions differ from the verified answer with the evidence in context "
                   f"({', '.join(sorted(set(s['decision_changes_by_criterion'])))}), on {len(tasks)} task(s). "
                   "This is a judgment error, the kind post-training can address.")
    failed = [g for g in plan.gates if not g.passed]
    if plan.verdict == "ready":
        out.append("Readiness gates pass: train with the recipe, then run the regression gate before any release.")
    elif failed:
        out.append("Not ready to train: " + "; ".join(f"{g.name} {g.actual} (needs {g.target})" for g in failed) + ".")
        out.append(f"The traces give {s['pairs_unique']} unique preference pair(s) and {s['sft_unique']} SFT "
                   "example(s). Keep the workflow fix in place and collect more verified cases before training.")
    return out


def recipe(plan: Plan) -> dict:
    """Framework-neutral training recipe. Hyperparameters are starting points, not tuned results."""
    return {
        "status": "ready" if plan.verdict == "ready" else f"blocked ({plan.verdict})",
        "blocked_by": [g.name for g in plan.gates if not g.passed],
        "base_model": "set by the person: an open-weight model the partner serves (closed hosted models need the "
                      "provider's fine-tuning API)",
        "stages": [
            {"method": "sft", "data": "sft.jsonl", "adapter": {"type": "lora", "r": 16, "alpha": 32, "dropout": 0.05},
             "epochs": 2, "learning_rate": 1e-4, "note": "optional warm start; skip if the base model already "
                                                        "follows the output schema"},
            {"method": "dpo", "data": "dpo.jsonl", "adapter": {"type": "lora", "r": 16, "alpha": 32, "dropout": 0.05},
             "beta": 0.1, "epochs": 2, "learning_rate": 5e-6},
        ],
        "split": plan.split,
        "regression_gate": {
            "how": "run the agent with the tuned proposer on the eval tasks, export traces, then "
                   "agent_evaluator.cli eval --candidate <tuned run> --baseline <current run>",
            "pass_when": ["evaluator decision is go", "no safety failure on any task",
                          "model calls per case at or below the current agent's (the point of tuning is to drop the "
                          "self-correction round without losing accuracy)"],
        },
    }


def jsonl(rows) -> str:
    return "".join(json.dumps(r.model_dump(), ensure_ascii=False) + "\n" for r in rows)
