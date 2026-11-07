"""Run the thirty-document dry population twice and write the review package."""

from __future__ import annotations

import json
import shutil
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from driver.common import (
    APPROVED_URI,
    EXPECTED_DOCUMENTS,
    EXPECTED_NODES,
    EXPECTED_RELATIONSHIPS,
    FEO011,
    FROZEN_RUN,
    REPO,
    ensure_adapter_path,
    protected_hashes,
    sha256_file,
    write_csv,
)
from driver.evaluate import write_population_tables, write_schema_rules_and_gaps, write_temporal_and_values, write_traceability
from driver.extract import (
    SafetyStop,
    extract_document,
    load_bundle,
    load_inventory,
    measure_graph,
    open_verified_session,
    save_bundle,
)
from driver.finish import write_coverage, write_cqs, write_identity, write_review, write_shacl
from driver.package_text import render_package
from driver.populate import failure_summary, process_document, safe_message
from driver.tables import write_candidate_stores, write_consolidated_rdf, write_inventory, write_mention_and_participants, write_processing_status

ensure_adapter_path()
from adapter.common import dump_json, load_flat_toml  # noqa: E402

DATA_DIRS = (
    "extraction",
    "candidates",
    "decisions",
    "rdf",
    "validation",
    "competency_questions",
    "review",
    "evaluation",
    "reports",
    "runs",
)
SEMANTIC_GLOBS = (
    "extraction/per_document/*/documents.json",
    "extraction/per_document/*/sentences.json",
    "extraction/per_document/*/tokens.json",
    "extraction/per_document/*/mentions.json",
    "extraction/per_document/*/canonical_entities.json",
    "extraction/per_document/*/canonical_events.json",
    "extraction/per_document/*/participants.json",
    "extraction/per_document/*/times.json",
    "extraction/per_document/*/temporal_relations.json",
    "extraction/per_document/*/values.json",
    "extraction/per_document/*/evidence.json",
    "extraction/per_document/*/warnings.json",
    "extraction/per_document/*/observed_counts.json",
    "extraction/per_document/*/indexes.json",
    "extraction/per_document/*/query_row_counts.json",
    "extraction/per_document/*/extraction_manifest.json",
    "candidates/per_document/*/*.json",
    "decisions/per_document/*/decisions.json",
    "decisions/per_document/*/summary.json",
    "decisions/per_document/*/participant_groups.json",
    "decisions/per_document/*/unresolved_participants.json",
    "decisions/per_document/*/time_anchors.json",
    "decisions/per_document/*/mention_iris.json",
    "decisions/per_document/*/process_summary.json",
    "rdf/accepted/per_document/*.ttl",
    "rdf/review-required/per_document/*.ttl",
    "rdf/rejected/per_document/*.ttl",
    "rdf/experimental/per_document/*.ttl",
)


def _config() -> dict:
    return load_flat_toml(FEO011 / "configuration/population-config.toml")


def _reset(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for name in DATA_DIRS:
        path = root / name
        if path.exists():
            shutil.rmtree(path)
    for name in ("FEO011_DRY_POPULATION_REVIEW_PACKAGE.md", "FEO011_TASK_MANIFEST.json"):
        path = root / name
        if path.exists() and root.resolve() == FEO011.resolve():
            path.unlink()


def _git() -> dict:
    import subprocess

    def read(args: list[str]) -> str:
        try:
            return subprocess.check_output(args, cwd=REPO, text=True).strip()
        except Exception:
            return ""

    return {"branch": read(["git", "rev-parse", "--abbrev-ref", "HEAD"]), "commit": read(["git", "rev-parse", "HEAD"])}


def _extract_all(session, manifest, inventory: list[dict], root: Path) -> list[str]:
    log = ["FEO-011 read-only query log", f"endpoint={APPROVED_URI}", "password=excluded", ""]
    failed = []
    for index, item in enumerate(inventory, start=1):
        document_id = item["document_id"]
        print(f"FEO-011 extract {index}/{len(inventory)} {document_id}", flush=True)
        extracted = None
        error = None
        for _attempt in (1, 2):
            try:
                extracted = extract_document(session, manifest, document_id)
                error = None
                break
            except SafetyStop:
                raise
            except Exception as exc:
                error = exc
        if error is not None or extracted is None:
            message = safe_message(error or RuntimeError("extraction failed"))
            failed.append(document_id)
            note = root / "extraction" / "per_document" / document_id
            note.mkdir(parents=True, exist_ok=True)
            (note / "extraction_error.txt").write_text(message + "\n", encoding="utf-8")
            log.append(f"{document_id}\textraction_failed")
            continue
        save_bundle(root / "extraction" / "per_document" / document_id, extracted)
        log.extend(extracted["query_log"])
        log.append("")
    destination = root / "extraction/manifests/queries_executed.txt"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(log) + "\n", encoding="utf-8")
    return failed


def _populate_all(inventory: list[dict], root: Path, *, validate_shacl: bool) -> tuple[list[dict], dict]:
    summaries = []
    durations = {}
    for index, item in enumerate(inventory, start=1):
        document_id = item["document_id"]
        print(f"FEO-011 populate {index}/{len(inventory)} {document_id}", flush=True)
        start = time.perf_counter()
        bundle_dir = root / "extraction" / "per_document" / document_id
        if not bundle_dir.is_dir():
            summaries.append(failure_summary(document_id, "Extraction did not produce a source bundle."))
            durations[document_id] = f"{time.perf_counter() - start:.3f}"
            continue
        bundle = load_bundle(bundle_dir, document_id)
        summary = None
        error = None
        for _attempt in (1, 2):
            try:
                summary = process_document(bundle, root, validate_shacl=validate_shacl)
                error = None
                break
            except SafetyStop:
                raise
            except Exception as exc:
                error = exc
        if error is not None or summary is None:
            summary = failure_summary(document_id, safe_message(error or RuntimeError("population failed")))
        durations[document_id] = f"{time.perf_counter() - start:.3f}"
        summaries.append(summary)
    return summaries, durations


def _hashes(root: Path) -> dict[str, str]:
    found = {}
    for pattern in SEMANTIC_GLOBS:
        for path in root.glob(pattern):
            if path.is_file():
                found[str(path.relative_to(root))] = sha256_file(path)
    return found


def _compare(first: Path, second: Path) -> dict:
    left = _hashes(first)
    right = _hashes(second)
    missing = sorted(set(left) - set(right))
    extra = sorted(set(right) - set(left))
    different = sorted(key for key in left.keys() & right.keys() if left[key] != right[key])
    return {
        "pass": not missing and not extra and not different,
        "compared_files": len(left),
        "missing_in_second": missing[:30],
        "extra_in_second": extra[:30],
        "different": different[:30],
        "different_count": len(different),
        "missing_count": len(missing),
        "extra_count": len(extra),
    }


def _write_determinism(root: Path, result: dict) -> None:
    lines = [
        "# Determinism report",
        "",
        "The dry population was executed twice. The comparison covers per-document source records, candidates, decisions, mention IRIs, and per-document RDF.",
        "Manifest timestamps and processing durations were not part of the comparison.",
        "",
        f"Result: {'pass' if result.get('pass') else 'fail'}.",
        f"Files compared: {result.get('compared_files')}.",
        f"Missing in the second pass: {result.get('missing_count')}.",
        f"Extra in the second pass: {result.get('extra_count')}.",
        f"Different checksums: {result.get('different_count')}.",
        "",
    ]
    if result.get("different"):
        lines.append("Differing paths:")
        lines.append("")
        for path in result["different"]:
            lines.append(f"- {path}")
        lines.append("")
    if not result.get("pass"):
        lines.append("Readiness cannot be READY while semantic outputs differ.")
        lines.append("")
    (root / "validation/determinism_report.md").write_text("\n".join(lines), encoding="utf-8")
    dump_json(root / "validation/determinism.json", result)


def _write_immutability(root: Path, before: dict, after: dict, valid: bool, reason: str = "") -> None:
    lines = [
        "# Graph immutability",
        "",
        f"Endpoint: {APPROVED_URI}.",
        f"Frozen run: {FROZEN_RUN}.",
        f"Expected nodes: {EXPECTED_NODES}. Expected relationships: {EXPECTED_RELATIONSHIPS}. Expected documents: {EXPECTED_DOCUMENTS}.",
        "",
        f"Nodes before: {before.get('node_count')}. Nodes after: {after.get('node_count')}.",
        f"Relationships before: {before.get('relationship_count')}. Relationships after: {after.get('relationship_count')}.",
        f"AnnotatedText before: {before.get('annotated_text_count')}. AnnotatedText after: {after.get('annotated_text_count')}.",
        "",
        f"Document identifiers unchanged: {valid}.",
        reason,
        "",
        "The population used read transactions. It did not rerun extraction phases and it did not write to the graph.",
        "",
    ]
    (root / "validation/graph_immutability.md").write_text("\n".join(lines), encoding="utf-8")


def _status_tally(decisions: list[dict], target: str) -> dict:
    rows = [item for item in decisions if item.get("target_local_name") == target]
    return dict(Counter(item.get("status") or "" for item in rows))


def _kind_tally(decisions: list[dict]) -> dict:
    counts = Counter()
    for item in decisions:
        if item.get("target_local_name") != "MarketChangeEvent":
            continue
        if item.get("candidate_set") == "sensitivity":
            counts["sensitivity"] += 1
        elif item.get("candidate_set") == "primary_strict" or item.get("rule_id") in {"FE-MCE-001", "FE-MCE-005"}:
            counts["primary"] += 1
        else:
            counts["other"] += 1
    return dict(counts)


def build_stats(root: Path, summaries: list[dict], decisions: list[dict], context: dict) -> dict:
    profiles = Counter()
    for summary in summaries:
        for name, count in (summary.get("profiles") or {}).items():
            profiles[name] += count
    policy = Counter()
    for summary in summaries:
        for key, value in (summary.get("policy") or {}).items():
            if isinstance(value, int):
                policy[key] += value
    accepted_event_time = sum(1 for item in decisions if item.get("target_local_name") == "hasEventTime" and item.get("status") == "accepted")
    review_event_time = sum(1 for item in decisions if item.get("target_local_name") == "hasEventTime" and item.get("status") == "requires_review")
    affected = _status_tally(decisions, "hasAffectedMarket")
    values = {name: _status_tally(decisions, name) for name in ("NumericalValue", "PercentageValue", "MonetaryAmount", "QuantityValue")}
    event_value_links = sum(1 for item in decisions if item.get("target_local_name") == "hasReportedValue" and item.get("status") == "accepted")
    extension_entities = {name: _status_tally(decisions, name) for name in ("CentralBank", "CommercialBank", "Currency", "EquityShare", "FinancialSystem", "FinancialSector")}
    blockers = []
    if not context.get("immutability"):
        blockers.append("Graph immutability failed.")
    if not context.get("determinism", {}).get("pass"):
        blockers.append("Determinism failed.")
    if context.get("inventory_count") != EXPECTED_DOCUMENTS or len(summaries) != EXPECTED_DOCUMENTS:
        blockers.append("The document scope is not exactly 30.")
    if context.get("mention", {}).get("cross_document_mention_collisions") or any(int((item.get("mention") or {}).get("collisions") or 0) for item in summaries):
        blockers.append("Mention collisions were recorded.")
    if any(int((item.get("mention") or {}).get("duplicate_iris") or 0) for item in summaries):
        blockers.append("Duplicate mention IRIs were recorded.")
    if policy["review_direct"] or policy["rejected_direct"] or policy["same_as"] or policy["noncore_in_core"] or policy["missing_direct"] or policy["missing_qualified"]:
        blockers.append(
            "Accepted materialisation policy failed "
            f"(review direct {policy['review_direct']}, rejected direct {policy['rejected_direct']}, "
            f"sameAs {policy['same_as']}, non-core in core {policy['noncore_in_core']}, "
            f"missing direct {policy['missing_direct']}, missing qualified {policy['missing_qualified']})."
        )
    if context.get("shacl_conforms") is not True:
        blockers.append("The release-eligible accepted core graph has unresolved SHACL violations.")
    if context.get("missing_financial_evidence"):
        blockers.append("Source evidence is missing for accepted financial assertions.")
    warnings = []
    if context.get("shacl_exceptions"):
        warnings.append(
            f"{context.get('shacl_exceptions')} documents have core SHACL violations. "
            "They are excluded from the release-eligible consolidated graph and listed in the exception register. "
            "The violations were not reclassified as warnings."
        )
    if context.get("mention", {}).get("unresolved_rows"):
        warnings.append("Unresolved participant references remain.")
    if accepted_event_time == 0:
        warnings.append("Accepted explicit event-time anchors are zero. The eligibility policy was not weakened.")
    warnings.append("Extension entity candidates remain outside the core profile because the corrected adapter requests CORE_DETERMINISTIC.")
    warnings.append("Independent SHACL confirmation with a second engine was not available.")
    warnings.append("A project-local OWL reasoner was not available.")
    warnings.append("Manual correctness has not been evaluated.")
    if blockers:
        readiness = "NOT_READY_FOR_MANUAL_REVIEW"
    elif warnings:
        readiness = "READY_FOR_MANUAL_REVIEW_WITH_WARNINGS"
    else:
        readiness = "READY_FOR_MANUAL_REVIEW"
    return {
        "readiness": readiness,
        "blockers": blockers,
        "warnings": warnings,
        "experiment_id": context.get("experiment_id"),
        "generated_at": context.get("generated_at"),
        "ontology_sha256": context.get("ontology_sha256"),
        "adapter_version": "feo010a-adapter-0.1.0",
        "mapping_version": "feo008-mapping-0.1.0",
        "rule_version": context.get("rule_version"),
        "endpoint": APPROVED_URI,
        "frozen_run": FROZEN_RUN,
        "container": context.get("container"),
        "inventory_count": context.get("inventory_count"),
        "documents_processed": len(summaries),
        "status_counts": dict(Counter(item.get("status") for item in summaries)),
        "source_records": sum(int(item.get("source_records") or 0) for item in summaries),
        "candidates": sum(int(item.get("candidates") or 0) for item in summaries),
        "decisions": len(decisions),
        "accepted": sum(1 for item in decisions if item.get("status") == "accepted"),
        "review_required": sum(1 for item in decisions if item.get("status") == "requires_review"),
        "rejected": sum(1 for item in decisions if item.get("status") == "rejected"),
        "insufficient_evidence": sum(1 for item in decisions if item.get("status") == "insufficient_evidence"),
        "out_of_scope": sum(1 for item in decisions if item.get("status") == "out_of_scope"),
        "suppressed": sum(1 for item in decisions if item.get("status") == "suppressed"),
        "invalid_candidates": context.get("invalid_candidates"),
        "profile_counts": dict(profiles),
        "market_index": _status_tally(decisions, "MarketIndex"),
        "equity_market": _status_tally(decisions, "EquityMarket"),
        "extension_entities": extension_entities,
        "market_change_kinds": _kind_tally(decisions),
        "market_change_status": _status_tally(decisions, "MarketChangeEvent"),
        "affected_market": {"accepted": affected.get("accepted", 0), "review_required": affected.get("requires_review", 0)},
        "accepted_event_time": accepted_event_time,
        "review_event_time": review_event_time,
        "tlink_count": context.get("tlink_count"),
        "values": values,
        "accepted_event_value_links": event_value_links,
        "missing_financial_evidence": context.get("missing_financial_evidence"),
        "shacl_conforms": context.get("shacl_conforms"),
        "shacl_counts": context.get("shacl_counts"),
        "shacl_exceptions": context.get("shacl_exceptions"),
        "cq_status_counts": context.get("cq_status_counts"),
        "primary_events": context.get("review", {}).get("primary_events"),
        "primary_documents": context.get("review", {}).get("primary_documents"),
        "extension_documents": context.get("review", {}).get("extension_documents"),
        "rejected_rows": context.get("review", {}).get("rejected_rows"),
        "temporal_rows": context.get("review", {}).get("temporal_rows"),
        "gap_severity": context.get("gap_severity"),
        "proposals": context.get("proposals"),
        "determinism": "pass" if context.get("determinism", {}).get("pass") else "fail",
        "nodes_before": context.get("before", {}).get("node_count"),
        "nodes_after": context.get("after", {}).get("node_count"),
        "relationships_before": context.get("before", {}).get("relationship_count"),
        "relationships_after": context.get("after", {}).get("relationship_count"),
        "documents_before": context.get("before", {}).get("annotated_text_count"),
        "documents_after": context.get("after", {}).get("annotated_text_count"),
        "policy": dict(policy),
    }


def _tlink_total(root: Path) -> int:
    total = 0
    for path in (root / "extraction/per_document").glob("*/temporal_relations.json"):
        for row in json.loads(path.read_text(encoding="utf-8")):
            if row.get("relationship_type") == "TLINK":
                total += 1
    return total


def write_outputs(root: Path, inventory: list[dict], summaries: list[dict], durations: dict, context: dict) -> dict:
    graph_ids = set(context["before_ids"])
    write_inventory(root, inventory, summaries, graph_ids)
    write_processing_status(root, summaries, durations)
    mention = write_mention_and_participants(root, summaries)
    write_candidate_stores(root)
    population = write_population_tables(root)
    decisions = population["decisions"]
    candidates = population["candidates"]
    write_temporal_and_values(root, decisions, candidates)
    trace = write_traceability(root, decisions, candidates)
    rules = write_schema_rules_and_gaps(root, summaries, decisions)
    write_identity(root)
    eligible = [item["document_id"] for item in summaries if (item.get("shacl") or {}).get("conforms") is True]
    rdf_info = write_consolidated_rdf(root, eligible)
    core_text = (root / "rdf/accepted/consolidated/fneo-stock-core.ttl").read_text(encoding="utf-8")
    extension_text = (root / "rdf/review-required/consolidated/fneo-stock-extension.ttl").read_text(encoding="utf-8")
    shacl = write_shacl(root, summaries, core_text, extension_text)
    write_coverage(root, decisions, candidates, core_text, extension_text, shacl["consolidated"].get("conforms") is True)
    cqs = write_cqs(root, core_text, extension_text)
    review = write_review(root, decisions, candidates)
    manifest = {
        "graphs": {
            "accepted_core": "rdf/accepted/consolidated/fneo-stock-core.ttl",
            "review_required": "rdf/review-required/consolidated/fneo-stock-review.ttl",
            "extension": "rdf/review-required/consolidated/fneo-stock-extension.ttl",
            "candidate_review": "rdf/review-required/consolidated/fneo-stock-candidate-review.ttl",
            "rejected": "rdf/rejected/fneo-stock-rejected.ttl",
            "experimental_temporal": "rdf/experimental/fneo-stock-temporal-experimental.ttl",
        },
        "profiles": ["CORE_DETERMINISTIC", "EXTENSION_REVIEWED", "CANDIDATE_REVIEW", "EXPERIMENTAL_TEMPORAL"],
        "documents_in_release_eligible_core": eligible,
        "checksums": rdf_info["checksums"],
        "triple_counts": rdf_info["triple_counts"],
        "ontology_version": "0.1.0-rc2",
        "ontology_sha256": context["hashes_before"]["ontology"],
        "mapping_version": "feo008-mapping-0.1.0",
        "rule_version": rules["rule_version"],
        "adapter_version": "feo010a-adapter-0.1.0",
        "licence": "The ontology is licensed CC BY 4.0. Dry-population graphs are research artefacts for manual review and are not a registered release. Short evidence excerpts come from the English stock-market subset of the MEANTIME/NewsReader corpus.",
        "generation_date": context["generated_at"],
        "accepted_versus_candidate_policy": "Accepted core RDF contains only accepted CORE_DETERMINISTIC facts that are direct-triple eligible, together with their qualified assertions. Review, rejected, suppressed, candidate-review, and experimental facts do not enter that graph as positive direct triples.",
        "namespace": "https://w3id.org/fneo/ is provisional and was not registered.",
    }
    dump_json(root / "rdf/manifests/dataset_manifest.json", manifest)
    context.update(
        {
            "mention": mention,
            "invalid_candidates": rules["invalid_candidates"],
            "rule_version": rules["rule_version"],
            "rule_checksums": rules["rule_checksums"],
            "proposals": rules["proposals"],
            "gap_severity": dict(Counter(item["severity"] for item in rules["gaps"])),
            "missing_financial_evidence": trace["missing_financial_evidence"],
            "shacl_conforms": shacl["consolidated"].get("conforms"),
            "shacl_counts": {
                "violations": shacl["consolidated"].get("violation_count"),
                "warnings": shacl["consolidated"].get("warning_count"),
                "information": shacl["consolidated"].get("info_count"),
            },
            "shacl_exceptions": shacl["exception_count"],
            "cq_status_counts": dict(Counter(row["execution_status"] for row in cqs)),
            "review": review,
            "tlink_count": _tlink_total(root),
            "rdf_checksums": rdf_info["checksums"],
            "rdf_counts": rdf_info["triple_counts"],
        }
    )
    return build_stats(root, summaries, decisions, context)


def _policy_from_disk(root: Path, document_id: str) -> dict:
    from driver.populate import _policy

    base = root / "decisions" / "per_document" / document_id
    decisions = json.loads((base / "decisions.json").read_text(encoding="utf-8"))
    candidates = json.loads((root / "candidates" / "per_document" / document_id / "candidates.json").read_text(encoding="utf-8"))
    graphs = {
        "accepted": (root / "rdf/accepted/per_document" / f"{document_id}-core.ttl").read_text(encoding="utf-8"),
        "review": (root / "rdf/review-required/per_document" / f"{document_id}-review.ttl").read_text(encoding="utf-8"),
        "extension": (root / "rdf/review-required/per_document" / f"{document_id}-extension.ttl").read_text(encoding="utf-8"),
        "candidate_review": (root / "rdf/review-required/per_document" / f"{document_id}-candidate-review.ttl").read_text(encoding="utf-8"),
        "rejected": (root / "rdf/rejected/per_document" / f"{document_id}-rejected.ttl").read_text(encoding="utf-8"),
        "experimental": (root / "rdf/experimental/per_document" / f"{document_id}-experimental.ttl").read_text(encoding="utf-8"),
    }
    return _policy({"decisions": decisions, "candidates": candidates}, graphs)


def resume_reports(output: Path | None = None) -> dict:
    """Finish report assembly from the completed semantic passes.

    The two population passes and the immutability measurement have already
    been written. This does not repeat extraction and does not modify the graph.
    """
    output = output or FEO011
    inventory = load_inventory()
    durations = {row["document_id"]: row["duration_seconds"] for row in csv_rows(output / "extraction/manifests/document_processing_status.csv")}
    summaries = []
    for item in inventory:
        document_id = item["document_id"]
        summary = json.loads((output / "decisions/per_document" / document_id / "process_summary.json").read_text(encoding="utf-8"))
        shacl_path = output / "validation/per_document" / f"{document_id}.json"
        shacl = json.loads(shacl_path.read_text(encoding="utf-8")) if shacl_path.is_file() else {}
        summary["shacl"] = shacl
        summary["policy"] = _policy_from_disk(output, document_id)
        summaries.append(summary)
    determinism = json.loads((output / "validation/determinism.json").read_text(encoding="utf-8"))
    hashes = protected_hashes()
    config = _config()
    driver, session, manifest, safety = open_verified_session(config)
    try:
        measured = measure_graph(session, manifest, [item["document_id"] for item in inventory])
    finally:
        session.close()
        driver.close()
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    context = {
        "experiment_id": "FEO-011-DRY-" + generated_at.replace(":", "").replace("-", "").replace("+", ""),
        "generated_at": generated_at,
        "ontology_sha256": hashes["ontology"],
        "hashes_before": hashes,
        "hashes_after": hashes,
        "container": safety.get("container"),
        "inventory_count": len(inventory),
        "before": measured["counts"],
        "after": measured["counts"],
        "before_ids": measured["document_ids"],
        "immutability": (
            measured["counts"]["node_count"] == EXPECTED_NODES
            and measured["counts"]["relationship_count"] == EXPECTED_RELATIONSHIPS
            and measured["counts"]["annotated_text_count"] == EXPECTED_DOCUMENTS
        ),
        "determinism": determinism,
        "git": _git(),
    }
    if not context["immutability"]:
        raise SafetyStop("Graph counts no longer match the frozen inventory.")
    stats = write_outputs(output, inventory, summaries, durations, context)
    (output / "FEO011_DRY_POPULATION_REVIEW_PACKAGE.md").write_text(render_package(stats), encoding="utf-8")
    task_manifest = {
        "task_id": "FEO-011",
        "experiment_id": context["experiment_id"],
        "generated_at": generated_at,
        "branch": context["git"].get("branch"),
        "commit": context["git"].get("commit"),
        "database_endpoint": APPROVED_URI,
        "database_name": "neo4j",
        "password_recorded": False,
        "frozen_run_id": FROZEN_RUN,
        "graph_counts_before": {"node_count": EXPECTED_NODES, "relationship_count": EXPECTED_RELATIONSHIPS, "annotated_text_count": EXPECTED_DOCUMENTS},
        "graph_counts_after": measured["counts"],
        "document_ids": measured["document_ids"],
        "document_inventory_checksum": hashes["document_inventory"],
        "ontology_checksum": hashes["ontology"],
        "shape_checksums": {
            "core": hashes["core_shapes"],
            "supplemental": hashes["supplemental_shapes"],
            "extension": hashes["extension_shapes"],
        },
        "adapter_checksum": hashes["feo010a_adapter"],
        "feo009_rule_checksums": context.get("rule_checksums"),
        "mapping_version": "feo008-mapping-0.1.0",
        "engine_mapping_version": "feo009-enrichment-0.1.0",
        "adapter_version": "feo010a-adapter-0.1.0",
        "population_profile_requested": "CORE_DETERMINISTIC",
        "optional_modules": {"event_coreference": False, "cross_document_merge": False, "llm": False},
        "commands": [
            "python research/financial_event_ontology/population/feo011/scripts/run_feo011.py",
            "python research/financial_event_ontology/population/feo011/scripts/run_feo011.py --reports-only",
        ],
        "output_checksums": context.get("rdf_checksums"),
        "tests": {"status": "pending"},
        "warnings": stats["warnings"],
        "blockers": stats["blockers"],
        "completion_status": stats["readiness"],
        "corpus_version": "MEANTIME/NewsReader English stock-market subset",
        "protected_hashes_before": hashes,
        "protected_hashes_after": hashes,
        "determinism": determinism,
        "report_note": "Semantic passes completed before report assembly. Report assembly was rerun from those saved outputs after a missing output directory was created. Graph counts were measured again at report time.",
    }
    dump_json(output / "FEO011_TASK_MANIFEST.json", task_manifest)
    dump_json(output / "reports/run_summary.json", stats)
    return stats


def csv_rows(path: Path) -> list[dict]:
    import csv

    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def run(output: Path | None = None, *, documents: str = "all", passes: int = 2) -> dict:
    output = output or FEO011
    if output.resolve() == FEO011.resolve() and documents != "all":
        raise SafetyStop("The canonical FEO-011 output must use the full 30-document inventory.")
    if output.resolve() == FEO011.resolve() and passes != 2:
        raise SafetyStop("The canonical FEO-011 output must run two passes.")
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    experiment_id = "FEO-011-DRY-" + generated_at.replace(":", "").replace("-", "").replace("+", "")
    _reset(output)
    inventory = load_inventory()
    if documents != "all":
        wanted = set(documents.split(","))
        inventory = [item for item in inventory if item["document_id"] in wanted]
    hashes_before = protected_hashes()
    if hashes_before["ontology"] != "6e58c94ce6ffcd0f94d7e8257abb5a33f342b567f28438ebca1761fc122b78af":
        _write_immutability(output, {}, {}, False, "Ontology checksum mismatch. Population stopped.")
        raise SafetyStop("Ontology checksum mismatch.")
    config = _config()
    if str(config.get("neo4j_uri")) != APPROVED_URI:
        raise SafetyStop("Configuration URI is not bolt://127.0.0.1:17688.")
    with_session = open_verified_session(config)
    driver, session, manifest, safety = with_session
    try:
        before = measure_graph(session, manifest, [item["document_id"] for item in load_inventory()])
        _extract_all(session, manifest, inventory, output)
        after_extract = measure_graph(session, manifest, [item["document_id"] for item in load_inventory()])
    finally:
        session.close()
        driver.close()
    if before["counts"] != after_extract["counts"] or before["document_ids"] != after_extract["document_ids"]:
        _write_immutability(output, before["counts"], after_extract["counts"], False, "Counts changed during extraction. Run marked invalid.")
        raise SafetyStop("Graph counts changed during extraction.")
    summaries, durations = _populate_all(inventory, output, validate_shacl=True)
    determinism = {"pass": False, "compared_files": 0, "different_count": 0, "missing_count": 0, "extra_count": 0}
    if passes >= 2:
        second = output / "runs" / "run2"
        driver, session, manifest, _safety = open_verified_session(config)
        try:
            _extract_all(session, manifest, inventory, second)
        finally:
            session.close()
            driver.close()
        _populate_all(inventory, second, validate_shacl=False)
        determinism = _compare(output, second)
    driver, session, manifest, _safety = open_verified_session(config)
    try:
        after = measure_graph(session, manifest, [item["document_id"] for item in load_inventory()])
    finally:
        session.close()
        driver.close()
    immutable = before["counts"] == after["counts"] and before["document_ids"] == after["document_ids"]
    _write_immutability(
        output,
        before["counts"],
        after["counts"],
        immutable,
        "" if immutable else "Counts or document identifiers changed. The run is invalid.",
    )
    _write_determinism(output, determinism)
    hashes_after = protected_hashes()
    if hashes_before != hashes_after:
        immutable = False
    context = {
        "experiment_id": experiment_id,
        "generated_at": generated_at,
        "ontology_sha256": hashes_before["ontology"],
        "hashes_before": hashes_before,
        "hashes_after": hashes_after,
        "container": safety.get("container"),
        "inventory_count": len(load_inventory()) if documents == "all" else len(inventory),
        "before": before["counts"],
        "after": after["counts"],
        "before_ids": before["document_ids"],
        "immutability": immutable,
        "determinism": determinism,
        "git": _git(),
    }
    if documents != "all":
        dump_json(output / "reports/smoke_summary.json", {"documents": [item["document_id"] for item in inventory], "status": [item.get("status") for item in summaries]})
        return {"readiness": "SMOKE", "summaries": summaries}
    stats = write_outputs(output, inventory, summaries, durations, context)
    (output / "FEO011_DRY_POPULATION_REVIEW_PACKAGE.md").write_text(render_package(stats), encoding="utf-8")
    manifest = {
        "task_id": "FEO-011",
        "experiment_id": experiment_id,
        "generated_at": generated_at,
        "branch": context["git"].get("branch"),
        "commit": context["git"].get("commit"),
        "database_endpoint": APPROVED_URI,
        "database_name": "neo4j",
        "password_recorded": False,
        "frozen_run_id": FROZEN_RUN,
        "graph_counts_before": before["counts"],
        "graph_counts_after": after["counts"],
        "document_ids": before["document_ids"],
        "document_inventory_checksum": hashes_before["document_inventory"],
        "ontology_checksum": hashes_before["ontology"],
        "shape_checksums": {
            "core": hashes_before["core_shapes"],
            "supplemental": hashes_before["supplemental_shapes"],
            "extension": hashes_before["extension_shapes"],
        },
        "adapter_checksum": hashes_before["feo010a_adapter"],
        "feo009_rule_checksums": context.get("rule_checksums") or stats.get("rule_checksums"),
        "mapping_version": "feo008-mapping-0.1.0",
        "engine_mapping_version": "feo009-enrichment-0.1.0",
        "adapter_version": "feo010a-adapter-0.1.0",
        "population_profile_requested": "CORE_DETERMINISTIC",
        "optional_modules": {"event_coreference": False, "cross_document_merge": False, "llm": False},
        "commands": ["python research/financial_event_ontology/population/feo011/scripts/run_feo011.py"],
        "output_checksums": context.get("rdf_checksums"),
        "tests": {"status": "pending"},
        "warnings": stats["warnings"],
        "blockers": stats["blockers"],
        "completion_status": stats["readiness"],
        "corpus_version": "MEANTIME/NewsReader English stock-market subset",
        "protected_hashes_before": hashes_before,
        "protected_hashes_after": hashes_after,
        "determinism": determinism,
    }
    # rule checksums are attached inside write_outputs via context
    manifest["feo009_rule_checksums"] = context.get("rule_checksums")
    dump_json(output / "FEO011_TASK_MANIFEST.json", manifest)
    dump_json(output / "reports/run_summary.json", stats)
    return stats
