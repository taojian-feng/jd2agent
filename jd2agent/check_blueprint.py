"""Phase 2 check — verify a blueprint is consistent with its role spec and resource files.

Usage:
    python -m jd2agent.check_blueprint roles/<slug> agents/<agent-dir>
"""
import re
import sys
from pathlib import Path

import yaml

from jd2agent.score import rank


def check(role_dir: Path, agent_dir: Path, notes: list[str] | None = None) -> list[str]:
    """Return blocking issues. Non-blocking observations are appended to `notes` when given.

    agent_dir is the primary (existing) agent. A tool or resource may name another agent with `agent:`;
    its files then resolve under agents/<agent>/. Resources with `status: planned` are listed, not required.
    """
    notes = notes if notes is not None else []
    spec = yaml.safe_load((role_dir / "role_spec.yaml").read_text())
    bp = yaml.safe_load((role_dir / "blueprint.yaml").read_text())
    issues: list[str] = []

    task_ids = {t["id"] for t in spec["tasks"]}
    mvp = {w["id"]: set(w["covers"]) for w in spec["workflows"] if w["priority"] == "MVP"}
    covered = {t for w in spec["workflows"] for t in w["covers"]}
    human = set(spec.get("human_owned", {}).get("tasks", []))

    # 1. tools cover real, non-human tasks; every MVP task has at least one tool
    tool_cover: dict[str, set[str]] = {}
    for tool in bp["tools"]:
        for t in tool.get("covers", []):
            if t not in task_ids:
                issues.append(f"tool {tool['name']} covers unknown task {t}")
            if t in human:
                issues.append(f"tool {tool['name']} covers human-owned task {t}")
            tool_cover.setdefault(tool["workflow"], set()).add(t)
    for wf, tasks in mvp.items():
        for t in sorted(tasks - tool_cover.get(wf, set())):
            issues.append(f"{wf} task {t} has no tool")

    # 2. BUILD tasks sit in a workflow; ones deferred to stretch are noted (engineer roles score many BUILD tasks)
    for r in rank(spec):
        if r["verdict"] != "BUILD":
            continue
        if r["id"] not in covered:
            issues.append(f"{r['id']} scores BUILD but is in no workflow")
        elif not any(r["id"] in s for s in mvp.values()):
            notes.append(f"{r['id']} scores BUILD ({r['score']:.2f}), deferred to a stretch workflow")

    # 3. every LLM tool names a validator
    for tool in bp["tools"]:
        if tool["kind"] in ("L", "D+L") and not tool.get("validator"):
            issues.append(f"LLM tool {tool['name']} has no deterministic validator")

    # 4. graph nodes are tools or declared internal steps
    tool_names = {t["name"] for t in bp["tools"]}
    internal = {"confirm_requirements", "assemble_design_doc", "validate_citations", "assemble_review"}
    for gname, g in bp["graphs"].items():
        for n in g["nodes"]:
            if n not in tool_names | internal:
                issues.append(f"graph {gname} node {n} is not a tool")

    # 5. resource files exist (resolved per owning agent); planned files are listed, not required
    for res in bp["resources"]:
        owner = agent_dir.parent / res["agent"] if res.get("agent") else agent_dir
        where = f"{owner.name}/{res['file']}"
        if res.get("status") == "planned":
            notes.append(f"planned resource: {where}")
        elif not res.get("generated") and not (owner / res["file"]).exists():
            issues.append(f"resource file missing: {where}")

    # 6. deterministic review rules point at sections the design template actually has
    template = (agent_dir / "resources/templates/design_doc.md").read_text()
    sections = set(re.findall(r"^## (.+)$", template, re.M))
    #    (the general rulebook and every rule pack, review_rules_<pack>.yaml)
    for path in sorted((agent_dir / "resources").glob("review_rules*.yaml")):
        for r in yaml.safe_load(path.read_text())["rules"]:
            if r["check"] == "deterministic" and r.get("requires_section") not in sections:
                issues.append(f"{path.name}: rule {r['id']} requires missing section {r.get('requires_section')!r}")

    # 7. pattern signals are all defined
    pats = yaml.safe_load((agent_dir / "resources/patterns.yaml").read_text())
    for p in pats["patterns"]:
        for s in p["fit"]:
            if s not in pats["signals"]:
                issues.append(f"pattern {p['id']} uses undefined signal {s}")
    return issues


if __name__ == "__main__":
    notes: list[str] = []
    problems = check(Path(sys.argv[1]), Path(sys.argv[2]), notes)
    print("Blueprint consistency: OK" if not problems else "\n".join(f"- {p}" for p in problems))
    for n in notes:
        print(f"  note: {n}")
    sys.exit(1 if problems else 0)
