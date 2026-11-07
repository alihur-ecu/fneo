"""Run the enrichment engine on fixtures and write the evaluation tables."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

from rdflib import Graph, Literal, URIRef

from engine.constants import FNEO_NS, RDF_TYPE, STATUSES
from engine.engine import EnrichmentEngine
from engine.feo008_adapter import load_feo008_fixtures
from engine.paths import feo009_root
from engine.rdf_emitter import emit_profile
from engine.review_queue import queue_rows, write_queue
from engine.shacl_runner import validate_turtle

RESULT_COLUMNS = [
    "fixture_id",
    "origin",
    "candidate_id",
    "rule_id",
    "status",
    "profile",
    "direct_triple_eligible",
    "expected_status",
    "match",
    "shacl_conforms",
    "materialisation_violation",
]


def load_native_fixtures() -> list[dict]:
    folder = feo009_root() / "fixtures" / "input" / "native"
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(folder.glob("*.json"))]


def _primary_decision(result: dict, candidate_id: str, rule_id: str) -> dict | None:
    matches = [item for item in result["decisions"] if item["candidate_id"] == candidate_id]
    if rule_id:
        for item in matches:
            if item["rule_id"] == rule_id:
                return item
    if not matches:
        return None
    non_structural = [item for item in matches if not str(item["rule_id"]).startswith("STR-")]
    return non_structural[-1] if non_structural else matches[-1]


def _graph_from_ttl(turtle: str) -> Graph:
    graph = Graph()
    if turtle.strip():
        graph.parse(data=turtle, format="turtle")
    return graph


def _direct_issues(turtle: str, decisions: list[dict], expected: dict) -> list[str]:
    graph = _graph_from_ttl(turtle)
    issues = []
    for decision in decisions:
        if not decision.get("predicate_iri") or not decision.get("subject_iri"):
            continue
        subject = URIRef(decision["subject_iri"])
        predicate = URIRef(decision["predicate_iri"])
        if decision.get("object_iri"):
            obj = URIRef(decision["object_iri"])
        elif decision.get("object_lexical"):
            datatype = URIRef(decision["object_datatype"]) if decision.get("object_datatype") else None
            obj = Literal(decision["object_lexical"], datatype=datatype)
        else:
            continue
        present = (subject, predicate, obj) in graph
        if decision.get("status") == "accepted" and decision.get("direct_triple_eligible") and not present:
            issues.append(f"missing direct {decision['rule_id']}")
        if decision.get("status") != "accepted" and present:
            issues.append(f"unaccepted direct {decision['rule_id']} {decision['status']}")
        if decision.get("status") == "accepted" and not decision.get("direct_triple_eligible") and present:
            issues.append(f"accepted without eligibility still direct {decision['rule_id']}")
    for local in expected.get("forbid_predicates") or []:
        predicate = URIRef(FNEO_NS + local)
        if any(True for _triple in graph.triples((None, predicate, None))):
            issues.append("forbidden predicate " + local)
    for local in expected.get("forbid_types") or []:
        class_iri = URIRef(FNEO_NS + local)
        if any(True for _triple in graph.triples((None, URIRef(RDF_TYPE), class_iri))):
            issues.append("forbidden type " + local)
    text = turtle
    for lexical in expected.get("forbid_literals") or []:
        if lexical in text:
            issues.append("forbidden literal " + lexical)
    for lexical in expected.get("require_literals") or []:
        if lexical not in text:
            issues.append("missing literal " + lexical)
    return issues


def _distinct_iris(result: dict, candidate_ids: list[str]) -> bool:
    iris = []
    for candidate_id in candidate_ids:
        for decision in result["decisions"]:
            if decision["candidate_id"] == candidate_id and decision.get("status") == "accepted" and decision.get("subject_iri"):
                iris.append(decision["subject_iri"])
                break
    return len(iris) == len(set(iris)) == len(candidate_ids)


def evaluate(write: bool = True) -> dict:
    engine = EnrichmentEngine()
    fixtures = load_native_fixtures() + load_feo008_fixtures()
    rows = []
    queue_input = []
    shacl_failures = []
    materialisation_failures = []
    mismatches = []
    false_acceptance = []
    false_rejection = []
    status_counts = Counter()
    output_root = feo009_root() / "fixtures" / "output"
    if write:
        output_root.mkdir(parents=True, exist_ok=True)
    for fixture in fixtures:
        first = engine.run(fixture)
        second = engine.run(fixture)
        if json.dumps(first["decisions"], sort_keys=True) != json.dumps(second["decisions"], sort_keys=True):
            mismatches.append({"fixture_id": fixture["fixture_id"], "issue": "nondeterministic decisions"})
        turtles = {}
        shacl_ok = True
        for profile, decisions in first["by_profile"].items():
            if not decisions:
                continue
            turtle = emit_profile(first, profile)
            again = emit_profile(second, profile)
            if turtle != again:
                mismatches.append({"fixture_id": fixture["fixture_id"], "issue": "nondeterministic turtle " + profile})
            turtles[profile] = turtle
            report = validate_turtle(turtle, profile)
            if not report["conforms"]:
                shacl_ok = False
                shacl_failures.append({"fixture_id": fixture["fixture_id"], "profile": profile, "results": report["results"][:8]})
            if write:
                path = output_root / fixture["fixture_id"] / f"{profile}.ttl"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(turtle, encoding="utf-8")
        expected = fixture.get("expected") or {}
        joined = "\n".join(turtles.values())
        issues = []
        for profile, turtle in turtles.items():
            profile_decisions = [item for item in first["decisions"] if item.get("profile") == profile]
            issues.extend(_direct_issues(turtle, profile_decisions, expected))
        if expected.get("distinct_subject_iris") and not _distinct_iris(first, expected["distinct_subject_iris"]):
            issues.append("subject IRIs were not distinct")
        if expected.get("single_participation_decision"):
            parts = [item for item in first["decisions"] if item["candidate_id"] == expected["primary_candidate_id"] and item["rule_id"].startswith("FE-AFF")]
            if len(parts) != 1:
                issues.append(f"participation decisions {len(parts)}")
        if issues:
            materialisation_failures.append({"fixture_id": fixture["fixture_id"], "issues": issues})
        primary = None
        if expected.get("status") != "structural_only":
            primary = _primary_decision(first, expected.get("primary_candidate_id") or "", expected.get("rule_id") or "")
            actual = primary["status"] if primary else "missing"
            rule_id = primary["rule_id"] if primary else ""
            matched = actual == expected.get("status") and (not expected.get("rule_id") or rule_id == expected.get("rule_id"))
            if not matched:
                mismatches.append(
                    {
                        "fixture_id": fixture["fixture_id"],
                        "expected_status": expected.get("status"),
                        "actual_status": actual,
                        "expected_rule": expected.get("rule_id"),
                        "actual_rule": rule_id,
                    }
                )
                if actual == "accepted" and expected.get("status") != "accepted":
                    false_acceptance.append(fixture["fixture_id"])
                if expected.get("status") == "accepted" and actual in {"rejected", "insufficient_evidence", "out_of_scope"}:
                    false_rejection.append(fixture["fixture_id"])
        else:
            matched = True
            actual = "structural_only"
            rule_id = ""
        for item in expected.get("also") or []:
            decision = _primary_decision(first, item["candidate_id"], item.get("rule_id") or "")
            actual_also = decision["status"] if decision else "missing"
            if actual_also != item["status"] or (item.get("rule_id") and (not decision or decision["rule_id"] != item["rule_id"])):
                mismatches.append({"fixture_id": fixture["fixture_id"], "also": item, "actual": actual_also, "rule": decision["rule_id"] if decision else ""})
            if item.get("profile") and decision and decision["profile"] != item["profile"]:
                mismatches.append({"fixture_id": fixture["fixture_id"], "profile": decision["profile"], "expected_profile": item["profile"]})
        for decision in first["decisions"]:
            status_counts[decision["status"]] += 1
            if decision["status"] == "accepted" and not decision.get("evidence_references"):
                materialisation_failures.append({"fixture_id": fixture["fixture_id"], "issues": ["accepted without evidence " + decision["rule_id"]]})
            if decision["status"] == "requires_review" and not decision.get("manual_review_reason"):
                mismatches.append({"fixture_id": fixture["fixture_id"], "issue": "review without reason " + decision["rule_id"]})
        rows.append(
            {
                "fixture_id": fixture["fixture_id"],
                "origin": fixture.get("origin") or "feo009",
                "candidate_id": expected.get("primary_candidate_id") or "",
                "rule_id": rule_id,
                "status": actual,
                "profile": primary["profile"] if primary else "",
                "direct_triple_eligible": primary["direct_triple_eligible"] if primary else False,
                "expected_status": expected.get("status") or "",
                "match": matched and not issues and shacl_ok,
                "shacl_conforms": shacl_ok,
                "materialisation_violation": "; ".join(issues),
            }
        )
        queue_input.append({"decisions": first["decisions"]})
        if write:
            decision_path = output_root / fixture["fixture_id"] / "decisions.json"
            decision_path.parent.mkdir(parents=True, exist_ok=True)
            decision_path.write_text(json.dumps(first["decisions"], indent=2) + "\n", encoding="utf-8")
    summary = {
        "fixture_count": len(fixtures),
        "native_fixture_count": len(load_native_fixtures()),
        "feo008_fixture_count": len(load_feo008_fixtures()),
        "decision_count": sum(status_counts.values()),
        "status_counts": {status: status_counts.get(status, 0) for status in STATUSES},
        "mismatch_count": len(mismatches),
        "false_acceptance": false_acceptance,
        "false_rejection": false_rejection,
        "materialisation_failures": materialisation_failures,
        "shacl_failures": [{"fixture_id": item["fixture_id"], "profile": item["profile"], "messages": [row["message"] for row in item["results"]]} for item in shacl_failures],
        "mismatches": mismatches,
    }
    if write:
        evaluation = feo009_root() / "evaluation"
        evaluation.mkdir(parents=True, exist_ok=True)
        with (evaluation / "rule_fixture_results.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=RESULT_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        write_queue(evaluation / "review_queue.csv", queue_rows(queue_input))
        (evaluation / "evaluation_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    summary = evaluate(write=True)
    print(json.dumps({key: summary[key] for key in ("fixture_count", "decision_count", "status_counts", "mismatch_count", "false_acceptance", "false_rejection")}, indent=2))
    print("shacl", len(summary["shacl_failures"]), "materialisation", len(summary["materialisation_failures"]))
    for item in summary["mismatches"][:30]:
        print(item)
    for item in summary["shacl_failures"][:8]:
        print(item)
    for item in summary["materialisation_failures"][:12]:
        print(item)


if __name__ == "__main__":
    main()
