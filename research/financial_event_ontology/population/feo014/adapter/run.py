"""Run the one-document adapter twice and write the review artefacts."""

from __future__ import annotations

import copy
import csv
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapter.checks import (  # noqa: E402
    ontology_profile,
    prohibited_identifier_audit,
    public_term_audit,
    reasoner_check,
    validate_accepted,
)
from adapter.common import dump_json, sha256_file  # noqa: E402
from adapter.extraction.extractor import (  # noqa: E402
    extract,
    feo010_root,
    load_config,
    selected_document_id,
)
from adapter.materialisation.materialise import materialise  # noqa: E402
from adapter.normalisation.normalise import (  # noqa: E402
    attach_accepted_markets,
    ensure_engine_path,
    normalise,
)
from adapter.safety.guards import repo_root  # noqa: E402

FINANCIAL_PREFIXES = ("FE-", "VAL-", "TMP-ANCHOR", "QA-")
EXCLUDED_RULES = {"FE-UNMATCHED-001", "NM-SCOPE-001"}
COMPARE_EXCLUDE = {
    "FEO010_TASK_MANIFEST.json",
    "FEO010_ADAPTER_REVIEW_PACKAGE.md",
    "evaluation/determinism_report.md",
    "reports/run_clock.json",
}


def _engine():
    ensure_engine_path()
    from engine.engine import EnrichmentEngine
    from engine.rdf_emitter import emit_profile
    from engine.rule_loader import iter_rule_files

    return EnrichmentEngine, emit_profile, iter_rule_files


def _validate_candidates(candidates: list[dict]) -> None:
    import jsonschema

    schema_path = (
        repo_root()
        / "research"
        / "financial_event_ontology"
        / "enrichment"
        / "feo009"
        / "rules"
        / "schemas"
        / "normalised_candidate.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    for candidate in candidates:
        jsonschema.validate(candidate, schema)


def _validate_records(bundle: dict) -> list[str]:
    import jsonschema

    schema_dir = ROOT / "adapter" / "extraction" / "schemas"
    mapping = {
        "document": "document_record.schema.json",
        "sentence": "sentence_record.schema.json",
        "mention": "mention_record.schema.json",
        "canonical_entity": "canonical_entity_record.schema.json",
        "canonical_event": "canonical_event_record.schema.json",
        "participant": "participant_record.schema.json",
        "time": "time_record.schema.json",
        "temporal_relation": "temporal_relation_record.schema.json",
        "value": "value_record.schema.json",
        "evidence": "evidence_record.schema.json",
    }
    errors = []
    groups = {
        "document": bundle["documents"],
        "sentence": bundle["sentences"],
        "mention": bundle["mentions"],
        "canonical_entity": bundle["canonical_entities"],
        "canonical_event": bundle["canonical_events"],
        "participant": bundle["participants"],
        "time": bundle["times"],
        "temporal_relation": bundle["temporal_relations"],
        "value": bundle["values"],
        "evidence": bundle["evidence"],
    }
    for kind, records in groups.items():
        schema = json.loads((schema_dir / mapping[kind]).read_text(encoding="utf-8"))
        for record in records:
            try:
                jsonschema.validate(record, schema)
            except jsonschema.ValidationError as exc:
                errors.append(f"{record.get('source_record_id')}: {exc.message}")
                if len(errors) > 12:
                    return errors
    return errors


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def _financial(decision: dict) -> bool:
    if decision.get("profile") != "CORE_DETERMINISTIC":
        return False
    if decision.get("status") not in {"accepted", "requires_review"}:
        return False
    rule_id = decision.get("rule_id") or ""
    if rule_id in EXCLUDED_RULES or rule_id.startswith("STR-"):
        return False
    return rule_id.startswith(FINANCIAL_PREFIXES)


def _excerpt(text: str, limit: int = 240) -> str:
    return " ".join(str(text or "").split())[:limit]


def _candidate_map(candidates: list[dict]) -> dict:
    return {item["candidate_id"]: item for item in candidates}


def _write_traces(decisions: list[dict], candidates: list[dict], shacl: dict, destination: Path) -> int:
    by_id = _candidate_map(candidates)
    destination.mkdir(parents=True, exist_ok=True)
    for old in destination.glob("*.md"):
        old.unlink()
    count = 0
    for decision in decisions:
        if not _financial(decision):
            continue
        candidate = by_id.get(decision["candidate_id"], {})
        features = candidate.get("features") or {}
        safe = "".join(char if char.isalnum() or char in "._-" else "_" for char in decision["decision_id"])
        focus = decision.get("subject_iri") or ""
        shacl_line = (
            f"Graph-level core SHACL conforms={shacl.get('conforms')}, "
            f"violations={shacl.get('violation_count')}, warnings={shacl.get('warning_count')}."
        )
        for item in shacl.get("violations") or []:
            if focus and focus in json.dumps(item):
                shacl_line += " A violation result mentions this subject."
                break
        lines = [
            f"# {decision['decision_id']}",
            "",
            f"1. Public assertion: {decision.get('assertion_iri') or decision.get('subject_iri') or ''}",
            f"2. Status: {decision.get('status')}",
            f"3. Source document ID: {decision.get('document_id')}",
            f"4. Source event or entity ID: {', '.join(decision.get('source_annotation_ids') or candidate.get('source_annotation_ids') or [])}",
            f"5. Source text excerpt: {_excerpt(candidate.get('textual_evidence') or candidate.get('trigger_or_lexical_form'))}",
            f"6. Token span: {candidate.get('token_start')} {candidate.get('token_end')}",
            f"7. Character span: {candidate.get('character_start')} {candidate.get('character_end')}",
            f"8. Source event or entity type: {candidate.get('generic_type') or ''}",
            f"9. Generic participant evidence: {', '.join(features.get('evidence_layers') or [])}",
            f"10. Source role: {', '.join(decision.get('source_roles_preserved') or candidate.get('source_roles') or [])}",
            f"11. FEO-009 rule: {decision.get('rule_id')} {decision.get('rule_version')}",
            f"12. Rule conditions satisfied: {', '.join(decision.get('satisfied_conditions') or [])}",
            f"13. Negative conditions checked: {', '.join(decision.get('negative_conditions_checked') or [])}",
            f"14. Confidence score: {decision.get('confidence')}",
            f"15. Direct-triple eligibility: {decision.get('direct_triple_eligible')}",
            f"16. Qualified assertion IRI: {decision.get('assertion_iri') or ''}",
            f"17. SHACL result: {shacl_line}",
            f"18. Manual-review reason: {decision.get('manual_review_reason') or ''}",
            "",
            "Negative conditions that fired: " + ", ".join(decision.get("negative_conditions_fired") or []) + ".",
            "",
            decision.get("explanation") or "",
            "",
        ]
        (destination / f"{safe}.md").write_text("\n".join(lines), encoding="utf-8")
        count += 1
    return count


def _metrics(bundle: dict, normalised: dict, result: dict, shacl: dict, materialised: dict) -> list[dict]:
    decisions = result["decisions"]
    core = [item for item in decisions if item.get("profile") == "CORE_DETERMINISTIC"]
    status_counts = Counter(item["status"] for item in core)
    accepted = [item for item in core if item["status"] == "accepted" and item.get("direct_triple_eligible")]
    def count_target(name: str) -> int:
        return sum(1 for item in accepted if item.get("target_local_name") == name)

    mention_with_token = sum(1 for item in bundle["mentions"] if item.get("token_start") is not None)
    mention_with_char = sum(1 for item in bundle["mentions"] if item.get("character_start") is not None)
    missing_ids = sum(1 for group in ("mentions", "canonical_entities", "canonical_events", "values", "times") for item in bundle[group] if not item.get("source_identifier"))
    duplicate_candidates = sum(1 for row in normalised["deduplication"] if row["operational_path_count"] > 1)
    rows = [
        ("source_node_or_relation_records", sum(len(bundle[key]) for key in ("documents", "sentences", "tokens", "mentions", "canonical_entities", "canonical_events", "participants", "times", "temporal_relations", "values", "evidence"))),
        ("candidates_entity", sum(1 for item in normalised["candidates"] if item["candidate_kind"] == "entity_candidate")),
        ("candidates_event", sum(1 for item in normalised["candidates"] if item["candidate_kind"] == "event_candidate")),
        ("candidates_participation", sum(1 for item in normalised["candidates"] if item["candidate_kind"] == "participation_candidate")),
        ("candidates_temporal", sum(1 for item in normalised["candidates"] if item["candidate_kind"] == "temporal_candidate")),
        ("candidates_value", sum(1 for item in normalised["candidates"] if item["candidate_kind"] == "value_candidate")),
        ("candidates_evidence", sum(1 for item in normalised["candidates"] if item["candidate_kind"] == "evidence_candidate")),
        ("decisions_total", len(decisions)),
        ("decisions_accepted", status_counts["accepted"]),
        ("decisions_requires_review", status_counts["requires_review"]),
        ("decisions_rejected", status_counts["rejected"]),
        ("decisions_out_of_scope", status_counts["out_of_scope"]),
        ("decisions_insufficient_evidence", status_counts["insufficient_evidence"]),
        ("decisions_suppressed", status_counts["suppressed"]),
        ("accepted_market_index", count_target("MarketIndex")),
        ("accepted_equity_market", count_target("EquityMarket")),
        ("accepted_market_change_event", count_target("MarketChangeEvent")),
        ("accepted_has_affected_market", count_target("hasAffectedMarket")),
        ("accepted_explicit_event_time", count_target("hasEventTime")),
        ("accepted_numerical_value", count_target("NumericalValue")),
        ("accepted_percentage_value", count_target("PercentageValue")),
        ("review_required_assertions", status_counts["requires_review"]),
        ("rejected_assertions", status_counts["rejected"] + status_counts["out_of_scope"] + status_counts["insufficient_evidence"] + status_counts["suppressed"]),
        ("unmapped_tlink_records", sum(1 for item in bundle["temporal_relations"] if item["relationship_type"] == "TLINK")),
        ("shacl_violations", shacl["violation_count"]),
        ("shacl_warnings", shacl["warning_count"]),
        ("shacl_information_results", shacl["info_count"]),
        ("evidence_records", len(bundle["evidence"])),
        ("token_span_mentions", mention_with_token),
        ("character_span_mentions", mention_with_char),
        ("mention_records", len(bundle["mentions"])),
        ("missing_source_identifiers", missing_ids),
        ("duplicate_operational_paths", duplicate_candidates),
        ("materialisation_errors", len(materialised["review_direct_triples"]) + len(materialised["rejected_direct_triples"]) + len(materialised["experimental_direct_triples"])),
    ]
    return [{"metric": name, "value": value, "notes": "Smoke-test count. Not precision, recall, or F1."} for name, value in rows]


def _gaps(bundle: dict, normalised: dict, result: dict, shacl: dict, materialised: dict) -> list[dict]:
    document_id = bundle["document_id"]
    rows = [
        {
            "gap_id": "GAP-TLINK-001",
            "layer": "temporal",
            "source_structure": "TLINK",
            "expected_mapping": "No core order triple in this smoke test",
            "observed_issue": "Ordering links were extracted for diagnosis and were not normalised, because extension temporal facts are disabled.",
            "severity": "informational",
            "document_id": document_id,
            "candidate_ids": "",
            "rule_ids": "",
            "workaround": "Diagnostic report only",
            "requires_feo009_change": "no",
            "requires_ontology_change": "no",
            "recommended_action": "Keep ordering links out of the core graph until an extension profile is explicitly enabled.",
            "notes": f"rows={sum(1 for item in bundle['temporal_relations'] if item['relationship_type'] == 'TLINK')}",
        },
        {
            "gap_id": "GAP-FRAME-001",
            "layer": "mention",
            "source_structure": "FrameArgument",
            "expected_mapping": "Not an entity mention",
            "observed_issue": "Frame-argument nodes were excluded from entity-mention records.",
            "severity": "informational",
            "document_id": document_id,
            "candidate_ids": "",
            "rule_ids": "",
            "workaround": "Align a frame argument with an entity only through REFERS_TO",
            "requires_feo009_change": "no",
            "requires_ontology_change": "no",
            "recommended_action": "Retain the exclusion.",
            "notes": f"count={bundle['observed_counts'].get('frame_argument_count')}",
        },
        {
            "gap_id": "GAP-MENTION-001",
            "layer": "materialisation",
            "source_structure": "additional mentions of one canonical record",
            "expected_mapping": "One mention IRI per textual mention",
            "observed_issue": "The enrichment emitter materialises one mention IRI from each candidate. Additional mention identifiers remain on the candidate.",
            "severity": "moderate",
            "document_id": document_id,
            "candidate_ids": "",
            "rule_ids": "STR-ENT-001; STR-EVT-001",
            "workaround": "Source records keep every mention identifier",
            "requires_feo009_change": "no",
            "requires_ontology_change": "no",
            "recommended_action": "Decide later whether each mention needs its own candidate before a 30-document run.",
            "notes": "This smoke test does not claim mention-level completeness in RDF.",
        },
    ]
    if shacl["violation_count"]:
        rows.append(
            {
                "gap_id": "GAP-SHACL-001",
                "layer": "validation",
                "source_structure": "accepted RDF",
                "expected_mapping": "Core and supplemental SHACL conformance",
                "observed_issue": f"{shacl['violation_count']} SHACL violations",
                "severity": "important",
                "document_id": document_id,
                "candidate_ids": "",
                "rule_ids": "",
                "workaround": "Violations are recorded and are not repaired in the ontology",
                "requires_feo009_change": "no",
                "requires_ontology_change": "no",
                "recommended_action": "Review the violation report before multi-document population.",
                "notes": "Extension shapes were not applied.",
            }
        )
    if materialised["review_direct_triples"] or materialised["rejected_direct_triples"]:
        rows.append(
            {
                "gap_id": "GAP-MAT-001",
                "layer": "materialisation",
                "source_structure": "review or rejected graph",
                "expected_mapping": "No direct domain triple",
                "observed_issue": "A direct domain triple was found outside the accepted graph.",
                "severity": "blocking",
                "document_id": document_id,
                "candidate_ids": "",
                "rule_ids": "",
                "workaround": "none",
                "requires_feo009_change": "no",
                "requires_ontology_change": "no",
                "recommended_action": "Do not treat the run as valid until the partition is corrected.",
                "notes": "",
            }
        )
    unresolved = sum(1 for row in normalised["deduplication"] if row["deduplication_decision"] == "unresolved_not_emitted")
    if unresolved:
        rows.append(
            {
                "gap_id": "GAP-PART-001",
                "layer": "participant",
                "source_structure": "EVENT_PARTICIPANT or frame/legacy participant",
                "expected_mapping": "One participation candidate when both endpoints resolve",
                "observed_issue": f"{unresolved} operational paths were not emitted because an endpoint did not resolve",
                "severity": "moderate",
                "document_id": document_id,
                "candidate_ids": "",
                "rule_ids": "FE-AFF-001",
                "workaround": "The paths remain in the deduplication table",
                "requires_feo009_change": "no",
                "requires_ontology_change": "no",
                "recommended_action": "Inspect unresolved endpoint types before a 30-document run.",
                "notes": "",
            }
        )
    rule_anchors = sum(
        1
        for item in bundle["temporal_relations"]
        if item["relationship_type"] == "HAS_TIME_ANCHOR"
        and str((item.get("source_properties") or {}).get("source_kind") or "").lower() == "rule"
    )
    if rule_anchors:
        rows.append(
            {
                "gap_id": "GAP-TIME-001",
                "layer": "temporal",
                "source_structure": "HAS_TIME_ANCHOR",
                "expected_mapping": "Explicit event-time anchor only",
                "observed_issue": f"{rule_anchors} HAS_TIME_ANCHOR rows have source kind rule and were not treated as explicit anchors",
                "severity": "important",
                "document_id": document_id,
                "candidate_ids": "",
                "rule_ids": "TMP-ANCHOR-001",
                "workaround": "The rows remain in the temporal diagnostic and are not accepted direct triples",
                "requires_feo009_change": "no",
                "requires_ontology_change": "no",
                "recommended_action": "Do not report rule-attached anchors as explicit event time.",
                "notes": "Operational source is a T1 rule attachment, not an explicit temporal link.",
            }
        )
    extension = len(result["by_profile"].get("EXTENSION_REVIEWED") or [])
    if extension:
        rows.append(
            {
                "gap_id": "GAP-EXT-001",
                "layer": "profile",
                "source_structure": "extension-profile decisions",
                "expected_mapping": "Disabled for the first core run",
                "observed_issue": f"{extension} extension-profile decisions were retained in JSON and were not materialised",
                "severity": "informational",
                "document_id": document_id,
                "candidate_ids": "",
                "rule_ids": "",
                "workaround": "Experimental and extension Turtle graphs are empty",
                "requires_feo009_change": "no",
                "requires_ontology_change": "no",
                "recommended_action": "Leave extension facts disabled until a separate profile run is requested.",
                "notes": "",
            }
        )
    return rows


def _temporal_report(bundle: dict, result: dict) -> str:
    relations = bundle["temporal_relations"]
    tlinks = [item for item in relations if item["relationship_type"] == "TLINK"]
    anchors = [item for item in relations if item["relationship_type"] == "HAS_TIME_ANCHOR"]
    core = [item for item in result["decisions"] if item.get("profile") == "CORE_DETERMINISTIC"]
    def lines_for(status: str, target: str) -> list[str]:
        matched = [item for item in core if item.get("status") == status and item.get("target_local_name") == target]
        return [f"- {item['candidate_id']} {item['rule_id']} {item.get('manual_review_reason') or ''}".rstrip() for item in matched]
    parts = [
        "# Temporal diagnostic",
        "",
        "This note separates operational temporal links from accepted core event-time anchors.",
        "Raw TLINK totals are not accepted temporal facts.",
        "No inferred inverse was materialised because a reasoner could entail it.",
        "",
        f"Operational TLINK rows extracted: {len(tlinks)}",
        f"HAS_TIME_ANCHOR rows extracted: {len(anchors)}",
        f"CREATED_ON rows extracted: {sum(1 for item in relations if item['relationship_type'] == 'CREATED_ON')}",
        "",
        "## Accepted event-time anchors",
        "",
        *(lines_for("accepted", "hasEventTime") or ["- none"]),
        "",
        "## Review-required anchors",
        "",
        *(lines_for("requires_review", "hasEventTime") or ["- none"]),
        "",
        "## Suppressed candidates",
        "",
        *(
            [
                f"- {item['candidate_id']} {item['rule_id']}"
                for item in core
                if item.get("status") == "suppressed"
            ]
            or ["- none"]
        ),
        "",
        "## Ineligibility",
        "",
        "Ordering TLINK rows were not submitted to the enrichment engine.",
        "The extension temporal profile is disabled for this core smoke test.",
        "A creation-time anchor is publication time and was not normalised as event time.",
        "",
    ]
    return "\n".join(parts) + "\n"


def _enrichment_report(result: dict, rule_checksums: dict) -> str:
    decisions = result["decisions"]
    counts = Counter((item.get("profile"), item.get("status")) for item in decisions)
    lines = [
        "# Enrichment execution",
        "",
        "The existing FEO-009 engine was imported and executed. Rule logic was not copied into this adapter.",
        "",
        f"Engine mapping version: {result.get('mapping_version')}",
        f"Candidate count: {len(result.get('candidates') or [])}",
        f"Decision count: {len(decisions)}",
        "",
        "## Decisions",
        "",
    ]
    for key in sorted(counts):
        lines.append(f"- {key[0]} {key[1]}: {counts[key]}")
    lines.extend(["", "## Rule file checksums", ""])
    for name, digest in rule_checksums.items():
        lines.append(f"- {name}: {digest}")
    lines.append("")
    return "\n".join(lines)


def _git(args: list[str]) -> str:
    completed = subprocess.run(["git", *args], cwd=repo_root(), check=False, capture_output=True, text=True)
    return (completed.stdout or "").strip()


def execute_once() -> dict:
    config = load_config()
    document_id = selected_document_id()
    extraction = extract(config)
    bundle = extraction["bundle"]
    record_errors = _validate_records(bundle)
    if record_errors:
        raise RuntimeError("Source records failed schema validation: " + "; ".join(record_errors[:8]))
    corpus = str(config.get("corpus_key") or "meantime-en-stock")
    normalised = normalise(bundle, corpus)
    _validate_candidates(normalised["candidates"])
    EnrichmentEngine, emit_profile, iter_rule_files = _engine()
    engine = EnrichmentEngine()
    publication = normalised["publication"] or {}
    envelope = {
        "fixture_id": "feo010-doc-" + document_id,
        "corpus": corpus,
        "documents": [
            {
                "document_id": document_id,
                "label": bundle["documents"][0].get("textual_form") or document_id,
                "publication_lexical": publication.get("lexical") or "",
                "publication_normalised": publication.get("normalised") or "",
                "time_key": "publication",
            }
        ],
        "candidates": normalised["candidates"],
    }
    preliminary = engine.run(copy.deepcopy(envelope))
    attach_notes = attach_accepted_markets(normalised["candidates"], preliminary["decisions"])
    _validate_candidates(normalised["candidates"])
    recorded = engine.run(envelope)
    graphs = materialise(recorded, emit_profile)
    root = feo010_root()
    candidate_dir = root / "candidates" / document_id
    by_kind = {
        "entity_candidates.json": "entity_candidate",
        "event_candidates.json": "event_candidate",
        "participation_candidates.json": "participation_candidate",
        "temporal_candidates.json": "temporal_candidate",
        "value_candidates.json": "value_candidate",
        "evidence_candidates.json": "evidence_candidate",
    }
    for name, kind in by_kind.items():
        dump_json(candidate_dir / name, [item for item in normalised["candidates"] if item["candidate_kind"] == kind])
    dump_json(candidate_dir / "candidates.json", normalised["candidates"])
    dump_json(candidate_dir / "normalisation_warnings.json", normalised["warnings"] + attach_notes)
    _write_csv(
        root / "evaluation" / "participant_deduplication.csv",
        normalised["deduplication"],
        [
            "candidate_id", "event_source_id", "participant_source_id", "primary_layer", "supporting_layers",
            "source_roles", "operational_path_count", "normalised_candidate_count", "deduplication_decision",
            "ambiguity", "notes",
        ],
    )
    decision_dir = root / "decisions" / document_id
    dump_json(decision_dir / "decisions.json", recorded["decisions"])
    dump_json(
        decision_dir / "summary.json",
        {
            "candidate_count": len(recorded["candidates"]),
            "decision_count": len(recorded["decisions"]),
            "by_status": dict(Counter(item["status"] for item in recorded["decisions"])),
            "by_profile": {profile: len(items) for profile, items in recorded["by_profile"].items()},
        },
    )
    (root / "rdf" / "accepted").mkdir(parents=True, exist_ok=True)
    (root / "rdf" / "review-required").mkdir(parents=True, exist_ok=True)
    (root / "rdf" / "rejected").mkdir(parents=True, exist_ok=True)
    (root / "rdf" / "experimental").mkdir(parents=True, exist_ok=True)
    paths = {
        "accepted": root / "rdf" / "accepted" / f"{document_id}-core.ttl",
        "review": root / "rdf" / "review-required" / f"{document_id}-review.ttl",
        "rejected": root / "rdf" / "rejected" / f"{document_id}-rejected.ttl",
        "experimental": root / "rdf" / "experimental" / f"{document_id}-experimental.ttl",
    }
    paths["accepted"].write_text(graphs["accepted"], encoding="utf-8")
    paths["review"].write_text(graphs["review"], encoding="utf-8")
    paths["rejected"].write_text(graphs["rejected"], encoding="utf-8")
    paths["experimental"].write_text(graphs["experimental"], encoding="utf-8")
    ontology = repo_root() / str(config["ontology_ttl"])
    core_shapes = repo_root() / str(config["core_shapes"])
    supplemental = repo_root() / str(config["supplemental_shapes"])
    extension = repo_root() / str(config["extension_shapes"])
    shacl = validate_accepted(graphs["accepted"], ontology, core_shapes, supplemental)
    profile = ontology_profile(ontology)
    terms = public_term_audit(graphs["accepted"], ontology)
    prohibited = prohibited_identifier_audit(graphs["accepted"] + "\n" + graphs["review"] + "\n" + graphs["rejected"])
    reasoner = reasoner_check(graphs["accepted"], ontology)
    rule_checksums = {path.name: sha256_file(path) for path in iter_rule_files()}
    shape_checksums = {
        "core": sha256_file(core_shapes),
        "supplemental": sha256_file(supplemental),
        "extension_not_applied": sha256_file(extension),
    }
    (root / "reports" / "enrichment_execution.md").write_text(_enrichment_report(recorded, rule_checksums), encoding="utf-8")
    (root / "reports" / "temporal_diagnostic.md").write_text(_temporal_report(bundle, recorded), encoding="utf-8")
    trace_count = _write_traces(recorded["decisions"], normalised["candidates"], shacl, root / "reports" / "traces")
    metrics = _metrics(bundle, normalised, recorded, shacl, graphs)
    _write_csv(root / "evaluation" / "adapter_smoke_metrics.csv", metrics, ["metric", "value", "notes"])
    gaps = _gaps(bundle, normalised, recorded, shacl, graphs)
    _write_csv(
        root / "evaluation" / "adapter_gaps.csv",
        gaps,
        [
            "gap_id", "layer", "source_structure", "expected_mapping", "observed_issue", "severity",
            "document_id", "candidate_ids", "rule_ids", "workaround", "requires_feo009_change",
            "requires_ontology_change", "recommended_action", "notes",
        ],
    )
    manifest = {
        "document_id": document_id,
        "population_profile": "CORE_DETERMINISTIC",
        "extension_and_experimental_profiles": "disabled",
        "graphs": {name: str(path.relative_to(repo_root())) for name, path in paths.items()},
        "checksums": {name: sha256_file(path) for name, path in paths.items()},
        "experimental_graph": "empty comment graph; no triples",
        "review_direct_domain_triples": graphs["review_direct_triples"],
        "rejected_direct_domain_triples": graphs["rejected_direct_triples"],
    }
    dump_json(root / "rdf" / "manifests" / f"{document_id}-dataset-manifest.json", manifest)
    dump_json(root / "validation" / "shacl_accepted.json", shacl)
    dump_json(root / "validation" / "ontology_profile.json", profile)
    dump_json(root / "validation" / "public_term_audit.json", terms)
    dump_json(root / "validation" / "prohibited_identifier_audit.json", prohibited)
    dump_json(root / "validation" / "reasoner.json", reasoner)
    immutability = {
        "counts_before": extraction["counts_before"],
        "counts_after": extraction["counts_after"],
        "unchanged": extraction["counts_before"] == extraction["counts_after"],
        "container_identity": extraction["container_line"],
        "endpoint": "bolt://127.0.0.1:17688",
        "password": "excluded",
    }
    (root / "validation" / "graph_immutability.md").write_text(
        "\n".join(
            [
                "# Graph immutability",
                "",
                "Read transactions only. No repair was attempted.",
                "",
                f"Endpoint: {immutability['endpoint']}",
                f"Container: {immutability['container_identity']}",
                f"Unchanged: {immutability['unchanged']}",
                "",
                "## Before",
                "",
                "```",
                json.dumps(immutability["counts_before"], indent=2, sort_keys=True),
                "```",
                "",
                "## After",
                "",
                "```",
                json.dumps(immutability["counts_after"], indent=2, sort_keys=True),
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {
        "document_id": document_id,
        "bundle": bundle,
        "normalised": normalised,
        "result": recorded,
        "graphs": graphs,
        "shacl": shacl,
        "profile": profile,
        "terms": terms,
        "prohibited": prohibited,
        "reasoner": reasoner,
        "metrics": metrics,
        "gaps": gaps,
        "trace_count": trace_count,
        "immutability": immutability,
        "rule_checksums": rule_checksums,
        "shape_checksums": shape_checksums,
        "ontology_checksum": extraction["ontology_checksum"],
        "document_ids": extraction["document_ids"],
        "config": {key: value for key, value in config.items() if "password" not in key},
    }


def _fingerprint() -> dict:
    root = feo010_root()
    found = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        if "extracted/raw" in str(path.relative_to(root)):
            continue
        relative = str(path.relative_to(root))
        if relative in COMPARE_EXCLUDE or relative.endswith("adapter-config.toml"):
            continue
        found[relative] = sha256_file(path)
    return found


def _status(stats: dict, determinism_ok: bool) -> str:
    if not stats["immutability"]["unchanged"]:
        return "invalid_graph_changed"
    if stats["shacl"]["violation_count"] or not stats["shacl"]["conforms"]:
        return "validation_failed"
    if stats["prohibited"]["problem_count"] or stats["terms"]["problem_count"]:
        return "validation_failed"
    if stats["graphs"]["review_direct_triples"] or stats["graphs"]["rejected_direct_triples"]:
        return "validation_failed"
    if not determinism_ok:
        return "determinism_failed"
    return "complete"


def _write_final(stats: dict, determinism_ok: bool, differences: list[str]) -> None:
    root = feo010_root()
    metrics = {row["metric"]: row["value"] for row in stats["metrics"]}
    gap_counts = Counter(row["severity"] for row in stats["gaps"])
    (root / "evaluation" / "determinism_report.md").write_text(
        "\n".join(
            [
                "# Determinism",
                "",
                "The one-document adapter was executed twice against the unchanged graph.",
                "Run manifests may contain timestamps. Semantic outputs were compared by SHA-256.",
                "",
                f"Match: {determinism_ok}",
                f"Compared files: {len(_fingerprint())}",
                "",
                "## Differences",
                "",
                *(differences or ["- none"]),
                "",
            ]
        ),
        encoding="utf-8",
    )
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    (root / "reports" / "run_clock.json").write_text(json.dumps({"generated_at": now}, indent=2) + "\n", encoding="utf-8")
    protected = [
        "research/financial_event_ontology/enrichment/feo009",
        "research/financial_event_ontology/ontology/feo007a/ontology/fneo-0.1.0-rc2.ttl",
        "research/financial_event_ontology/mappings/feo008",
        "src/textgraphx/datastore/annotated/corpus_stock",
        "src/textgraphx/datastore/meantime_newsreader_english_raw_NAF/corpus_stock",
        "research/financial_event_ontology/experiments/pipeline_runs/FEO-MASTER-001-STOCK-20261029T232113",
    ]
    git_status = {path: _git(["status", "--short", "--", path]) for path in protected}
    branch = _git(["branch", "--show-current"])
    commit = _git(["rev-parse", "HEAD"])
    status = _status(stats, determinism_ok)
    manifest = {
        "task_id": "FEO-010",
        "date": now,
        "branch": branch,
        "commit": commit,
        "selected_document": stats["document_id"],
        "neo4j_endpoint": "bolt://127.0.0.1:17688",
        "neo4j_password": "excluded",
        "initial_graph_counts": stats["immutability"]["counts_before"],
        "final_graph_counts": stats["immutability"]["counts_after"],
        "ontology_checksum_sha256": stats["ontology_checksum"],
        "shape_checksums": stats["shape_checksums"],
        "mapping_package_version": "feo008-mapping-0.1.0",
        "engine_mapping_version": stats["result"].get("mapping_version"),
        "feo009_rule_checksums": stats["rule_checksums"],
        "commands": [
            "python research/financial_event_ontology/population/feo010/adapter/run.py"
        ],
        "output_checksums": {
            name: sha256_file(root / "rdf" / folder / f"{stats['document_id']}-{suffix}.ttl")
            for name, folder, suffix in (
                ("accepted", "accepted", "core"),
                ("review", "review-required", "review"),
                ("rejected", "rejected", "rejected"),
                ("experimental", "experimental", "experimental"),
            )
        },
        "tests": "pending in this manifest until pytest is recorded",
        "validation": {
            "shacl_conforms": stats["shacl"]["conforms"],
            "shacl_violations": stats["shacl"]["violation_count"],
            "shacl_warnings": stats["shacl"]["warning_count"],
            "shacl_information": stats["shacl"]["info_count"],
            "reasoner": stats["reasoner"],
            "public_term_problems": stats["terms"]["problem_count"],
            "prohibited_identifier_problems": stats["prohibited"]["problem_count"],
            "ontology_profile": stats["profile"],
        },
        "warnings": stats["bundle"]["warnings"] + stats["normalised"]["warnings"],
        "completion_status": status,
        "determinism_match": determinism_ok,
        "protected_path_git_status": git_status,
        "smoke_metrics": metrics,
        "trace_count": stats["trace_count"],
    }
    dump_json(root / "FEO010_TASK_MANIFEST.json", manifest)
    accepted_entities = [
        item["target_local_name"]
        for item in stats["result"]["decisions"]
        if item.get("status") == "accepted" and item.get("direct_triple_eligible") and item.get("target_local_name") in {
            "MarketIndex", "EquityMarket", "CentralBank", "CommercialBank", "Currency", "EquityShare"
        }
    ]
    review = "\n".join(
        [
            "# FEO-010 adapter review",
            "",
            "## 1. Task identity",
            "",
            "FEO-010 is a single-document, read-only smoke test of ontology population for Financial News Event Ontology 0.1.0-rc2.",
            f"Completion status: {status}.",
            "",
            "## 2. Selected document",
            "",
            f"Document {stats['document_id']} was locked before enrichment.",
            "The tie-break was the smallest document identifier among documents meeting the declared corpus criteria.",
            "Results for this document must not be reported as held-out evaluation performance.",
            "",
            "## 3. Database safety",
            "",
            "Endpoint `bolt://127.0.0.1:17688`. Password excluded.",
            f"Container check: {stats['immutability']['container_identity']}",
            "Transactions were read-only. The development endpoint and port 7687 were rejected by the adapter guard.",
            "",
            "## 4. Adapter architecture",
            "",
            "The adapter extracts one document, normalises source records into the FEO-009 candidate schema, and calls the existing enrichment engine.",
            "Rule files were not copied or edited. Extension and experimental profiles were disabled.",
            "",
            "## 5. Source extraction",
            "",
            "Queries were defined in the query manifest before execution and scoped to the selected document, apart from graph-wide safety counts.",
            "",
            "## 6. Source-record counts",
            "",
            f"Records: {metrics.get('source_node_or_relation_records')}.",
            f"Mentions: {metrics.get('mention_records')}. Token spans present on {metrics.get('token_span_mentions')} mentions. Character spans present on {metrics.get('character_span_mentions')} mentions.",
            "",
            "## 7. Normalisation",
            "",
            f"Entity candidates: {metrics.get('candidates_entity')}. Event candidates: {metrics.get('candidates_event')}. Participation candidates: {metrics.get('candidates_participation')}.",
            f"Temporal candidates: {metrics.get('candidates_temporal')}. Value candidates: {metrics.get('candidates_value')}. Evidence candidates: {metrics.get('candidates_evidence')}.",
            "Financial classes were not assigned in the normalisation layer.",
            "",
            "## 8. Participant deduplication",
            "",
            "EVENT_PARTICIPANT is the primary layer. HAS_FRAME_ARGUMENT is supporting. Legacy PARTICIPANT is diagnostic.",
            f"Merged operational paths: {metrics.get('duplicate_operational_paths')}.",
            "An argument label was not treated as a financial role.",
            "",
            "## 9. FEO-009 execution",
            "",
            f"Mapping version recorded by the engine: {stats['result'].get('mapping_version')}.",
            "A first engine call classified entities. Accepted market identifiers were then copied onto existing primary participant paths, and the recorded call followed.",
            "",
            "## 10. Decision summary",
            "",
            f"Decisions: {metrics.get('decisions_total')}. Accepted: {metrics.get('decisions_accepted')}. Requires review: {metrics.get('decisions_requires_review')}. Rejected: {metrics.get('decisions_rejected')}.",
            f"Out of scope: {metrics.get('decisions_out_of_scope')}. Insufficient evidence: {metrics.get('decisions_insufficient_evidence')}. Suppressed: {metrics.get('decisions_suppressed')}.",
            "",
            "## 11. RDF materialisation",
            "",
            "Accepted, review-required, rejected, and experimental graphs were written separately.",
            "The experimental graph has no triples.",
            "",
            "## 12. Identifier audit",
            "",
            f"Public-term problems: {stats['terms']['problem_count']}. Prohibited-identifier problems: {stats['prohibited']['problem_count']}.",
            "Public IRIs use the FEO-008 resource templates as implemented by the enrichment engine.",
            "Canonical event identifiers from the operational graph are source annotation literals, not IRI segments.",
            "",
            "## 13. Temporal mapping",
            "",
            f"Accepted explicit event-time anchors: {metrics.get('accepted_explicit_event_time')}.",
            "Ordering TLINK rows were not emitted as accepted facts.",
            "",
            "## 14. Value mapping",
            "",
            f"Accepted numerical values: {metrics.get('accepted_numerical_value')}. Accepted percentage values: {metrics.get('accepted_percentage_value')}.",
            "No event-value relation was created from co-presence. Percentage points follow the enrichment engine.",
            "",
            "## 15. Evidence coverage",
            "",
            f"Evidence records: {metrics.get('evidence_records')}. Trace reports: {stats['trace_count']}.",
            "",
            "## 16. SHACL result",
            "",
            f"Core and supplemental shapes, engine {stats['shacl'].get('engine')}: conforms={stats['shacl']['conforms']}, violations={stats['shacl']['violation_count']}, warnings={stats['shacl']['warning_count']}, information={stats['shacl']['info_count']}.",
            "Extension shapes were not applied to the core accepted graph.",
            "",
            "## 17. Reasoner result",
            "",
            stats["reasoner"].get("note") or "",
            f"Ran: {stats['reasoner'].get('ran')}. Unsatisfiable classes reported: {len(stats['reasoner'].get('unsatisfiable_classes') or [])}.",
            "",
            "## 18. Determinism result",
            "",
            f"Semantic output match across two runs: {determinism_ok}.",
            "",
            "## 19. Graph immutability",
            "",
            f"Unchanged: {stats['immutability']['unchanged']}.",
            "",
            "## 20. Adapter gaps",
            "",
            f"Gap counts by severity: {dict(gap_counts)}.",
            "",
            "## 21. Unresolved issues",
            "",
            "Additional mentions of one canonical record are not all materialised as separate mention IRIs.",
            "Ordering temporal links remain outside the core graph.",
            "This document is not a held-out evaluation set.",
            "",
            "## 22. Readiness for multi-document population",
            "",
            "Not ready as a 30-document population. This run is one smoke test and does not estimate corpus precision, recall, or F1.",
            "",
            "## 23. Files created",
            "",
            "Outputs are under `research/financial_event_ontology/population/feo010/`.",
            "",
            "## 24. Recommended next task",
            "",
            "Review the recorded gaps and SHACL results, then decide whether mention cardinality and unresolved participant endpoints need an adapter revision before any multi-document run.",
            "",
            "## Accepted financial entities in this document",
            "",
            ", ".join(f"{name} ({accepted_entities.count(name)})" for name in sorted(set(accepted_entities))) or "none",
            "",
        ]
    )
    (root / "FEO010_ADAPTER_REVIEW_PACKAGE.md").write_text(review, encoding="utf-8")


def main() -> int:
    raise SystemExit(
        "FEO-010A does not rerun extraction. Use corrected_adapter/run_feo010a.py, which reads saved FEO-010 records."
    )
    first = execute_once()
    first_fp = _fingerprint()
    second = execute_once()
    second_fp = _fingerprint()
    differences = [name for name in sorted(set(first_fp) | set(second_fp)) if first_fp.get(name) != second_fp.get(name)]
    determinism_ok = not differences and first["immutability"] == second["immutability"]
    _write_final(second, determinism_ok, [f"- {item}" for item in differences])
    print("document", second["document_id"])
    print("status", _status(second, determinism_ok))
    print("decisions", len(second["result"]["decisions"]))
    print("shacl", second["shacl"]["conforms"], second["shacl"]["violation_count"])
    print("determinism", determinism_ok, len(differences))
    print("graph_unchanged", second["immutability"]["unchanged"])
    return 0 if _status(second, determinism_ok) == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
