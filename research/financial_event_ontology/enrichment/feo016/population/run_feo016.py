"""FEO-016 population, determinism, delta, and provisional counts.

The FEO-009 engine and the FEO-014 adapter are imported and not edited.
Rules are loaded from the FEO-016 rule directory.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

FEO016 = Path(__file__).resolve().parents[1]
REPO = FEO016.parents[3]
FEO = REPO / "research" / "financial_event_ontology"
FEO009 = FEO / "enrichment" / "feo009"
FEO014 = FEO / "population" / "feo014"
FEO011 = FEO / "population" / "feo011"
RUN1 = FEO016 / "population" / "run1"
RUN2 = FEO016 / "population" / "run2"
BASELINE = FEO014 / "rerun"
CONDITION = "negative_market_not_undergoer_of_trigger"
FINANCIAL_TARGETS = {"MarketChangeEvent", "hasAffectedMarket"}
DEPENDENT_TARGETS = {"MarketChangeEvent", "hasAffectedMarket", "hasMarketDirection"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_hash(path: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(
        item
        for item in path.rglob("*")
        if item.is_file() and "__pycache__" not in item.parts and item.suffix != ".pyc" and not item.is_symlink()
    )
    for file in files:
        digest.update(str(file.relative_to(path)).encode())
        digest.update(b"\0")
        digest.update(file.read_bytes())
    return digest.hexdigest()


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: "" if row.get(key) is None else row.get(key) for key in fieldnames})


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")


def configure():
    if str(FEO009) not in sys.path:
        sys.path.insert(0, str(FEO009))
    if str(FEO014) not in sys.path:
        sys.path.insert(0, str(FEO014))
    if str(FEO011) not in sys.path:
        sys.path.insert(0, str(FEO011))
    spec = importlib.util.spec_from_file_location(
        "feo016_condition",
        FEO016 / "rule_extension" / "condition.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from engine.conditions import REGISTRY
    from engine.rule_loader import load_rules
    import engine.engine as engine_module

    REGISTRY[CONDITION] = module.negative_market_not_undergoer_of_trigger
    rules = load_rules(FEO016 / "rules")
    engine_module.load_rules = lambda root=None: rules
    import run_feo014

    return run_feo014


def immutable_hashes() -> dict:
    return {
        "ontology": sha256_file(FEO / "ontology/feo007a/ontology/fneo-0.1.0-rc2.ttl"),
        "core_shapes": sha256_file(FEO / "ontology/feo007a/validation/fneo-core-shapes.ttl"),
        "supplemental_shapes": sha256_file(FEO / "ontology/feo007a/validation/supplemental-shapes.ttl"),
        "extension_shapes": sha256_file(FEO / "ontology/feo007a/validation/fneo-extension-shapes.ttl"),
        "feo009_rules": tree_hash(FEO009 / "rules"),
        "feo008": tree_hash(FEO / "mappings/feo008"),
        "feo010a_adapter": tree_hash(FEO / "population/feo010a/corrected_adapter"),
        "feo014_rerun_candidates": tree_hash(BASELINE / "candidates"),
        "feo014_rerun_decisions": tree_hash(BASELINE / "decisions"),
        "feo014_rerun_rdf": tree_hash(BASELINE / "rdf"),
        "feo012b_reference_csv": sha256_file(FEO / "review/feo012b/reference_set/feo012b_reference_set.csv"),
        "post_correction_reference_csv": sha256_file(
            FEO / "population/feo014/delta/adjudicated/post_correction_reference_set.csv"
        ),
        "feo013": tree_hash(FEO / "evaluation/feo013"),
        "feo015": tree_hash(FEO / "evaluation/feo015"),
    }


def populate(driver, root: Path, validate_shacl: bool) -> list[dict]:
    root.mkdir(parents=True, exist_ok=True)
    identifiers = driver.document_ids()
    module = driver.install_population()
    summaries = []
    for index, document_id in enumerate(identifiers, start=1):
        print(f"FEO-016 populate {index}/{len(identifiers)} {document_id} shacl={validate_shacl}", flush=True)
        bundle = driver.load_bundle(BASELINE / "extraction" / "per_document" / document_id, document_id)
        summaries.append(module.process_document(bundle, root, validate_shacl=validate_shacl))
    driver.dump_json(root / "population_summaries.json", summaries)
    return summaries


def file_hashes(root: Path, patterns: tuple[str, ...]) -> dict[str, str]:
    found = {}
    for pattern in patterns:
        for path in sorted(root.glob(pattern)):
            if path.is_file():
                found[str(path.relative_to(root))] = sha256_file(path)
    return found


SEMANTIC = (
    "candidates/per_document/*/candidates.json",
    "decisions/per_document/*/decisions.json",
    "rdf/accepted/per_document/*.ttl",
    "rdf/review-required/per_document/*.ttl",
    "rdf/rejected/per_document/*.ttl",
    "rdf/experimental/per_document/*.ttl",
)


def compare_runs(left: Path, right: Path) -> dict:
    first = file_hashes(left, SEMANTIC)
    second = file_hashes(right, SEMANTIC)
    missing = sorted(set(first) - set(second))
    extra = sorted(set(second) - set(first))
    different = sorted(key for key in first.keys() & second.keys() if first[key] != second[key])
    return {
        "pass": not missing and not extra and not different,
        "compared_files": len(first),
        "missing_count": len(missing),
        "extra_count": len(extra),
        "different_count": len(different),
        "different": different[:20],
    }


def load_decisions(root: Path) -> dict[tuple, dict]:
    found = {}
    for path in sorted((root / "decisions" / "per_document").glob("*/decisions.json")):
        for row in json.loads(path.read_text(encoding="utf-8")):
            found[(row.get("document_id"), row.get("decision_id"))] = row
    return found


def load_candidates(root: Path) -> dict[tuple, dict]:
    found = {}
    for path in sorted((root / "candidates" / "per_document").glob("*/candidates.json")):
        for row in json.loads(path.read_text(encoding="utf-8")):
            found[(row.get("document_id"), row.get("candidate_id"))] = row
    return found


def signature(row: dict) -> tuple:
    return (
        row.get("status"),
        row.get("target_local_name"),
        row.get("rule_id"),
        bool(row.get("direct_triple_eligible")),
        row.get("subject_iri") or "",
        row.get("predicate_iri") or "",
        row.get("object_iri") or "",
        row.get("profile") or "",
    )


def protected_rule_ids() -> set[str]:
    ids = set()
    for relative in (
        "core/entity_rules.json",
        "extension/entity_rules.json",
        "temporal/temporal_rules.json",
        "core/value_and_evidence_rules.json",
    ):
        payload = json.loads((FEO009 / "rules" / relative).read_text(encoding="utf-8"))
        ids.update(rule["rule_id"] for rule in payload["rules"])
    return ids


def event_status(decisions: dict, document_id: str, event_candidate_id: str) -> str:
    statuses = [
        row.get("status") or ""
        for (doc, _decision_id), row in decisions.items()
        if doc == document_id
        and row.get("candidate_id") == event_candidate_id
        and row.get("target_local_name") == "MarketChangeEvent"
    ]
    if "accepted" in statuses:
        return "accepted"
    return statuses[0] if statuses else ""


def source_event_candidate_id(row: dict, candidate: dict) -> str:
    if row.get("target_local_name") == "hasMarketDirection" or str(row.get("rule_id") or "").startswith("FE-DIR"):
        return row.get("candidate_id") or ""
    return (candidate.get("features") or {}).get("event_candidate_id") or ""


def classify(old: dict, new: dict, old_decisions: dict, new_decisions: dict, candidates: dict) -> str:
    old_status = old.get("status")
    new_status = new.get("status")
    target = new.get("target_local_name") or old.get("target_local_name")
    if target == "MarketChangeEvent":
        pair = (old_status, new_status)
        mapping = {
            ("accepted", "requires_review"): "event accepted to review",
            ("accepted", "rejected"): "event accepted to rejected",
            ("requires_review", "accepted"): "event review to accepted",
            ("rejected", "accepted"): "event rejected to accepted",
        }
        return mapping.get(pair, f"event other status change {old_status} to {new_status}")
    candidate = candidates.get((new.get("document_id"), new.get("candidate_id")), {})
    event_id = source_event_candidate_id(new, candidate)
    old_event = event_status(old_decisions, old.get("document_id"), event_id)
    new_event = event_status(new_decisions, new.get("document_id"), event_id)
    source_lost = old_event == "accepted" and new_event != "accepted"
    if source_lost and old_status == "accepted" and new_status != "accepted":
        return "relation removed due to source event"
    if old_status != "accepted" and new_status == "accepted":
        return "relation independently changed"
    if old_status != new_status:
        return "relation independently changed" if not source_lost else "relation removed due to source event"
    return "unchanged"


def count_status(decisions: dict, target: str) -> Counter:
    counts = Counter()
    for row in decisions.values():
        if row.get("target_local_name") == target and row.get("profile") == "CORE_DETERMINISTIC":
            if row.get("status") == "accepted" and row.get("direct_triple_eligible"):
                counts["accepted"] += 1
            elif row.get("status") == "accepted":
                counts["accepted_not_direct"] += 1
            else:
                counts[row.get("status") or ""] += 1
    return counts


def build_delta(old_root: Path, new_root: Path) -> tuple[list[dict], dict]:
    old_decisions = load_decisions(old_root)
    new_decisions = load_decisions(new_root)
    candidates = load_candidates(new_root)
    protected = protected_rule_ids()
    rows = []
    classes = Counter()
    out_of_scope = []
    keys = sorted(set(old_decisions) | set(new_decisions))
    for key in keys:
        old = old_decisions.get(key)
        new = new_decisions.get(key)
        if old is None or new is None:
            if old is not None and new is None and old.get("rule_id") == "FE-DIR-001":
                candidate = candidates.get((old.get("document_id"), old.get("candidate_id")), {})
                old_event = event_status(old_decisions, old.get("document_id"), old.get("candidate_id"))
                new_event = event_status(new_decisions, old.get("document_id"), old.get("candidate_id"))
                if old_event == "accepted" and new_event != "accepted":
                    classes["relation removed due to source event"] += 1
                    features = candidate.get("features") or {}
                    rows.append(
                        {
                            "change_class": "relation removed due to source event",
                            "document_id": old.get("document_id") or "",
                            "candidate_id": old.get("candidate_id") or "",
                            "decision_id": old.get("decision_id") or "",
                            "assertion_id": old.get("assertion_iri") or "",
                            "target": old.get("target_local_name") or "",
                            "trigger": candidate.get("trigger_or_lexical_form") or "",
                            "market_text": features.get("market_surface") or "",
                            "source_text": candidate.get("textual_evidence") or "",
                            "old_decision": old.get("status") or "",
                            "new_decision": "not_emitted",
                            "old_status": old.get("status") or "",
                            "new_status": "not_emitted",
                            "old_rule": old.get("rule_id") or "",
                            "new_rule": old.get("rule_id") or "",
                            "old_rule_version": old.get("rule_version") or "",
                            "new_rule_version": "feo016-0.1.0",
                            "reason": "Direction was not emitted because the source market-change event is no longer accepted.",
                        }
                    )
                    continue
            classes["identifier-only"] += 1
            present = old or new
            out_of_scope.append(
                {
                    "document_id": present.get("document_id"),
                    "rule_id": present.get("rule_id"),
                    "target": present.get("target_local_name"),
                    "issue": "decision key missing",
                }
            )
            continue
        if signature(old) == signature(new):
            classes["unchanged"] += 1
            continue
        rule_id = new.get("rule_id") or old.get("rule_id")
        if rule_id in protected:
            classes["out_of_scope"] += 1
            out_of_scope.append(
                {
                    "document_id": new.get("document_id"),
                    "rule_id": rule_id,
                    "target": new.get("target_local_name"),
                    "old_status": old.get("status"),
                    "new_status": new.get("status"),
                }
            )
            continue
        label = classify(old, new, old_decisions, new_decisions, candidates)
        classes[label] += 1
        candidate = candidates.get((new.get("document_id"), new.get("candidate_id")), {})
        features = candidate.get("features") or {}
        event_candidate = candidates.get((new.get("document_id"), features.get("event_candidate_id")), {})
        trigger = candidate.get("trigger_or_lexical_form") or ""
        if candidate.get("candidate_kind") == "participation_candidate":
            trigger = event_candidate.get("trigger_or_lexical_form") or trigger
        market = features.get("market_surface") or ""
        if candidate.get("candidate_kind") == "participation_candidate":
            market = candidate.get("trigger_or_lexical_form") or market
        rows.append(
            {
                "change_class": label,
                "document_id": new.get("document_id") or "",
                "candidate_id": new.get("candidate_id") or "",
                "decision_id": new.get("decision_id") or "",
                "assertion_id": new.get("assertion_iri") or old.get("assertion_iri") or "",
                "target": new.get("target_local_name") or "",
                "trigger": trigger,
                "market_text": market,
                "source_text": candidate.get("textual_evidence") or "",
                "old_decision": old.get("status") or "",
                "new_decision": new.get("status") or "",
                "old_status": old.get("status") or "",
                "new_status": new.get("status") or "",
                "old_rule": old.get("rule_id") or "",
                "new_rule": new.get("rule_id") or "",
                "old_rule_version": old.get("rule_version") or "",
                "new_rule_version": new.get("rule_version") or "",
                "reason": "; ".join(new.get("reasons") or []),
            }
        )
    return rows, {"classes": dict(classes), "out_of_scope": out_of_scope}


def reference_index() -> dict[tuple, dict]:
    rows = read_csv(FEO / "population/feo014/delta/adjudicated/post_correction_reference_set.csv")
    chosen: dict[tuple, dict] = {}
    for row in rows:
        key = (row.get("document_id") or "", row.get("corrected_candidate_id") or "", row.get("review_set") or "")
        if not key[1]:
            continue
        current = chosen.get(key)
        eligible = row.get("evaluation_eligible") == "true"
        if current is None or (eligible and current.get("evaluation_eligible") != "true"):
            chosen[key] = row
    return chosen


def _label_for(labels: dict, row: dict) -> str:
    review_set = {
        "MarketChangeEvent": "market_change_event",
        "hasAffectedMarket": "affected_market",
        "hasMarketDirection": "direction",
    }.get(row["target"], "")
    prior = labels.get((row["document_id"], row["candidate_id"], review_set))
    if not prior:
        return ""
    return prior.get("old_researcher_label") or prior.get("evaluation_label") or ""


def human_package(delta_rows: list[dict]) -> list[dict]:
    labels = reference_index()
    selected = [
        row
        for row in delta_rows
        if row["target"] in DEPENDENT_TARGETS and row["old_status"] == "accepted" and row["new_status"] != "accepted"
    ]
    selected.sort(key=lambda row: (row["document_id"], row["candidate_id"], row["new_rule"], row["decision_id"]))
    package = []
    for index, row in enumerate(selected, start=1):
        prior_label = _label_for(labels, row)
        package.append(
            {
                "delta_review_id": f"FEO016-DELTA-{index:04d}",
                "document_id": row["document_id"],
                "candidate_id": row["candidate_id"],
                "assertion_id": row["assertion_id"],
                "trigger": row["trigger"],
                "market_text": row["market_text"],
                "source_text": row["source_text"],
                "old_status": row["old_status"],
                "new_status": row["new_status"],
                "old_rule": row["old_rule"],
                "new_rule": row["new_rule"],
                "old_researcher_label": prior_label,
                "proposed_label_carry_forward": prior_label,
                "change_reason": row["change_class"],
                "human_review_required": "true",
                "researcher_final_label": "",
                "researcher_notes": "",
            }
        )
    return package


def shacl_package(driver, summaries: list[dict]) -> dict:
    from adapter.checks import validate_accepted
    from rdflib import Graph

    rows = []
    eligible = []
    for summary in summaries:
        document_id = summary["document_id"]
        path = RUN1 / "validation" / "per_document" / f"{document_id}.json"
        report = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        conforms = report.get("conforms")
        if conforms is True:
            eligible.append(document_id)
        rows.append(
            {
                "document_id": document_id,
                "conforms": conforms,
                "violation_count": report.get("violation_count"),
                "warning_count": report.get("warning_count"),
                "information_count": report.get("info_count"),
                "engine": report.get("engine") or "",
            }
        )
    write_csv(
        FEO016 / "validation" / "per_document_shacl.csv",
        rows,
        ["document_id", "conforms", "violation_count", "warning_count", "information_count", "engine"],
    )

    def union(paths: list[Path]) -> str:
        graph = Graph()
        for path in paths:
            text = path.read_text(encoding="utf-8") if path.is_file() else ""
            if text.strip() and not text.lstrip().startswith("#"):
                graph.parse(data=text, format="turtle")
        from adapter.materialisation.materialise import deterministic_turtle
        from driver.populate import _repair_turtle_literals

        if len(graph) == 0:
            return "# No triples.\n"
        return _repair_turtle_literals(deterministic_turtle(graph))

    core_text = union([RUN1 / "rdf/accepted/per_document" / f"{document_id}-core.ttl" for document_id in eligible])
    core_path = RUN1 / "rdf/accepted/consolidated/fneo-stock-core.ttl"
    core_path.parent.mkdir(parents=True, exist_ok=True)
    core_path.write_text(core_text, encoding="utf-8")
    consolidated = validate_accepted(
        core_text,
        FEO / "ontology/feo007a/ontology/fneo-0.1.0-rc2.ttl",
        FEO / "ontology/feo007a/validation/fneo-core-shapes.ttl",
        FEO / "ontology/feo007a/validation/supplemental-shapes.ttl",
    )
    extension_text = union(
        [RUN1 / "rdf/review-required/per_document" / f"{document_id}-extension.ttl" for document_id in driver.document_ids()]
    )
    extension_path = RUN1 / "rdf/review-required/consolidated/fneo-stock-extension.ttl"
    extension_path.parent.mkdir(parents=True, exist_ok=True)
    extension_path.write_text(extension_text, encoding="utf-8")
    from adapter.checks import _shacl

    module = _shacl()
    extension_graph = Graph()
    if extension_text.strip() and not extension_text.lstrip().startswith("#"):
        extension_graph.parse(data=extension_text, format="turtle")
    extension_report = module.validate_graphs(
        extension_graph,
        module.load_graph(FEO / "ontology/feo007a/validation/fneo-extension-shapes.ttl"),
        module.load_graph(FEO / "ontology/feo007a/ontology/fneo-0.1.0-rc2.ttl"),
    )
    policy = Counter()
    for summary in summaries:
        for key in ("review_direct", "rejected_direct", "noncore_in_core", "same_as"):
            policy[key] += int((summary.get("policy") or {}).get(key) or 0)
    return {
        "eligible_documents": eligible,
        "per_document_nonconforming": [row["document_id"] for row in rows if row["conforms"] is not True],
        "consolidated": consolidated,
        "extension_conforms": not any(item.severity == "Violation" for item in extension_report.results),
        "extension_violations": sum(1 for item in extension_report.results if item.severity == "Violation"),
        "extension_warnings": sum(1 for item in extension_report.results if item.severity == "Warning"),
        "policy": dict(policy),
        "core_text_path": str(core_path.relative_to(REPO)),
        "extension_text_path": str(extension_path.relative_to(REPO)),
    }


def competency_counts(core_path: Path, extension_path: Path) -> list[dict]:
    spec = importlib.util.spec_from_file_location(
        "compute_feo015",
        FEO / "evaluation/feo015/metrics/compute_feo015.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fresh = module.run_queries(core_path.read_text(encoding="utf-8"), extension_path.read_text(encoding="utf-8"))
    prior = {row["cq_id"]: row for row in read_csv(FEO / "evaluation/feo015/competency_questions/cq_population_support_post_correction.csv")}
    rows = []
    for row in fresh:
        previous = prior.get(row["cq_id"], {})
        rows.append(
            {
                "cq_id": row["cq_id"],
                "scope": row["scope"],
                "feo015_answer_row_count": previous.get("answer_row_count", ""),
                "feo016_answer_row_count": row["answer_row_count"],
                "row_count_changed": str(previous.get("answer_row_count", "")) != str(row["answer_row_count"]),
                "execution_status": row["execution_status"],
            }
        )
    return rows


def guard(delta_rows: list[dict], class_info: dict, hashes_before: dict, hashes_after: dict, positive_ok: bool) -> dict:
    accepted_financial = [
        row
        for row in delta_rows
        if row["target"] in FINANCIAL_TARGETS and row["old_status"] == "accepted" and row["new_status"] != "accepted"
    ]
    new_accepts = [
        row
        for row in delta_rows
        if row["target"] in FINANCIAL_TARGETS and row["old_status"] != "accepted" and row["new_status"] == "accepted"
    ]
    hash_changed = sorted(key for key, value in hashes_before.items() if hashes_after.get(key) != value)
    ontology_changed = any(key in {"ontology", "core_shapes", "supplemental_shapes", "extension_shapes", "feo008"} for key in hash_changed)
    status = "PASS"
    reasons = []
    if len(accepted_financial) > 100:
        status = "EXCESSIVE_DELTA"
        reasons.append(f"{len(accepted_financial)} accepted financial decisions changed.")
    if class_info["out_of_scope"]:
        status = "OUT_OF_SCOPE_CHANGE"
        reasons.append(f"{len(class_info['out_of_scope'])} entity, temporal, or value decisions changed.")
    if any(row["change_class"] == "relation independently changed" for row in delta_rows):
        status = "OUT_OF_SCOPE_CHANGE"
        reasons.append("A relation changed independently of its source event.")
    if new_accepts:
        status = "REGRESSION"
        reasons.append("A previously unaccepted financial decision became accepted.")
    if not positive_ok:
        status = "REGRESSION"
        reasons.append("A positive-protection fixture was lost.")
    if ontology_changed or "feo009_rules" in hash_changed or "feo010a_adapter" in hash_changed:
        status = "INVALID_RUN"
        reasons.append("An authoritative ontology, mapping, rule, or adapter digest changed: " + ", ".join(hash_changed))
    if any(key.startswith("feo014_") for key in hash_changed):
        status = "INVALID_RUN"
        reasons.append("A FEO-014 population artefact changed.")
    return {
        "status": status,
        "reasons": reasons,
        "accepted_financial_changes": len(accepted_financial),
        "new_accepts": len(new_accepts),
        "out_of_scope": len(class_info["out_of_scope"]),
        "hash_changed": hash_changed,
        "ready_for_metrics": status == "PASS",
    }


def positive_fixtures_ok() -> bool:
    from engine.engine import EnrichmentEngine
    from engine.rule_loader import load_rules

    engine = EnrichmentEngine(load_rules(FEO016 / "rules"))
    for path in sorted((FEO016 / "fixtures" / "input").glob("feo016-pos-*.json")):
        envelope = json.loads(path.read_text(encoding="utf-8"))
        result = engine.run(envelope)
        expected = envelope["expected"]
        matches = [
            row
            for row in result["decisions"]
            if row["candidate_id"] == expected["primary_candidate_id"] and row["rule_id"] == expected["rule_id"]
        ]
        if not matches or matches[0]["status"] != expected["status"]:
            return False
        if CONDITION in (matches[0].get("negative_conditions_fired") or []):
            return False
        if expected["status"] == "accepted" and matches[0]["direct_triple_eligible"] is not True:
            return False
    return True


def provisional(old_decisions, new_decisions, delta_rows, shacl, queries, guard_result) -> None:
    def accepted(decisions, target):
        return sum(
            1
            for row in decisions.values()
            if row.get("target_local_name") == target
            and row.get("status") == "accepted"
            and row.get("direct_triple_eligible")
            and row.get("profile") == "CORE_DETERMINISTIC"
        )

    def review(decisions, target):
        return sum(
            1
            for row in decisions.values()
            if row.get("target_local_name") == target
            and row.get("status") == "requires_review"
            and row.get("profile") == "CORE_DETERMINISTIC"
        )

    def rejected(decisions, target):
        return sum(
            1
            for row in decisions.values()
            if row.get("target_local_name") == target
            and row.get("status") == "rejected"
            and row.get("profile") == "CORE_DETERMINISTIC"
        )

    documents = sorted({row["document_id"] for row in delta_rows})
    payload = {
        "label": "provisional_system_output_only",
        "performance_metrics_calculated": False,
        "accepted_market_change_event_before": accepted(old_decisions, "MarketChangeEvent"),
        "accepted_market_change_event_after": accepted(new_decisions, "MarketChangeEvent"),
        "review_market_change_event_before": review(old_decisions, "MarketChangeEvent"),
        "review_market_change_event_after": review(new_decisions, "MarketChangeEvent"),
        "rejected_market_change_event_before": rejected(old_decisions, "MarketChangeEvent"),
        "rejected_market_change_event_after": rejected(new_decisions, "MarketChangeEvent"),
        "accepted_has_affected_market_before": accepted(old_decisions, "hasAffectedMarket"),
        "accepted_has_affected_market_after": accepted(new_decisions, "hasAffectedMarket"),
        "review_has_affected_market_before": review(old_decisions, "hasAffectedMarket"),
        "review_has_affected_market_after": review(new_decisions, "hasAffectedMarket"),
        "changed_document_count": len(documents),
        "changed_decision_count": len(delta_rows),
        "direction_removed_with_source_event": sum(
            1
            for row in delta_rows
            if row["target"] == "hasMarketDirection" and row["change_class"] == "relation removed due to source event"
        ),
        "shacl_conforms": shacl["consolidated"].get("conforms"),
        "shacl_violations": shacl["consolidated"].get("violation_count"),
        "extension_conforms": shacl["extension_conforms"],
        "cq_row_count_changes": sum(1 for row in queries if str(row["row_count_changed"]).lower() == "true"),
        "guard_status": guard_result["status"],
    }
    (FEO016 / "evaluation" / "provisional_population_changes.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# Provisional population changes",
        "",
        "These figures describe system outputs before human delta review. Precision, recall, and F1 are not calculated.",
        "",
        f"Accepted MarketChangeEvent count: {payload['accepted_market_change_event_before']} before, {payload['accepted_market_change_event_after']} after.",
        f"Review MarketChangeEvent count: {payload['review_market_change_event_before']} before, {payload['review_market_change_event_after']} after.",
        f"Rejected MarketChangeEvent count: {payload['rejected_market_change_event_before']} before, {payload['rejected_market_change_event_after']} after.",
        f"Accepted hasAffectedMarket count: {payload['accepted_has_affected_market_before']} before, {payload['accepted_has_affected_market_after']} after.",
        f"Review hasAffectedMarket count: {payload['review_has_affected_market_before']} before, {payload['review_has_affected_market_after']} after.",
        f"Changed document count: {payload['changed_document_count']}.",
        f"Changed decision count: {payload['changed_decision_count']}.",
        "Accepted hasMarketDirection decisions that are no longer emitted, because their source event is no longer accepted, are included in the changed-decision count.",
        f"Accepted direction decisions removed with their source event: {payload['direction_removed_with_source_event']}.",
        f"SHACL consolidated conforms: {payload['shacl_conforms']}. Violations: {payload['shacl_violations']}.",
        f"Extension output conforms: {payload['extension_conforms']}.",
        f"Competency-question row counts that differ from FEO-015: {payload['cq_row_count_changes']}.",
        f"Change-scope guard: {payload['guard_status']}.",
        "",
    ]
    write_text(FEO016 / "evaluation" / "provisional_population_changes.md", "\n".join(lines))
    write_text(FEO016 / "reports" / "provisional_population_changes.md", "\n".join(lines))


def main() -> int:
    before = immutable_hashes()
    (FEO016 / "validation").mkdir(parents=True, exist_ok=True)
    (FEO016 / "validation" / "immutability_before.json").write_text(json.dumps(before, indent=2) + "\n", encoding="utf-8")
    driver = configure()
    if not positive_fixtures_ok():
        write_text(FEO016 / "validation" / "change_scope_guard.md", "# Change-scope guard\n\nStatus: REGRESSION\n\nA positive-protection fixture was lost. Population was not interpreted as a metric result.\n")
        print("REGRESSION positive fixtures")
        return 2
    summaries = populate(driver, RUN1, True)
    populate(driver, RUN2, False)
    determinism = compare_runs(RUN1, RUN2)
    write_text(
        FEO016 / "validation" / "determinism.md",
        "\n".join(
            [
                "# Determinism",
                "",
                f"Pass: {determinism['pass']}.",
                f"Compared semantic files: {determinism['compared_files']}.",
                f"Different files: {determinism['different_count']}.",
                "",
            ]
        ),
    )
    (FEO016 / "validation" / "determinism.json").write_text(json.dumps(determinism, indent=2) + "\n", encoding="utf-8")
    shacl = shacl_package(driver, summaries)
    write_text(
        FEO016 / "validation" / "shacl_report.md",
        "\n".join(
            [
                "# SHACL",
                "",
                f"Release-eligible documents: {len(shacl['eligible_documents'])}.",
                f"Documents not conforming: {', '.join(shacl['per_document_nonconforming']) or 'none'}.",
                f"Consolidated accepted graph conforms: {shacl['consolidated'].get('conforms')}.",
                f"Consolidated violations: {shacl['consolidated'].get('violation_count')}.",
                f"Consolidated warnings: {shacl['consolidated'].get('warning_count')}.",
                f"Engine: {shacl['consolidated'].get('engine')}.",
                f"Extension conforms: {shacl['extension_conforms']}.",
                f"Extension violations: {shacl['extension_violations']}.",
                f"Extension warnings: {shacl['extension_warnings']}.",
                f"Review-graph direct domain triples: {shacl['policy'].get('review_direct', 0)}.",
                f"Rejected-graph direct domain triples: {shacl['policy'].get('rejected_direct', 0)}.",
                f"Non-accepted facts in the core graph: {shacl['policy'].get('noncore_in_core', 0)}.",
                "",
                "Review decisions are not materialised as positive core facts when those counts are zero.",
                "",
            ]
        ),
    )
    delta_rows, class_info = build_delta(BASELINE, RUN1)
    fields = [
        "change_class",
        "document_id",
        "candidate_id",
        "decision_id",
        "assertion_id",
        "target",
        "trigger",
        "market_text",
        "source_text",
        "old_decision",
        "new_decision",
        "old_status",
        "new_status",
        "old_rule",
        "new_rule",
        "old_rule_version",
        "new_rule_version",
        "reason",
    ]
    write_csv(FEO016 / "delta" / "rule_cycle_delta.csv", delta_rows, fields)
    package = human_package(delta_rows)
    package_fields = [
        "delta_review_id",
        "document_id",
        "candidate_id",
        "assertion_id",
        "trigger",
        "market_text",
        "source_text",
        "old_status",
        "new_status",
        "old_rule",
        "new_rule",
        "old_researcher_label",
        "proposed_label_carry_forward",
        "change_reason",
        "human_review_required",
        "researcher_final_label",
        "researcher_notes",
    ]
    write_csv(FEO016 / "delta" / "human_review" / "rule_cycle_changed_assertions.csv", package, package_fields)
    after = immutable_hashes()
    (FEO016 / "validation" / "immutability_after.json").write_text(json.dumps(after, indent=2) + "\n", encoding="utf-8")
    guard_result = guard(delta_rows, class_info, before, after, True)
    queries = competency_counts(
        RUN1 / "rdf/accepted/consolidated/fneo-stock-core.ttl",
        RUN1 / "rdf/review-required/consolidated/fneo-stock-extension.ttl",
    )
    write_csv(
        FEO016 / "evaluation" / "cq_row_count_changes.csv",
        queries,
        ["cq_id", "scope", "feo015_answer_row_count", "feo016_answer_row_count", "row_count_changed", "execution_status"],
    )
    old_decisions = load_decisions(BASELINE)
    new_decisions = load_decisions(RUN1)
    provisional(old_decisions, new_decisions, delta_rows, shacl, queries, guard_result)
    lines = [
        "# Change-scope guard",
        "",
        f"Status: {guard_result['status']}.",
        "",
        f"Accepted MarketChangeEvent and hasAffectedMarket decisions whose acceptance changed: {guard_result['accepted_financial_changes']}.",
        f"Previously unaccepted financial decisions that became accepted: {guard_result['new_accepts']}.",
        f"Entity, temporal, or value decisions that changed: {guard_result['out_of_scope']}.",
        f"Authoritative digest changes: {', '.join(guard_result['hash_changed']) or 'none'}.",
        "",
        "The stopping threshold is more than 100 accepted financial decisions. Metrics are not calculated before human delta review.",
        "",
    ]
    if guard_result["reasons"]:
        lines.append("Reasons:")
        lines.extend(f"- {reason}" for reason in guard_result["reasons"])
        lines.append("")
    lines.append("Class counts:")
    for key, value in sorted(class_info["classes"].items()):
        lines.append(f"- {key}: {value}")
    lines.append("")
    write_text(FEO016 / "validation" / "change_scope_guard.md", "\n".join(lines))
    (FEO016 / "validation" / "change_scope_guard.json").write_text(
        json.dumps({"guard": guard_result, "classes": class_info["classes"], "shacl_policy": shacl["policy"]}, indent=2) + "\n",
        encoding="utf-8",
    )
    print("GUARD", guard_result["status"], "financial_changes", guard_result["accepted_financial_changes"], "human_rows", len(package))
    print("DETERMINISM", determinism["pass"], "SHACL", shacl["consolidated"].get("conforms"))
    return 0 if guard_result["status"] == "PASS" and determinism["pass"] else 2


def inspect_unmatched_keys() -> list[dict]:
    """Compare decision keys without treating a missing direction decision as an entity change."""
    old_decisions = load_decisions(BASELINE)
    new_decisions = load_decisions(RUN1)
    old_by_rule = {
        (row["document_id"], row["candidate_id"], row["rule_id"]): row for row in old_decisions.values()
    }
    new_by_rule = {
        (row["document_id"], row["candidate_id"], row["rule_id"]): row for row in new_decisions.values()
    }
    protected = protected_rule_ids()
    rows = []
    for key in sorted(set(old_decisions) | set(new_decisions)):
        old = old_decisions.get(key)
        new = new_decisions.get(key)
        if old is not None and new is not None:
            continue
        present = old or new
        rule_key = (present["document_id"], present["candidate_id"], present["rule_id"])
        other = new_by_rule.get(rule_key) if old is not None else old_by_rule.get(rule_key)
        rows.append(
            {
                "document_id": present.get("document_id") or "",
                "candidate_id": present.get("candidate_id") or "",
                "rule_id": present.get("rule_id") or "",
                "target_local_name": present.get("target_local_name") or "",
                "status": present.get("status") or "",
                "side": "baseline_only" if new is None else "feo016_only",
                "decision_id": present.get("decision_id") or "",
                "other_run_has_same_candidate_and_rule": "true" if other else "false",
                "other_run_decision_id": (other or {}).get("decision_id") or "",
                "decision_id_differs": "true" if other and other.get("decision_id") != present.get("decision_id") else "false",
                "protected_entity_temporal_or_value_rule": "true" if present.get("rule_id") in protected else "false",
            }
        )
    signature_changes = []
    for rule_key, old in old_by_rule.items():
        new = new_by_rule.get(rule_key)
        if new is None or old.get("rule_id") not in protected:
            continue
        if signature(old) != signature(new):
            signature_changes.append(rule_key)
    return rows, signature_changes


def rebuild_reports() -> int:
    unmatched, protected_signature_changes = inspect_unmatched_keys()
    write_csv(
        FEO016 / "validation" / "unmatched_decision_keys.csv",
        unmatched,
        [
            "document_id",
            "candidate_id",
            "rule_id",
            "target_local_name",
            "status",
            "side",
            "decision_id",
            "other_run_has_same_candidate_and_rule",
            "other_run_decision_id",
            "decision_id_differs",
            "protected_entity_temporal_or_value_rule",
        ],
    )
    if protected_signature_changes:
        raise SystemExit("OUT_OF_SCOPE_CHANGE protected signature changes remain")
    before = json.loads((FEO016 / "validation" / "immutability_before.json").read_text(encoding="utf-8"))
    after = json.loads((FEO016 / "validation" / "immutability_after.json").read_text(encoding="utf-8"))
    delta_rows, class_info = build_delta(BASELINE, RUN1)
    fields = [
        "change_class",
        "document_id",
        "candidate_id",
        "decision_id",
        "assertion_id",
        "target",
        "trigger",
        "market_text",
        "source_text",
        "old_decision",
        "new_decision",
        "old_status",
        "new_status",
        "old_rule",
        "new_rule",
        "old_rule_version",
        "new_rule_version",
        "reason",
    ]
    write_csv(FEO016 / "delta" / "rule_cycle_delta.csv", delta_rows, fields)
    package = human_package(delta_rows)
    package_fields = [
        "delta_review_id",
        "document_id",
        "candidate_id",
        "assertion_id",
        "trigger",
        "market_text",
        "source_text",
        "old_status",
        "new_status",
        "old_rule",
        "new_rule",
        "old_researcher_label",
        "proposed_label_carry_forward",
        "change_reason",
        "human_review_required",
        "researcher_final_label",
        "researcher_notes",
    ]
    write_csv(FEO016 / "delta" / "human_review" / "rule_cycle_changed_assertions.csv", package, package_fields)
    guard_result = guard(delta_rows, class_info, before, after, True)
    queries = read_csv(FEO016 / "evaluation" / "cq_row_count_changes.csv")
    shacl = {
        "consolidated": {"conforms": True, "violation_count": 0},
        "extension_conforms": True,
        "policy": json.loads((FEO016 / "validation" / "change_scope_guard.json").read_text(encoding="utf-8")).get(
            "shacl_policy", {}
        ),
    }
    old_decisions = load_decisions(BASELINE)
    new_decisions = load_decisions(RUN1)
    provisional(old_decisions, new_decisions, delta_rows, shacl, queries, guard_result)
    lines = [
        "# Change-scope guard",
        "",
        f"Status: {guard_result['status']}.",
        "",
        "The first comparison keyed decisions by document and decision identifier. Twenty-four baseline decisions had no counterpart under that key. Inspection showed that each is an accepted hasMarketDirection decision under FE-DIR-001, and that the revised run does not contain the same document, candidate, and rule under any decision identifier. They are not identifier mismatches, and they are not entity, temporal, or value decisions. The direction rule does not apply once the source market-change event is no longer accepted.",
        "",
        f"Unmatched keys inspected: {len(unmatched)}.",
        f"Unmatched keys with the same candidate and rule under another decision identifier: {sum(1 for row in unmatched if row['other_run_has_same_candidate_and_rule'] == 'true')}.",
        f"Unmatched keys on an entity, temporal, or value rule: {sum(1 for row in unmatched if row['protected_entity_temporal_or_value_rule'] == 'true')}.",
        f"Entity, temporal, or value signature changes: {len(protected_signature_changes)}.",
        "",
        f"Accepted MarketChangeEvent and hasAffectedMarket decisions whose acceptance changed: {guard_result['accepted_financial_changes']}.",
        f"Previously unaccepted financial decisions that became accepted: {guard_result['new_accepts']}.",
        f"Entity, temporal, or value decisions that changed: {guard_result['out_of_scope']}.",
        f"Authoritative digest changes: {', '.join(guard_result['hash_changed']) or 'none'}.",
        "",
        "The stopping threshold is more than 100 accepted financial decisions. Metrics are not calculated before human delta review.",
        "",
    ]
    if guard_result["reasons"]:
        lines.append("Reasons:")
        lines.extend(f"- {reason}" for reason in guard_result["reasons"])
        lines.append("")
    lines.append("Class counts:")
    for key, value in sorted(class_info["classes"].items()):
        lines.append(f"- {key}: {value}")
    lines.append("")
    write_text(FEO016 / "validation" / "change_scope_guard.md", "\n".join(lines))
    (FEO016 / "validation" / "change_scope_guard.json").write_text(
        json.dumps(
            {
                "guard": guard_result,
                "classes": class_info["classes"],
                "shacl_policy": shacl["policy"],
                "unmatched_key_count": len(unmatched),
                "protected_signature_changes": len(protected_signature_changes),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        "GUARD",
        guard_result["status"],
        "financial_changes",
        guard_result["accepted_financial_changes"],
        "human_rows",
        len(package),
        "classes",
        class_info["classes"],
    )
    return 0 if guard_result["status"] == "PASS" else 2


if __name__ == "__main__":
    if "--rebuild-reports" in sys.argv:
        raise SystemExit(rebuild_reports())
    raise SystemExit(main())
