"""Evaluation tables, review files, SHACL, and competency-question previews."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from rdflib import Graph, URIRef

from driver.common import (
    CORPUS,
    REPO,
    ensure_adapter_path,
    excerpt,
    local_name,
    sha256_file,
    write_csv,
)

ensure_adapter_path()

from adapter.checks import validate_accepted  # noqa: E402
from adapter.common import dump_json  # noqa: E402
from adapter.materialisation.materialise import deterministic_turtle  # noqa: E402
from driver.populate import _repair_turtle_literals  # noqa: E402
from adapter.normalisation.normalise import ensure_engine_path  # noqa: E402

FINANCIAL_CLASSES = (
    "MarketIndex",
    "EquityMarket",
    "CentralBank",
    "CommercialBank",
    "Currency",
    "EquityShare",
    "FinancialSystem",
    "FinancialSector",
)
CORE_QUERIES = [f"FCQ-{index:03d}" for index in range(1, 11)] + [f"FDQ-{index:03d}" for index in range(1, 6)]
DEMONSTRATION_QUERIES = ("FDQ-006", "FDQ-008")
EXTENSION_ON_CORE = ("FDQ-007", "EXT-001")
EXTENSION_ON_EXTENSION = ("FDQ-009", "FDQ-010", "FDQ-011", "FDQ-012", "FDQ-013")
TEMPORAL_EXTENSION = ("EXT-002", "EXT-003", "EXT-004")
ORDER_PREDICATES = {"precedes", "follows", "simultaneousWith", "occursDuring", "includes"}
SPARQL_DIR = REPO / "research/financial_event_ontology/ontology/feo006/competency_questions/sparql"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def document_dirs(root: Path) -> list[str]:
    base = root / "extraction" / "per_document"
    if not base.is_dir():
        return []
    return sorted((path.name for path in base.iterdir() if path.is_dir()), key=lambda item: int(item))


def _union(paths: list[Path]) -> tuple[Graph, str]:
    graph = Graph()
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if text.strip() and not text.lstrip().startswith("#"):
            graph.parse(data=text, format="turtle")
    if len(graph) == 0:
        return graph, "# No triples were emitted for this graph.\n"
    return graph, _repair_turtle_literals(deterministic_turtle(graph))


def write_consolidated_rdf(root: Path, eligible_documents: list[str]) -> dict:
    def paths(folder: str, suffix: str, documents: list[str]) -> list[Path]:
        return [root / folder / f"{document_id}{suffix}" for document_id in documents]

    all_docs = document_dirs(root)
    selected = eligible_documents or all_docs
    outputs = {
        "core": (root / "rdf/accepted/consolidated/fneo-stock-core.ttl", "rdf/accepted/per_document", "-core.ttl", selected),
        "review": (root / "rdf/review-required/consolidated/fneo-stock-review.ttl", "rdf/review-required/per_document", "-review.ttl", all_docs),
        "extension": (root / "rdf/review-required/consolidated/fneo-stock-extension.ttl", "rdf/review-required/per_document", "-extension.ttl", all_docs),
        "candidate_review": (
            root / "rdf/review-required/consolidated/fneo-stock-candidate-review.ttl",
            "rdf/review-required/per_document",
            "-candidate-review.ttl",
            all_docs,
        ),
        "rejected": (root / "rdf/rejected/fneo-stock-rejected.ttl", "rdf/rejected/per_document", "-rejected.ttl", all_docs),
        "experimental": (
            root / "rdf/experimental/fneo-stock-temporal-experimental.ttl",
            "rdf/experimental/per_document",
            "-experimental.ttl",
            all_docs,
        ),
    }
    checksums = {}
    graphs = {}
    for name, (destination, folder, suffix, documents) in outputs.items():
        graph, text = _union(paths(folder, suffix, documents))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8")
        checksums[name] = sha256_file(destination)
        graphs[name] = graph
    return {"checksums": checksums, "triple_counts": {name: len(graph) for name, graph in graphs.items()}, "graphs": graphs}


def _decisions(root: Path) -> list[dict]:
    rows = []
    for document_id in document_dirs(root):
        path = root / "decisions" / "per_document" / document_id / "decisions.json"
        if path.is_file():
            rows.extend(load_json(path))
    return rows


def _candidates(root: Path) -> list[dict]:
    rows = []
    for document_id in document_dirs(root):
        path = root / "candidates" / "per_document" / document_id / "candidates.json"
        if path.is_file():
            rows.extend(load_json(path))
    return rows


def write_candidate_stores(root: Path) -> None:
    kinds = {
        "entity_candidates.json": "entity_candidate",
        "event_candidates.json": "event_candidate",
        "participation_candidates.json": "participation_candidate",
        "temporal_candidates.json": "temporal_candidate",
        "value_candidates.json": "value_candidate",
        "evidence_candidates.json": "evidence_candidate",
    }
    grouped = {name: [] for name in kinds}
    all_rows = []
    for document_id in document_dirs(root):
        path = root / "candidates" / "per_document" / document_id / "candidates.json"
        if not path.is_file():
            continue
        rows = load_json(path)
        all_rows.extend(rows)
        for row in rows:
            for name, kind in kinds.items():
                if row.get("candidate_kind") == kind:
                    grouped[name].append(row)
    destination = root / "candidates" / "consolidated"
    for name, rows in grouped.items():
        dump_json(destination / name, rows)
    dump_json(destination / "candidates.json", all_rows)
    decisions = _decisions(root)
    dump_json(root / "decisions" / "consolidated" / "decisions.json", decisions)
    rejected = [
        row
        for row in decisions
        if row.get("status") in {"rejected", "insufficient_evidence", "out_of_scope", "suppressed"}
    ]
    write_csv(
        root / "rdf/rejected/rejected-candidates.csv",
        [
            {
                "document_id": row.get("document_id"),
                "candidate_id": row.get("candidate_id"),
                "decision_id": row.get("decision_id"),
                "rule_id": row.get("rule_id"),
                "status": row.get("status"),
                "profile": row.get("profile"),
                "target": row.get("target_local_name"),
                "confidence": row.get("confidence"),
                "manual_review_reason": row.get("manual_review_reason") or "",
                "explanation": excerpt(row.get("explanation") or "", 300),
            }
            for row in rejected
        ],
        [
            "document_id",
            "candidate_id",
            "decision_id",
            "rule_id",
            "status",
            "profile",
            "target",
            "confidence",
            "manual_review_reason",
            "explanation",
        ],
    )


def write_inventory(root: Path, inventory: list[dict], summaries: list[dict], graph_ids: set[str]) -> None:
    by_id = {row["document_id"]: row for row in summaries}
    rows = []
    for order, item in enumerate(inventory, start=1):
        document_id = item["document_id"]
        summary = by_id.get(document_id, {})
        from driver.extract import source_checksum

        rows.append(
            {
                "document_id": document_id,
                "document_stem": item.get("document_stem") or "",
                "source_naf": item.get("naf_file") or "",
                "gold_xml": item.get("gold_file") or "",
                "graph_present": "yes" if document_id in graph_ids else "no",
                "selected": "yes",
                "processing_order": order,
                "source_checksum": source_checksum(item.get("naf_file") or ""),
                "status": summary.get("status") or "skipped_due_to_safety",
                "notes": summary.get("notes") or item.get("notes") or "",
            }
        )
    write_csv(
        root / "extraction/manifests/document_inventory.csv",
        rows,
        [
            "document_id",
            "document_stem",
            "source_naf",
            "gold_xml",
            "graph_present",
            "selected",
            "processing_order",
            "source_checksum",
            "status",
            "notes",
        ],
    )


def write_processing_status(root: Path, summaries: list[dict], durations: dict[str, str]) -> None:
    rows = []
    for summary in summaries:
        document_id = summary["document_id"]
        rows.append(
            {
                "document_id": document_id,
                "status": summary.get("status"),
                "source_records": summary.get("source_records", 0),
                "candidates": summary.get("candidates", 0),
                "decisions": summary.get("decisions", 0),
                "accepted": summary.get("accepted", 0),
                "review_required": summary.get("review_required", 0),
                "rejected": summary.get("rejected", 0),
                "out_of_scope": summary.get("out_of_scope", 0),
                "insufficient_evidence": summary.get("insufficient_evidence", 0),
                "suppressed": summary.get("suppressed", 0),
                "warnings": summary.get("warnings", 0),
                "errors": summary.get("errors", 0),
                "duration_seconds": durations.get(document_id, ""),
                "notes": summary.get("notes") or "",
            }
        )
    write_csv(
        root / "extraction/manifests/document_processing_status.csv",
        rows,
        [
            "document_id",
            "status",
            "source_records",
            "candidates",
            "decisions",
            "accepted",
            "review_required",
            "rejected",
            "out_of_scope",
            "insufficient_evidence",
            "suppressed",
            "warnings",
            "errors",
            "duration_seconds",
            "notes",
        ],
    )


def write_mention_and_participants(root: Path, summaries: list[dict]) -> dict:
    iris_by_doc = {}
    for summary in summaries:
        path = root / "decisions/per_document" / summary["document_id"] / "mention_iris.json"
        iris_by_doc[summary["document_id"]] = load_json(path) if path.is_file() else []
    owner = defaultdict(list)
    for document_id, iris in iris_by_doc.items():
        for iri in iris:
            owner[iri].append(document_id)
    collisions = {iri: docs for iri, docs in owner.items() if len(set(docs)) > 1}
    mention_rows = []
    for summary in summaries:
        row = dict(summary.get("mention") or {})
        row["document_id"] = summary["document_id"]
        row["cross_document_collision"] = sum(1 for iri in iris_by_doc.get(summary["document_id"], []) if iri in collisions)
        if row["cross_document_collision"] or int(row.get("collisions") or 0) or int(row.get("duplicate_iris") or 0):
            row["status"] = "blocking"
        mention_rows.append(row)
    write_csv(
        root / "evaluation/mention_identity_summary.csv",
        mention_rows,
        [
            "document_id",
            "source_mention_records",
            "public_mention_iris",
            "coextensive_source_records",
            "candidate_reuse_count",
            "collisions",
            "duplicate_iris",
            "cross_document_collision",
            "status",
            "notes",
        ],
    )
    participant_rows = []
    unresolved = []
    structural_emitted = 0
    for summary in summaries:
        row = dict(summary.get("participant") or {})
        structural_emitted += int(row.pop("structural_emitted", 0) or 0)
        participant_rows.append(row)
        path = root / "decisions/per_document" / summary["document_id"] / "unresolved_participants.json"
        if path.is_file():
            unresolved.extend(load_json(path))
    write_csv(
        root / "evaluation/participant_path_summary.csv",
        participant_rows,
        [
            "document_id",
            "raw_operational_paths",
            "normalised_groups",
            "valid_entity_participants",
            "value_arguments",
            "temporal_arguments",
            "event_arguments",
            "mention_without_entity",
            "frame_argument_without_entity",
            "unresolved_references",
            "duplicate_paths",
            "structural_only",
            "out_of_scope",
            "malformed",
            "unresolved",
            "review_required",
            "notes",
        ],
    )
    if unresolved:
        fields = list(unresolved[0].keys())
        write_csv(root / "evaluation/participant_unresolved_register.csv", unresolved, fields)
    else:
        write_csv(
            root / "evaluation/participant_unresolved_register.csv",
            [],
            ["document_id", "path_id", "classification", "notes"],
        )
    return {
        "cross_document_mention_collisions": len(collisions),
        "structural_emitted": structural_emitted,
        "unresolved_rows": len(unresolved),
    }
