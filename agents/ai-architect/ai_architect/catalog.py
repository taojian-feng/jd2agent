"""Loads the knowledge catalogs in resources/ (cached; the files are the source of truth)."""
import os
import re
from functools import lru_cache
from pathlib import Path

import yaml

RESOURCES = Path(os.environ.get("AI_ARCHITECT_RESOURCES", Path(__file__).resolve().parents[1] / "resources"))


@lru_cache
def load(name: str) -> dict:
    return yaml.safe_load((RESOURCES / name).read_text(encoding="utf-8"))


def text(name: str) -> str:
    return (RESOURCES / name).read_text(encoding="utf-8")


def patterns() -> dict:
    return load("patterns.yaml")


def platforms() -> dict:
    return load("platforms.yaml")


def rules() -> list[dict]:
    return load("review_rules.yaml")["rules"]


def rule(rule_id: str) -> dict:
    for r in rules():
        if r["id"] == rule_id:
            return r
    raise KeyError(rule_id)


def template_sections() -> list[str]:
    return re.findall(r"^## (.+)$", text("templates/design_doc.md"), re.M)


def scenario(scenario_id: str) -> str:
    path = (RESOURCES / "scenarios" / f"{scenario_id}.md").resolve()
    if path.parent != (RESOURCES / "scenarios").resolve() or not path.exists():
        raise FileNotFoundError(f"unknown scenario: {scenario_id}")
    return path.read_text(encoding="utf-8")
