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


PACK_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")


def available_packs() -> list[str]:
    """Rule packs on disk: resources/review_rules_<pack>.yaml."""
    return sorted(p.stem.removeprefix("review_rules_") for p in RESOURCES.glob("review_rules_*.yaml"))


def pack(name: str) -> dict:
    if not PACK_NAME.match(name) or name not in available_packs():
        raise KeyError(f"unknown rule pack {name!r}; available: {available_packs()}")
    return load(f"review_rules_{name}.yaml")


def packs_for_scenario(scenario_id: str) -> list[str]:
    """Packs a scenario switches on by default (each pack lists its scenarios)."""
    return [p for p in available_packs() if scenario_id in pack(p).get("scenarios", [])]


def rules(packs: list[str] | tuple[str, ...] = ()) -> list[dict]:
    """The general rulebook plus the rules of each requested pack, in that order."""
    out = list(load("review_rules.yaml")["rules"])
    for p in packs:
        out += pack(p)["rules"]
    return out


def all_rules() -> list[dict]:
    return rules(available_packs())


def rule(rule_id: str) -> dict:
    for r in all_rules():
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
