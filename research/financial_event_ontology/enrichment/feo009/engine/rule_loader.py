"""Load JSON or YAML rules and check them against the rule schema.

Condition identifiers are validated against the engine vocabulary.
Rule text is never executed.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import yaml

from engine.conditions import REGISTRY
from engine.constants import PROFILES
from engine.paths import feo009_root

RULE_SUFFIXES = {".json", ".yaml", ".yml"}
REQUIRED_KEYS = (
    "rule_id",
    "version",
    "description",
    "population_profile",
    "candidate_kinds",
    "negative_conditions",
    "materialisation_policy",
    "acceptance_threshold",
    "review_threshold",
)


def _schema_path() -> Path:
    return feo009_root() / "rules" / "schemas" / "enrichment_rule.schema.json"


def iter_rule_files(root: Path | None = None) -> list[Path]:
    base = root or (feo009_root() / "rules")
    files = []
    for folder in ("core", "extension", "temporal"):
        directory = base / folder
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*")):
            if path.suffix.lower() in RULE_SUFFIXES and path.is_file():
                files.append(path)
    return files


def _read(path: Path):
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    return yaml.safe_load(text)


def validate_rule(rule: dict, schema: dict | None = None) -> None:
    if schema is not None:
        jsonschema.validate(rule, schema)
    missing = [key for key in REQUIRED_KEYS if key not in rule]
    if missing:
        raise ValueError(f"Rule {rule.get('rule_id')} is missing {missing}")
    if rule["population_profile"] not in PROFILES:
        raise ValueError(f"Rule {rule['rule_id']} has an unknown profile.")
    if not rule["negative_conditions"]:
        raise ValueError(f"Rule {rule['rule_id']} has no negative conditions.")
    for key in (
        "applicability_conditions",
        "required_conditions",
        "optional_conditions",
        "negative_conditions",
        "blocking_conditions",
        "review_conditions",
        "rejection_conditions",
        "scope_conditions",
    ):
        for condition_id in rule.get(key) or []:
            if condition_id not in REGISTRY:
                raise ValueError(f"Rule {rule['rule_id']} cites unknown condition {condition_id}")
    for item in rule.get("outcome_overrides") or []:
        if item["when"] not in REGISTRY:
            raise ValueError(f"Rule {rule['rule_id']} cites unknown override {item['when']}")
    for condition_id in (rule.get("confidence_contributions") or {}):
        if condition_id not in REGISTRY:
            raise ValueError(f"Rule {rule['rule_id']} cites unknown contribution {condition_id}")


def load_rules(root: Path | None = None) -> list[dict]:
    schema_path = _schema_path()
    schema = json.loads(schema_path.read_text(encoding="utf-8")) if schema_path.exists() else None
    rules = []
    seen = set()
    for path in iter_rule_files(root):
        payload = _read(path)
        items = payload["rules"] if isinstance(payload, dict) and "rules" in payload else payload
        if isinstance(items, dict):
            items = [items]
        for rule in items:
            validate_rule(rule, schema)
            if rule["rule_id"] in seen:
                raise ValueError(f"Duplicate rule id {rule['rule_id']}")
            seen.add(rule["rule_id"])
            rules.append(rule)
    if not rules:
        raise ValueError("No enrichment rules were loaded.")
    return rules
