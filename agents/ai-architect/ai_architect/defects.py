"""Planted-defect sets: does a review (with its rule packs) catch known flaws?

A set lives in resources/defect_sets/<set>/:
    base.md       a clean design that passed review
    defects.yaml  variants, each = base + edits to named sections, with the rule ids it should trigger

    python -m ai_architect.cli review-set --set prior-auth

Scoring is a pure function (score_set) so it is unit-tested without a model.
"""
import re
from pathlib import Path

import yaml

from ai_architect import catalog

SECTION = r"(^## {name}\n)(.*?)(?=^## |\Z)"


def set_dir(set_id: str) -> Path:
    if not re.match(r"^[a-z0-9][a-z0-9-]{0,60}$", set_id):
        raise FileNotFoundError(set_id)
    d = catalog.RESOURCES / "defect_sets" / set_id
    if not (d / "defects.yaml").exists():
        raise FileNotFoundError(f"unknown defect set {set_id}")
    return d


def load_set(set_id: str) -> dict:
    d = set_dir(set_id)
    spec = yaml.safe_load((d / "defects.yaml").read_text(encoding="utf-8"))
    spec["base"] = (d / spec.get("base", "base.md")).read_text(encoding="utf-8")
    return spec


def apply_edit(markdown: str, edit: dict) -> str:
    """edit: {section, set: text} replaces the section body; {section, append: text} adds a paragraph;
    {section, replace: [old, new]} swaps text inside the section. Raises if the section or text is missing."""
    pat = re.compile(SECTION.format(name=re.escape(edit["section"])), re.M | re.S)
    m = pat.search(markdown)
    if not m:
        raise ValueError(f"section not found: {edit['section']}")
    body = m.group(2)
    if "set" in edit:
        body = edit["set"].strip() + "\n\n"
    elif "append" in edit:
        body = body.rstrip() + "\n\n" + edit["append"].strip() + "\n\n"
    elif "replace" in edit:
        old, new = edit["replace"]
        if old not in body:
            raise ValueError(f"text not found in {edit['section']}: {old[:60]!r}")
        body = body.replace(old, new)
    return markdown[:m.start(2)] + body + markdown[m.end(2):]


def variants(spec: dict) -> dict[str, str]:
    out = {}
    for v in spec["variants"]:
        md = spec["base"]
        for e in v.get("edits", []):
            md = apply_edit(md, e)
        out[v["id"]] = md
    return out


def score_set(spec: dict, findings: dict[str, list[str]], decisions: dict[str, str]) -> dict:
    """findings: variant id -> rule ids found. A planted defect counts as caught if any of its expected rules fired.
    For the clean variant, any finding from the set's watched rules is a false alarm."""
    watched = set(spec.get("watch_rules", []))
    rows, caught, planted = [], 0, 0
    false_alarms: list[str] = []
    for v in spec["variants"]:
        got = findings.get(v["id"], [])
        expect = v.get("expect_any", [])
        if expect:
            planted += 1
            hit = bool(set(expect) & set(got))
            caught += hit
        else:
            hit = None
            false_alarms += [r for r in got if r in watched]
        rows.append({"id": v["id"], "defect": v.get("defect", "clean"), "expect_any": expect,
                     "found": got, "caught": hit, "decision": decisions.get(v["id"])})
    return {"planted": planted, "caught": caught, "recall": round(caught / planted, 3) if planted else None,
            "clean_false_alarms": false_alarms, "rows": rows}


def report(result: dict, target: float) -> str:
    ok = result["recall"] is not None and result["recall"] >= target
    out = ["# Planted-defect review", "",
           f"Recall {result['caught']}/{result['planted']} = {result['recall']:.0%} (target ≥ {target:.0%}): "
           f"{'pass' if ok else 'FAIL'}. False alarms on the clean design: "
           f"{', '.join(result['clean_false_alarms']) or 'none'}.", "",
           "| Variant | Planted defect | Expected rule | Decision | Caught | Findings |", "|---|---|---|---|---|---|"]
    for r in result["rows"]:
        caught = "—" if r["caught"] is None else ("yes" if r["caught"] else "NO")
        out.append(f"| {r['id']} | {r['defect']} | {' or '.join(r['expect_any']) or '—'} | {r['decision']} | "
                   f"{caught} | {', '.join(r['found']) or 'none'} |")
    return "\n".join(out) + "\n"
