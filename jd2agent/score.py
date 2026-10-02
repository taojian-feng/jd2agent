"""Phase 1b — Score: rank a role's tasks by how well an agent can take them on.

Usage:
    python -m jd2agent.score roles/<slug>/role_spec.yaml
"""
import sys
from pathlib import Path

import yaml

# Checkability weighs most: an agent whose output can't be verified isn't enterprise-ready.
WEIGHTS = {
    "repeatability": 0.20,
    "input_availability": 0.20,
    "checkability": 0.30,
    "demo_value": 0.15,
    "product_reuse": 0.15,
}
BUILD, ASSIST = 3.8, 3.0  # >= BUILD: agent does it; >= ASSIST: agent drafts, human finishes; else human-owned


def score(task: dict) -> float:
    s = task["scores"]
    missing = set(WEIGHTS) - set(s)
    if missing:
        raise ValueError(f"{task['id']} missing scores: {sorted(missing)}")
    return round(sum(WEIGHTS[k] * s[k] for k in WEIGHTS), 2)


def verdict(value: float, checkability: int) -> str:
    if value >= BUILD and checkability >= 3:
        return "BUILD"
    if value >= ASSIST:
        return "ASSIST"
    return "HUMAN"


def rank(spec: dict) -> list[dict]:
    rows = []
    for t in spec["tasks"]:
        v = score(t)
        rows.append({"id": t["id"], "name": t["name"], "score": v,
                     "verdict": verdict(v, t["scores"]["checkability"])})
    return sorted(rows, key=lambda r: r["score"], reverse=True)


def check_workflows(spec: dict, rows: list[dict]) -> list[str]:
    """Flag inconsistencies between the ranking and the chosen workflows."""
    by_id = {r["id"]: r for r in rows}
    issues = []
    covered = {t for w in spec["workflows"] for t in w["covers"]}
    for r in rows:
        if r["verdict"] == "BUILD" and r["id"] not in covered:
            issues.append(f"{r['id']} scores BUILD but no workflow covers it")
    for t in spec.get("human_owned", {}).get("tasks", []):
        if by_id[t]["verdict"] != "HUMAN":
            issues.append(f"{t} is listed human-owned but scores {by_id[t]['verdict']}")
        if t in covered:
            issues.append(f"{t} is human-owned but a workflow covers it")
    return issues


def main(path: str) -> None:
    spec = yaml.safe_load(Path(path).read_text())
    rows = rank(spec)
    print(f"# {spec['role']['title']} — {spec['role']['company']}\n")
    print("| Task | Score | Verdict | Name |\n|---|---|---|---|")
    for r in rows:
        print(f"| {r['id']} | {r['score']:.2f} | {r['verdict']} | {r['name']} |")
    issues = check_workflows(spec, rows)
    print("\nConsistency: " + ("OK" if not issues else "\n- " + "\n- ".join(issues)))


if __name__ == "__main__":
    main(sys.argv[1])
