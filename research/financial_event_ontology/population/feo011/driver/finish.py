"""Review package, SHACL reports, coverage, and competency-question previews."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from rdflib import Graph, URIRef

from driver.common import REPO, ensure_adapter_path, excerpt, local_name, write_csv
from driver.evaluate import ENTITY_TARGETS, ORDER_NAMES, VALUE_TARGETS
from driver.tables import (
    CORE_QUERIES,
    DEMONSTRATION_QUERIES,
    EXTENSION_ON_CORE,
    EXTENSION_ON_EXTENSION,
    SPARQL_DIR,
    TEMPORAL_EXTENSION,
    document_dirs,
    load_json,
)

ensure_adapter_path()

from adapter.checks import _shacl, validate_accepted  # noqa: E402

COVERAGE_TARGETS = (
    "FinancialNewsDocument",
    "TextualEvidence",
    "EntityMention",
    "EventMention",
    "TimeMention",
    "Event",
    "TimeEntity",
    "MarketIndex",
    "EquityMarket",
    "MarketChangeEvent",
    "CentralBank",
    "CommercialBank",
    "Currency",
    "EquityShare",
    "FinancialSystem",
    "FinancialSector",
    "NumericalValue",
    "PercentageValue",
    "MonetaryAmount",
    "QuantityValue",
    "hasAffectedMarket",
    "hasEventTime",
    "hasMarketDirection",
    "hasReportedValue",
    "hasParticipant",
    "precedes",
    "follows",
    "simultaneousWith",
    "occursDuring",
)


def write_identity(root: Path) -> int:
    grouped = defaultdict(list)
    shared_ids = defaultdict(list)
    for document_id in document_dirs(root):
        path = root / "extraction/per_document" / document_id / "canonical_entities.json"
        if not path.is_file():
            continue
        for record in load_json(path):
            surface = " ".join(str(record.get("textual_form") or "").split())
            key = surface.casefold()
            if key:
                grouped[key].append((document_id, surface, record))
            source_id = str(record.get("source_identifier") or "")
            if source_id and document_id not in source_id:
                shared_ids[source_id].append((document_id, record))
    rows = []
    for key, members in sorted(grouped.items()):
        documents = sorted({item[0] for item in members})
        if len(documents) < 2:
            continue
        rows.append(
            {
                "match_basis": "same_surface_form",
                "surface_form": members[0][1],
                "generic_type": members[0][2].get("generic_type") or "",
                "document_ids": "|".join(documents),
                "entity_iris": "",
                "source_identifiers": "|".join(sorted({str(item[2].get("source_identifier") or "") for item in members})),
                "owl_sameAs_emitted": "no",
                "notes": "Possible future identity candidate only. No cross-document identity triple is emitted.",
            }
        )
    for source_id, members in sorted(shared_ids.items()):
        documents = sorted({item[0] for item in members})
        if len(documents) < 2:
            continue
        rows.append(
            {
                "match_basis": "same_source_identifier",
                "surface_form": members[0][1].get("textual_form") or "",
                "generic_type": members[0][1].get("generic_type") or "",
                "document_ids": "|".join(documents),
                "entity_iris": "",
                "source_identifiers": source_id,
                "owl_sameAs_emitted": "no",
                "notes": "The frozen graph identifier is not treated as validated identity.",
            }
        )
    write_csv(
        root / "evaluation/cross_document_identity_candidates.csv",
        rows,
        ["match_basis", "surface_form", "generic_type", "document_ids", "entity_iris", "source_identifiers", "owl_sameAs_emitted", "notes"],
    )
    return len(rows)


def write_coverage(root: Path, decisions: list[dict], candidates: list[dict], core_text: str, extension_text: str, core_conforms: bool) -> None:
    ontology = Graph()
    ontology.parse(REPO / "research/financial_event_ontology/ontology/feo007a/ontology/fneo-0.1.0-rc2.ttl", format="turtle")
    ontology_terms = {local_name(str(term)) for term in ontology.all_nodes() if isinstance(term, URIRef)}
    ensure_adapter_path()
    from adapter.normalisation.normalise import ensure_engine_path

    ensure_engine_path()
    from engine.rule_loader import load_rules

    rule_terms = set()
    for rule in load_rules():
        rule_terms.add(local_name(rule.get("target_class") or ""))
        rule_terms.add(local_name(rule.get("target_property") or ""))
    rule_terms.discard("")
    rows = []
    for target in COVERAGE_TARGETS:
        matched = [
            item
            for item in decisions
            if item.get("target_local_name") == target or local_name(item.get("predicate_iri") or "") == target
        ]
        documents = sorted({item.get("document_id") for item in matched if item.get("document_id")})
        accepted = sum(1 for item in matched if item.get("status") == "accepted")
        review = sum(1 for item in matched if item.get("status") == "requires_review")
        rejected = sum(1 for item in matched if item.get("status") == "rejected")
        insufficient = sum(1 for item in matched if item.get("status") == "insufficient_evidence")
        materialised = "yes" if (f"fneo:{target}" in core_text or f"fneo:{target}" in extension_text) else "no"
        rows.append(
            {
                "target_class_or_property": target,
                "candidate_count": len({item.get("candidate_id") for item in matched}),
                "accepted_count": accepted,
                "review_count": review,
                "rejected_count": rejected,
                "insufficient_count": insufficient,
                "document_coverage": len(documents),
                "mapping_defined": "yes" if target in ontology_terms else "no",
                "rule_available": "yes" if target in rule_terms else "no",
                "rdf_materialised": materialised,
                "shacl_conformant": "yes" if core_conforms else "no",
                "manual_review_pending": "true",
                "known_limitation": "Coverage is not correctness. Human labels have not been assigned.",
                "notes": "",
            }
        )
    write_csv(
        root / "evaluation/population_coverage.csv",
        rows,
        [
            "target_class_or_property",
            "candidate_count",
            "accepted_count",
            "review_count",
            "rejected_count",
            "insufficient_count",
            "document_coverage",
            "mapping_defined",
            "rule_available",
            "rdf_materialised",
            "shacl_conformant",
            "manual_review_pending",
            "known_limitation",
            "notes",
        ],
    )


def write_shacl(root: Path, summaries: list[dict], core_text: str, extension_text: str) -> dict:
    rows = []
    exceptions = []
    eligible = []
    engines = set()
    for summary in summaries:
        document_id = summary["document_id"]
        shacl = summary.get("shacl") or {}
        engines.add(shacl.get("engine") or "")
        conforms = shacl.get("conforms")
        if conforms is True:
            eligible.append(document_id)
        elif conforms is False:
            for item in shacl.get("violations") or []:
                exceptions.append(
                    {
                        "document_id": document_id,
                        "severity": "Violation",
                        "shape": item.get("shape") or "",
                        "focus_node": item.get("focus") or "",
                        "message": item.get("message") or "",
                        "included_in_release_eligible_graph": "no",
                        "reason": "A core violation excludes this document from the release-eligible consolidated graph.",
                    }
                )
        results = []
        path = root / "validation/per_document" / f"{document_id}.json"
        if path.is_file():
            results = load_json(path)
            for bucket, severity in (("violations", "Violation"), ("warnings", "Warning"), ("infos", "Info")):
                for item in results.get(bucket) or []:
                    rows.append(
                        {
                            "document_id": document_id,
                            "conforms": results.get("conforms"),
                            "violation_count": results.get("violation_count"),
                            "warning_count": results.get("warning_count"),
                            "information_count": results.get("info_count"),
                            "severity": item.get("severity") or severity,
                            "shape": item.get("shape") or "",
                            "focus_node": item.get("focus") or "",
                            "message": item.get("message") or "",
                            "engine": results.get("engine") or "",
                        }
                    )
        if not any(row["document_id"] == document_id for row in rows):
            rows.append(
                {
                    "document_id": document_id,
                    "conforms": conforms,
                    "violation_count": shacl.get("violation_count"),
                    "warning_count": shacl.get("warning_count"),
                    "information_count": shacl.get("info_count"),
                    "severity": "",
                    "shape": "",
                    "focus_node": "",
                    "message": "",
                    "engine": shacl.get("engine") or "",
                }
            )
    write_csv(
        root / "validation/per_document_shacl.csv",
        rows,
        ["document_id", "conforms", "violation_count", "warning_count", "information_count", "severity", "shape", "focus_node", "message", "engine"],
    )
    ontology = REPO / "research/financial_event_ontology/ontology/feo007a/ontology/fneo-0.1.0-rc2.ttl"
    core_shapes = REPO / "research/financial_event_ontology/ontology/feo007a/validation/fneo-core-shapes.ttl"
    supplemental = REPO / "research/financial_event_ontology/ontology/feo007a/validation/supplemental-shapes.ttl"
    extension_shapes = REPO / "research/financial_event_ontology/ontology/feo007a/validation/fneo-extension-shapes.ttl"
    consolidated = validate_accepted(core_text, ontology, core_shapes, supplemental)
    extension_report = {"conforms": None, "violation_count": 0, "warning_count": 0, "info_count": 0, "engine": consolidated.get("engine"), "note": "No extension triples."}
    if extension_text.strip() and not extension_text.lstrip().startswith("#"):
        module = _shacl()
        data = Graph()
        data.parse(data=extension_text, format="turtle")
        report = module.validate_graphs(data, module.load_graph(extension_shapes), module.load_graph(ontology))
        extension_report = {
            "conforms": report.conforms if report.results or report.conforms else report.conforms,
            "violation_count": sum(1 for item in report.results if item.severity == "Violation"),
            "warning_count": sum(1 for item in report.results if item.severity == "Warning"),
            "info_count": sum(1 for item in report.results if item.severity == "Info"),
            "engine": report.engine,
            "note": "Extension shapes were applied only to the extension-profile graph.",
        }
        if report.engine.startswith("pyshacl"):
            extension_report["conforms"] = report.conforms
            extension_report["note"] += " pySHACL returned a text report; structured focus nodes come from the local checker when it is the active engine."
    if not exceptions:
        exceptions.append(
            {
                "document_id": "ALL",
                "severity": "",
                "shape": "",
                "focus_node": "",
                "message": "",
                "included_in_release_eligible_graph": "yes",
                "reason": "No per-document core violation was recorded.",
            }
        )
    write_csv(
        root / "validation/shacl_exception_register.csv",
        exceptions,
        ["document_id", "severity", "shape", "focus_node", "message", "included_in_release_eligible_graph", "reason"],
    )
    lines = [
        "# Consolidated SHACL report",
        "",
        "The release-eligible accepted graph was validated with the core shapes and the supplemental shapes.",
        "Extension shapes were applied only to the extension-profile graph.",
        "Violations were not converted into warnings.",
        "",
        f"Engine: {consolidated.get('engine')}",
        f"Core conforms: {consolidated.get('conforms')}",
        f"Core violations: {consolidated.get('violation_count')}",
        f"Core warnings: {consolidated.get('warning_count')}",
        f"Core information results: {consolidated.get('info_count')}",
        "",
        f"Extension conforms: {extension_report.get('conforms')}",
        f"Extension violations: {extension_report.get('violation_count')}",
        f"Extension warnings: {extension_report.get('warning_count')}",
        "",
        "pySHACL is not installed in the project environment. Independent SHACL-engine confirmation remains a pre-release condition.",
        "The local checker implements the SHACL subset used by these shape files. Conformance ignores Warning and Info.",
        "",
    ]
    if consolidated.get("violations"):
        lines.append("## Consolidated violations")
        lines.append("")
        for item in consolidated["violations"]:
            lines.append(f"- {item.get('focus')}: {item.get('message')}")
        lines.append("")
    report_path = root / "validation/consolidated_shacl_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")
    (root / "validation/reasoner_report.md").write_text(
        "\n".join(
            [
                "# Reasoner report",
                "",
                "No project-local OWL reasoner is installed. `owlrl` could not be imported, and no HermiT or ROBOT binary was invoked.",
                "The dry population was not blocked for that reason. No package was installed from the network.",
                "",
                "Consistency of the ontology plus the consolidated accepted graph was not checked.",
                "Unsatisfiable named classes were not enumerated.",
                "No inferred triples were counted as extracted facts.",
                "Inverse temporal triples were not materialised.",
                "",
                "This is a recorded limitation, not a claim of consistency.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    write_csv(
        root / "validation/asserted_vs_inferred_summary.csv",
        [
            {
                "graph": "consolidated_accepted_core",
                "asserted_triples": "see dataset manifest",
                "inferred_triples_not_counted_as_extractions": 0,
                "consistent": "",
                "unsatisfiable_classes": "",
                "engine": "unavailable",
                "notes": "No reasoner expansion was run. Asserted triples remain the extracted graph.",
            }
        ],
        ["graph", "asserted_triples", "inferred_triples_not_counted_as_extractions", "consistent", "unsatisfiable_classes", "engine", "notes"],
    )
    return {
        "eligible_documents": eligible,
        "consolidated": consolidated,
        "extension": extension_report,
        "engines": sorted(item for item in engines if item),
        "exception_count": 0 if exceptions and exceptions[0].get("document_id") == "ALL" else len(exceptions),
    }


def _query_text(cq_id: str) -> tuple[str, str]:
    path = SPARQL_DIR / f"{cq_id}.rq"
    if not path.is_file():
        return "", ""
    return str(path.relative_to(REPO)), path.read_text(encoding="utf-8")


def _comment(text: str, prefix: str) -> str:
    for line in text.splitlines():
        if line.startswith(prefix):
            return line.split(":", 1)[-1].strip()
    return ""


def _run_query(graph: Graph, text: str) -> tuple[str, list[dict], int, int, str]:
    try:
        sample = []
        count = 0
        documents = set()
        for result in graph.query(text):
            count += 1
            data = {str(key): str(value) for key, value in result.asdict().items()}
            if count <= 3:
                sample.append({key: excerpt(value, 120) for key, value in data.items()})
            for key in ("sourceDocumentIdentifier", "document"):
                value = data.get(key) or ""
                if value.isdigit():
                    documents.add(value)
                elif "/document/" in value:
                    documents.add(value.rstrip("/").rsplit("/", 1)[-1])
        return "executed", sample, count, len(documents), ""
    except Exception as exc:
        return "execution_error", [], 0, 0, type(exc).__name__ + ": " + str(exc)[:240]


def _documents_in(rows: list[dict]) -> int:
    found = set()
    for row in rows:
        for key in ("sourceDocumentIdentifier", "document"):
            value = str(row.get(key) or "")
            if not value:
                continue
            if value.isdigit():
                found.add(value)
            elif "/document/" in value:
                found.add(value.rstrip("/").rsplit("/", 1)[-1])
    return len(found)


def write_cqs(root: Path, core_text: str, extension_text: str) -> list[dict]:
    core = Graph()
    if core_text.strip() and not core_text.lstrip().startswith("#"):
        core.parse(data=core_text, format="turtle")
    extension = Graph()
    if extension_text.strip() and not extension_text.lstrip().startswith("#"):
        extension.parse(data=extension_text, format="turtle")
    temporal_facts = sum(1 for predicate in ORDER_NAMES if f"fneo:{predicate}" in extension_text)
    rows = []

    def add(cq_id: str, scope: str, graph: Graph | None, note: str, status: str | None = None) -> None:
        relative, text = _query_text(cq_id)
        if not relative:
            rows.append(
                {
                    "cq_id": cq_id,
                    "scope": scope,
                    "query_file": "",
                    "execution_status": "query_file_missing",
                    "answer_row_count": "",
                    "document_coverage": "",
                    "answer_type": "",
                    "sample_answers": "",
                    "schema_supported": "",
                    "population_supported": "false",
                    "manual_correctness_not_yet_evaluated": "true",
                    "known_limitation": "",
                    "notes": note,
                }
            )
            return
        if status == "not_executed_no_accepted_extension_temporal_facts" or graph is None:
            execution, answers, answer_count, document_count, error = status or "not_executed", [], 0, 0, ""
        else:
            execution, answers, answer_count, document_count, error = _run_query(graph, text)
        sample = json.dumps(answers, ensure_ascii=False)
        if len(sample) > 500:
            sample = sample[:500]
        rows.append(
            {
                "cq_id": cq_id,
                "scope": scope,
                "query_file": relative,
                "execution_status": execution,
                "answer_row_count": answer_count if execution == "executed" else "",
                "document_coverage": document_count if execution == "executed" else "",
                "answer_type": _comment(text, "# Expected answer columns:"),
                "sample_answers": sample if execution == "executed" else "",
                "schema_supported": _comment(text, "# Schema-support status:"),
                "population_supported": "true" if execution == "executed" and answer_count else "false",
                "manual_correctness_not_yet_evaluated": "true",
                "known_limitation": _comment(text, "# Limitation:"),
                "notes": " ".join(part for part in (note, error) if part),
            }
        )

    for cq_id in CORE_QUERIES:
        add(cq_id, "accepted_core_preview", core, "Preview only. Correctness is not evaluated.")
    add("FDQ-006", "demonstration", core, "Query demonstration. Not a separate modelling result.")
    add(
        "FDQ-008",
        "co_presence_demonstration",
        core,
        "WARNING: co-presence of an index and a percentage is not a semantic association and is not an event-value link.",
    )
    for cq_id in EXTENSION_ON_CORE:
        add(cq_id, "extension_query_on_accepted_core", core, "Extension-layer query executed on the accepted core graph because it uses core classes.")
    for cq_id in EXTENSION_ON_EXTENSION:
        add(cq_id, "extension_profile_graph", extension, "Executed on the extension-profile graph. A zero row count is not a correctness result.")
    for cq_id in TEMPORAL_EXTENSION:
        if temporal_facts:
            add(cq_id, "accepted_extension_temporal", extension, "Executed only because accepted extension temporal facts were present.")
        else:
            add(
                cq_id,
                "accepted_extension_temporal",
                None,
                "Not executed. No accepted extension temporal ordering facts were materialised.",
                status="not_executed_no_accepted_extension_temporal_facts",
            )
    write_csv(
        root / "competency_questions/results/cq_preview_results.csv",
        rows,
        [
            "cq_id",
            "scope",
            "query_file",
            "execution_status",
            "answer_row_count",
            "document_coverage",
            "answer_type",
            "sample_answers",
            "schema_supported",
            "population_supported",
            "manual_correctness_not_yet_evaluated",
            "known_limitation",
            "notes",
        ],
    )
    notes_path = root / "competency_questions/diagnostics/cq_execution_notes.md"
    notes_path.parent.mkdir(parents=True, exist_ok=True)
    notes_path.write_text(
        "\n".join(
            [
                "# Competency-question preview notes",
                "",
                "These executions are dry-run previews against the consolidated accepted core graph or, where stated, the extension-profile graph.",
                "They are not final competency-question results.",
                "Every row has manual correctness marked as not yet evaluated.",
                "FDQ-008 demonstrates co-presence. It does not assert an event-value relation.",
                "Temporal extension queries run only when accepted extension temporal facts exist.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return rows


def write_review(root: Path, decisions: list[dict], candidates: list[dict]) -> dict:
    by_candidate = {item["candidate_id"]: item for item in candidates}
    by_subject = defaultdict(list)
    for decision in decisions:
        if decision.get("subject_iri"):
            by_subject[decision["subject_iri"]].append(decision)
    primary = []
    for decision in decisions:
        if decision.get("target_local_name") != "MarketChangeEvent":
            continue
        if decision.get("candidate_set") == "primary_strict" or decision.get("rule_id") == "FE-MCE-001":
            primary.append(decision)
    primary.sort(key=lambda item: (int(item.get("document_id") or 0), item.get("candidate_id") or ""))
    review_rows = []
    for index, decision in enumerate(primary, start=1):
        candidate = by_candidate.get(decision.get("candidate_id"), {})
        subject = decision.get("subject_iri") or ""
        related = by_subject.get(subject, [])
        affected = [item for item in related if item.get("target_local_name") == "hasAffectedMarket"]
        directions = [item for item in related if item.get("target_local_name") == "hasMarketDirection"]
        sentence = candidate.get("sentence_id")
        values = [
            item.get("trigger_or_lexical_form") or ""
            for item in candidates
            if item.get("document_id") == decision.get("document_id")
            and item.get("candidate_kind") == "value_candidate"
            and sentence
            and item.get("sentence_id") == sentence
        ]
        anchors = []
        anchor_path = root / "decisions/per_document" / str(decision.get("document_id")) / "time_anchors.json"
        if anchor_path.is_file():
            for anchor in load_json(anchor_path):
                if anchor.get("event_source_id") and anchor.get("event_source_id") in (candidate.get("source_annotation_ids") or []):
                    anchors.append(f"{anchor.get('classification')}:{anchor.get('time_text')}")
        review_rows.append(
            {
                "review_id": f"REV-MCE-{index:04d}",
                "document_id": decision.get("document_id"),
                "event_candidate_id": decision.get("candidate_id"),
                "event_iri": subject,
                "trigger": candidate.get("trigger_or_lexical_form") or "",
                "source_text": excerpt(candidate.get("textual_evidence") or "", 400),
                "event_span": f"{candidate.get('token_start')}:{candidate.get('token_end')}/{candidate.get('character_start')}:{candidate.get('character_end')}",
                "proposed_event_type": "MarketChangeEvent",
                "status": decision.get("status"),
                "rule_id": decision.get("rule_id"),
                "confidence": decision.get("confidence"),
                "affected_market_candidates": "|".join(item.get("candidate_id") or "" for item in affected),
                "accepted_affected_markets": "|".join(item.get("object_iri") or "" for item in affected if item.get("status") == "accepted"),
                "review_affected_markets": "|".join(item.get("object_iri") or "" for item in affected if item.get("status") == "requires_review"),
                "direction": "|".join(local_name(item.get("object_iri") or "") for item in directions),
                "time_candidates": "|".join(anchors),
                "value_context": "|".join(value for value in values if value),
                "evidence_ids": "|".join(decision.get("evidence_references") or candidate.get("source_annotation_ids") or []),
                "review_label": "",
                "reviewer_notes": "",
            }
        )
    write_csv(
        root / "review/primary_events/primary_market_change_review.csv",
        review_rows,
        [
            "review_id",
            "document_id",
            "event_candidate_id",
            "event_iri",
            "trigger",
            "source_text",
            "event_span",
            "proposed_event_type",
            "status",
            "rule_id",
            "confidence",
            "affected_market_candidates",
            "accepted_affected_markets",
            "review_affected_markets",
            "direction",
            "time_candidates",
            "value_context",
            "evidence_ids",
            "review_label",
            "reviewer_notes",
        ],
    )
    flags = {}
    for document_id in document_dirs(root):
        doc_decisions = [item for item in decisions if item.get("document_id") == document_id]
        targets = {item.get("target_local_name") for item in doc_decisions}
        statuses = {item.get("status") for item in doc_decisions}
        found = set()
        if "MarketIndex" in targets:
            found.add("market_index")
        if "EquityMarket" in targets:
            found.add("equity_market")
        if "CentralBank" in targets:
            found.add("central_bank")
        if "CommercialBank" in targets:
            found.add("commercial_bank")
        if "Currency" in targets:
            found.add("currency")
        if "EquityShare" in targets:
            found.add("equity_share")
        if "FinancialSystem" in targets or "FinancialSector" in targets:
            found.add("financial_system_or_sector")
        if "PercentageValue" in targets:
            found.add("percentage")
        anchor_path = root / "decisions/per_document" / document_id / "time_anchors.json"
        if anchor_path.is_file() and load_json(anchor_path):
            found.add("temporal")
        if "accepted" in statuses:
            found.add("accepted_output")
        if "requires_review" in statuses:
            found.add("review_output")
        if statuses.intersection({"rejected", "insufficient_evidence"}):
            found.add("rejected_or_insufficient_output")
        flags[document_id] = found
    selected = []
    covered = set()
    remaining = sorted(flags, key=lambda item: int(item))
    while len(selected) < 8 and remaining:
        best = remaining[0]
        best_gain = -1
        for document_id in remaining:
            gain = len(flags[document_id] - covered)
            if gain > best_gain:
                best = document_id
                best_gain = gain
        selected.append(best)
        remaining.remove(best)
        covered |= flags[best]
    available = sorted({flag for values in flags.values() for flag in values})
    missing_strata = [
        name
        for name in (
            "market_index",
            "equity_market",
            "central_bank",
            "commercial_bank",
            "currency",
            "equity_share",
            "financial_system_or_sector",
            "percentage",
            "temporal",
            "accepted_output",
            "review_output",
            "rejected_or_insufficient_output",
        )
        if name not in available
    ]
    selection_lines = [
        "# Extension-sample selection",
        "",
        "Eight documents were selected after population by a deterministic set cover.",
        "The tie break is the ascending document identifier. Documents were not ranked by how many decisions were accepted.",
        "",
        "Selected documents: " + ", ".join(selected),
        "",
        "Strata present in the population: " + (", ".join(available) if available else "none"),
        "",
        "Strata not populated, and therefore not available for selection: " + (", ".join(missing_strata) if missing_strata else "none"),
        "",
        "Central-bank, commercial-bank, currency, equity-share, and financial-system classes are absent when the corrected adapter does not request the extension profile those rules consume.",
        "That absence is recorded as an adapter gap. It was not repaired by inventing class assignments.",
        "",
    ]
    selection_path = root / "review/extension_sample/selection.md"
    selection_path.parent.mkdir(parents=True, exist_ok=True)
    selection_path.write_text("\n".join(selection_lines), encoding="utf-8")
    extension_rows = []
    counter = 1
    for document_id in selected:
        doc_decisions = [item for item in decisions if str(item.get("document_id")) == document_id]
        interesting = [
            item
            for item in doc_decisions
            if item.get("profile") != "CORE_DETERMINISTIC"
            or item.get("target_local_name") in ENTITY_TARGETS.union({"PercentageValue", "MarketChangeEvent", "hasEventTime", "hasAffectedMarket"})
        ]
        for decision in interesting[:12]:
            candidate = by_candidate.get(decision.get("candidate_id"), {})
            extension_rows.append(
                {
                    "review_id": f"REV-EXT-{counter:04d}",
                    "document_id": document_id,
                    "candidate_id": decision.get("candidate_id"),
                    "target": decision.get("target_local_name"),
                    "profile": decision.get("profile"),
                    "status": decision.get("status"),
                    "rule_id": decision.get("rule_id"),
                    "confidence": decision.get("confidence"),
                    "surface": excerpt(candidate.get("trigger_or_lexical_form") or "", 120),
                    "evidence": excerpt(candidate.get("textual_evidence") or "", 180),
                    "review_label": "",
                    "reviewer_notes": "",
                }
            )
            counter += 1
    write_csv(
        root / "review/extension_sample/extension_review.csv",
        extension_rows,
        ["review_id", "document_id", "candidate_id", "target", "profile", "status", "rule_id", "confidence", "surface", "evidence", "review_label", "reviewer_notes"],
    )
    rejected_rows = _rejected_sample(root, decisions, candidates)
    temporal_rows = _temporal_sample(root)
    definitions = _definitions()
    (root / "review").mkdir(parents=True, exist_ok=True)
    (root / "review/review_forms").mkdir(parents=True, exist_ok=True)
    (root / "review/review_label_definitions.md").write_text(definitions, encoding="utf-8")
    (root / "review/review_forms/review_label_definitions.md").write_text(definitions, encoding="utf-8")
    instructions = _instructions()
    (root / "review/review_instructions.md").write_text(instructions, encoding="utf-8")
    (root / "review/review_forms/review_instructions.md").write_text(instructions, encoding="utf-8")
    return {
        "primary_events": len(review_rows),
        "primary_documents": len({row["document_id"] for row in review_rows}),
        "extension_documents": selected,
        "extension_rows": len(extension_rows),
        "rejected_rows": len(rejected_rows),
        "temporal_rows": len(temporal_rows),
    }


def _rejected_sample(root: Path, decisions: list[dict], candidates: list[dict]) -> list[dict]:
    by_candidate = {item["candidate_id"]: item for item in candidates}
    rows = []

    def add(category: str, document_id: str, identifier: str, text: str, note: str) -> None:
        rows.append(
            {
                "category": category,
                "document_id": document_id,
                "identifier": identifier,
                "text": excerpt(text, 240),
                "note": note,
                "review_label": "",
                "reviewer_notes": "",
            }
        )

    trigger = [
        item
        for item in decisions
        if item.get("rule_id") == "FE-MCE-003" or "negative_trigger_only" in (item.get("negative_conditions_fired") or [])
    ]
    for item in sorted(trigger, key=lambda row: (int(row.get("document_id") or 0), row.get("candidate_id") or ""))[:8]:
        candidate = by_candidate.get(item.get("candidate_id"), {})
        add("trigger_only_market_change", item.get("document_id"), item.get("candidate_id"), candidate.get("textual_evidence") or "", item.get("status") or "")
    ambiguous = [
        item
        for item in decisions
        if item.get("target_local_name") == "MarketChangeEvent" and ("ambiguous" in (item.get("manual_review_reason") or "").lower() or "blocking_ambiguity" in (item.get("negative_conditions_fired") or []))
    ]
    for item in sorted(ambiguous, key=lambda row: (int(row.get("document_id") or 0), row.get("candidate_id") or ""))[:8]:
        candidate = by_candidate.get(item.get("candidate_id"), {})
        add("ambiguous_market_phrase", item.get("document_id"), item.get("candidate_id"), candidate.get("textual_evidence") or "", item.get("manual_review_reason") or "")
    values = [item for item in decisions if item.get("target_local_name") == "hasReportedValue"]
    for item in sorted(values, key=lambda row: (int(row.get("document_id") or 0), row.get("candidate_id") or ""))[:8]:
        add("invalid_or_uncertain_value_attachment", item.get("document_id"), item.get("candidate_id"), item.get("explanation") or "", item.get("status") or "")
    for document_id in document_dirs(root):
        group_path = root / "decisions/per_document" / document_id / "participant_groups.json"
        anchor_path = root / "decisions/per_document" / document_id / "time_anchors.json"
        if not group_path.is_file() or not anchor_path.is_file():
            continue
        groups = load_json(group_path)
        for group in groups:
            if group.get("classification") == "structural_only":
                add("argument_label_only_role", document_id, group.get("path_id"), group.get("text") or "", group.get("source_roles") or "")
            elif group.get("classification") == "unresolved_reference":
                add("unresolved_participant_path", document_id, group.get("path_id"), group.get("text") or "", group.get("notes") or "")
        anchors = load_json(anchor_path)
        for anchor in anchors:
            if anchor.get("classification") in {"unsupported_attachment", "inferred_event_time", "rule_attached_candidate"} and anchor.get("direct_triple_eligible") in {False, "false", ""}:
                add("unsupported_temporal_attachment", document_id, anchor.get("anchor_id"), f"{anchor.get('event_text')} / {anchor.get('time_text')}", anchor.get("classification") or "")
    # Keep the sample deterministic and bounded after the full scan.
    bounded = []
    seen = defaultdict(int)
    for row in rows:
        if seen[row["category"]] >= 8:
            continue
        seen[row["category"]] += 1
        bounded.append(row)
    expected = [
        "trigger_only_market_change",
        "argument_label_only_role",
        "ambiguous_market_phrase",
        "invalid_or_uncertain_value_attachment",
        "unsupported_temporal_attachment",
        "unresolved_participant_path",
    ]
    present = {row["category"] for row in bounded}
    for category in expected:
        if category not in present:
            bounded.append(
                {
                    "category": category,
                    "document_id": "",
                    "identifier": "",
                    "text": "",
                    "note": "No candidate of this category was produced by the unchanged adapter and rules.",
                    "review_label": "",
                    "reviewer_notes": "",
                }
            )
    write_csv(
        root / "review/rejected_sample/rejected_sample.csv",
        bounded,
        ["category", "document_id", "identifier", "text", "note", "review_label", "reviewer_notes"],
    )
    (root / "review/rejected_sample/README.md").write_text(
        "\n".join(
            [
                "# Rejected and insufficient sample",
                "",
                "This sample is a deterministic extract for manual review.",
                "A blank review label means the row has not been judged.",
                "Categories that the population did not produce are recorded with an empty identifier.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return bounded


def _temporal_sample(root: Path) -> list[dict]:
    rows = []
    for document_id in document_dirs(root):
        anchor_path = root / "decisions/per_document" / document_id / "time_anchors.json"
        relation_path = root / "extraction/per_document" / document_id / "temporal_relations.json"
        if not anchor_path.is_file() or not relation_path.is_file():
            continue
        for anchor in load_json(anchor_path):
            classification = anchor.get("classification") or ""
            if classification == "explicit_event_time":
                category = "accepted_explicit_event_time" if str(anchor.get("direct_triple_eligible")).lower() == "true" else "explicit_event_time_candidate"
            elif classification == "rule_attached_candidate":
                category = "rule_attached_anchor"
            elif classification == "inferred_event_time":
                category = "inferred_anchor"
            else:
                category = classification or "other_anchor"
            rows.append(
                {
                    "category": category,
                    "document_id": document_id,
                    "identifier": anchor.get("anchor_id"),
                    "event_text": anchor.get("event_text") or "",
                    "time_text": anchor.get("time_text") or "",
                    "source_relation": anchor.get("source_relation") or "",
                    "status": anchor.get("status") or "",
                    "direct_triple_eligible": anchor.get("direct_triple_eligible") or "",
                    "notes": anchor.get("notes") or "",
                    "review_label": "",
                    "reviewer_notes": "",
                }
            )
        for relation in load_json(relation_path):
            if relation.get("relationship_type") != "TLINK":
                continue
            properties = relation.get("source_properties") or {}
            source_kind = str(properties.get("source_kind") or "")
            if properties.get("suppressed"):
                category = "suppressed_temporal"
            elif source_kind in {"inverse_generated", "closure_derived", "model_inferred", "reasoner_entailed"}:
                category = "experimental_ordering"
            else:
                category = "committed_or_operational_ordering_not_accepted"
            rows.append(
                {
                    "category": category,
                    "document_id": document_id,
                    "identifier": relation.get("source_identifier"),
                    "event_text": properties.get("start_eid") or "",
                    "time_text": properties.get("end_tid") or properties.get("end_eid") or "",
                    "source_relation": properties.get("rel_type") or "TLINK",
                    "status": properties.get("status") or "",
                    "direct_triple_eligible": "false",
                    "notes": "Source ordering inventory. Not an accepted temporal fact.",
                    "review_label": "",
                    "reviewer_notes": "",
                }
            )
    write_csv(
        root / "review/temporal_sample/temporal_sample.csv",
        rows,
        ["category", "document_id", "identifier", "event_text", "time_text", "source_relation", "status", "direct_triple_eligible", "notes", "review_label", "reviewer_notes"],
    )
    (root / "review/temporal_sample/README.md").write_text(
        "\n".join(
            [
                "# Temporal sample",
                "",
                "Each row has a category. The categories are not interchangeable.",
                "",
                "- accepted_explicit_event_time: an anchor the eligibility policy marked direct-triple eligible.",
                "- explicit_event_time_candidate: classified explicit, without a direct triple.",
                "- rule_attached_anchor: an operational rule attachment. Not accepted event time.",
                "- inferred_anchor: an inferred attachment. Not accepted event time.",
                "- committed_or_operational_ordering_not_accepted: a source ordering relation that was not materialised as an accepted fact.",
                "- suppressed_temporal: a suppressed source link.",
                "- experimental_ordering: a source link whose kind is inverse, closure, model, or reasoner output.",
                "",
                "Blank review labels are for the human reviewer.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return rows


def _definitions() -> str:
    return "\n".join(
        [
            "# Review label definitions",
            "",
            "Leave every review label blank until a human reviewer assigns it. Do not copy a rule status into a review label.",
            "",
            "## Entity type",
            "",
            "- correct",
            "- incorrect",
            "- ambiguous",
            "- insufficient evidence",
            "- out of scope",
            "",
            "## Event type",
            "",
            "- correct",
            "- incorrect",
            "- partially correct",
            "- ambiguous",
            "- insufficient evidence",
            "- out of scope",
            "",
            "## Affected-market role",
            "",
            "- correct",
            "- incorrect",
            "- ambiguous",
            "- unresolved attachment",
            "- wrong participant type",
            "- insufficient evidence",
            "",
            "## Temporal anchor",
            "",
            "- explicit and correct",
            "- inferred but plausible",
            "- unsupported",
            "- wrong event",
            "- wrong time",
            "- document time only",
            "- ambiguous",
            "",
            "## Evidence",
            "",
            "- exact support",
            "- partial support",
            "- insufficient support",
            "- wrong evidence",
            "",
        ]
    )


def _instructions() -> str:
    return "\n".join(
        [
            "# Review instructions",
            "",
            "This package prepares manual review. It does not record precision, recall, or a final accuracy figure.",
            "",
            "1. Use the label definitions in `review_label_definitions.md`.",
            "2. Leave `review_label` and `reviewer_notes` blank until a person has read the source text.",
            "3. Judge the proposed type or role against the quoted evidence. A rule status is not a review label.",
            "4. Keep event time separate from document publication time and from event-to-event order.",
            "5. Do not treat co-presence of a value and an event as an event-value link.",
            "6. Do not merge entities across documents while reviewing this package.",
            "7. The elicited set of 25 market-change events across 18 documents is background from an earlier elicitation. It is not a quota for this file.",
            "",
            "Primary market-change rows are in `review/primary_events/`.",
            "The extension sample is in `review/extension_sample/`.",
            "Rejected and insufficient examples are in `review/rejected_sample/`.",
            "Temporal categories are distinguished in `review/temporal_sample/`.",
            "",
        ]
    )
