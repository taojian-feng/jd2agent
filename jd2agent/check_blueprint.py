"""Phase 2 check — verify a blueprint is consistent with its role spec and resource files.

Usage:
    python -m jd2agent.check_blueprint roles/<slug> agents/<agent-dir>
"""
import re
import sys
from pathlib import Path

import yaml

from jd2agent.score import rank


def check(role_dir: Path, agent_dir: Path) -> list[str]:
    spec = yaml.safe_load((role_dir / "role_spec.yaml").read_text())
    bp = yaml.safe_load((role_dir / "blueprint.yaml").read_text())
    issues: list[str] = []

    task_ids = {t["id"] for t in spec["tasks"]}
    mvp = {w["id"]: set(w["covers"]) for w in spec["workflows"] if w["priority"] == "MVP"}
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

    # 2. BUILD tasks are in an MVP workflow
    for r in rank(spec):
        if r["verdict"] == "BUILD" and not any(r["id"] in s for s in mvp.values()):
            issues.append(f"{r['id']} scores BUILD but is not in an MVP workflow")

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

    # 5. resource files exist
    for res in bp["resources"]:
        if not res.get("generated") and not (agent_dir / res["file"]).exists():
            issues.append(f"resource file missing: {res['file']}")

    # 6. deterministic review rules point at sections the design template actually has
    template = (agent_dir / "resources/templates/design_doc.md").read_text()
    sections = set(re.findall(r"^## (.+)$", template, re.M))
    rules = yaml.safe_load((agent_dir / "resources/review_rules.yaml").read_text())
    for r in rules["rules"]:
        if r["check"] == "deterministic" and r.get("requires_section") not in sections:
            issues.append(f"rule {r['id']} requires missing section {r.get('requires_section')!r}")

    # 7. pattern signals are all defined
    pats = yaml.safe_load((agent_dir / "resources/patterns.yaml").read_text())
    for p in pats["patterns"]:
        for s in p["fit"]:
            if s not in pats["signals"]:
                issues.append(f"pattern {p['id']} uses undefined signal {s}")
    return issues


if __name__ == "__main__":
    problems = check(Path(sys.argv[1]), Path(sys.argv[2]))
    print("Blueprint consistency: OK" if not problems else "\n".join(f"- {p}" for p in problems))
    sys.exit(1 if problems else 0)
