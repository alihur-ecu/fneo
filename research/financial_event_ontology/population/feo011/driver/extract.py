"""Read-only extraction for the frozen 30-document graph.

Query text, record construction, and the read-only guard come from the
corrected adapter. This module only chooses the canonical document and
writes records under the FEO-011 tree.
"""

from __future__ import annotations

import csv
from pathlib import Path

from driver.common import (
    ADAPTER_ROOT,
    APPROVED_URI,
    CORPUS,
    EXPECTED_DOCUMENTS,
    EXPECTED_NODES,
    EXPECTED_RELATIONSHIPS,
    FROZEN_RUN,
    ONTOLOGY_SHA,
    RECORD_GROUPS,
    REPO,
    ensure_adapter_path,
    scrub,
    sha256_file,
)

ensure_adapter_path()

from adapter.common import dump_json, sanitise, sha256_file as adapter_sha  # noqa: E402
from adapter.extraction.extractor import (  # noqa: E402
    EXPECTED_CONTAINER,
    _inspect_container,
    _run_queries,
    graph_counts,
    load_manifest,
)
from adapter.extraction.records import build_records as build_source_records  # noqa: E402
from adapter.safety.guards import (  # noqa: E402
    assert_approved_endpoint,
    assert_read_only_query,
    load_password,
)

GLOBAL_QUERY_IDS = {
    "Q01_node_count",
    "Q02_relationship_count",
    "Q03_annotated_text_count",
    "Q04_document_ids",
    "Q05_labels",
    "Q06_relationship_types",
}


class SafetyStop(RuntimeError):
    """The frozen graph or the endpoint failed a pre-condition."""


def load_inventory() -> list[dict]:
    path = REPO / "research" / "financial_event_ontology" / "corpus_audit" / "stock_documents.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != EXPECTED_DOCUMENTS or len({row["document_id"] for row in rows}) != EXPECTED_DOCUMENTS:
        raise SafetyStop("The canonical document inventory is not an exact 30-document set.")
    return rows


def _scoped_ids(manifest: dict) -> set[str]:
    found = set()
    for query in manifest["queries"]:
        if query["query_id"] in GLOBAL_QUERY_IDS:
            continue
        found.add(query["query_id"])
    return found


def _activate_guard(manifest: dict) -> None:
    for query in manifest["queries"]:
        assert_read_only_query(query["cypher"], allow_unscoped=bool(query.get("allow_unscoped")))


def _counts_from(results: dict) -> dict:
    counts = graph_counts(results)
    return {
        "node_count": counts.get("node_count"),
        "relationship_count": counts.get("relationship_count"),
        "annotated_text_count": counts.get("annotated_text_count"),
    }


def _check_counts(counts: dict, document_ids: list[str], inventory_ids: list[str]) -> None:
    if counts.get("node_count") != EXPECTED_NODES:
        raise SafetyStop(f"Node count {counts.get('node_count')} is not {EXPECTED_NODES}.")
    if counts.get("relationship_count") != EXPECTED_RELATIONSHIPS:
        raise SafetyStop(f"Relationship count {counts.get('relationship_count')} is not {EXPECTED_RELATIONSHIPS}.")
    if counts.get("annotated_text_count") != EXPECTED_DOCUMENTS:
        raise SafetyStop(f"AnnotatedText count {counts.get('annotated_text_count')} is not {EXPECTED_DOCUMENTS}.")
    if sorted(document_ids) != sorted(inventory_ids) or len(document_ids) != len(set(document_ids)):
        raise SafetyStop("The graph document identifiers are not the canonical 30-document set.")


def open_verified_session(config: dict):
    """Return (driver, session, safety). Caller closes the driver."""
    from neo4j import GraphDatabase

    uri = assert_approved_endpoint(str(config.get("neo4j_uri") or ""))
    if uri != APPROVED_URI:
        raise SafetyStop("Endpoint verification did not return bolt://127.0.0.1:17688.")
    ontology = REPO / str(config["ontology_ttl"])
    checksum = adapter_sha(ontology)
    if checksum != ONTOLOGY_SHA:
        raise SafetyStop("The ontology checksum does not match the release candidate.")
    container = _inspect_container(str(config.get("expected_container_name") or EXPECTED_CONTAINER))
    manifest = load_manifest()
    _activate_guard(manifest)
    password = load_password(str(config.get("neo4j_password_env") or "FEO_NEO4J_PASSWORD"))
    driver = GraphDatabase.driver(uri, auth=(str(config.get("neo4j_username") or "neo4j"), password))
    del password
    try:
        driver.verify_connectivity()
    except Exception as exc:
        driver.close()
        raise SafetyStop("The research graph could not be reached: " + scrub(str(exc))) from exc
    session = driver.session(database=str(config.get("neo4j_database") or "neo4j"))
    safety = {
        "uri": uri,
        "database": str(config.get("neo4j_database") or "neo4j"),
        "container": container,
        "ontology_sha256": checksum,
        "frozen_run_id": FROZEN_RUN,
        "corpus": CORPUS,
        "guard": "adapter.safety.guards.assert_read_only_query",
        "transactions": "execute_read",
    }
    return driver, session, manifest, safety


def measure_graph(session, manifest: dict, inventory_ids: list[str]) -> dict:
    log: list[str] = []
    early = _run_queries(session, manifest, inventory_ids[0], GLOBAL_QUERY_IDS, log)
    found = [str(row.get("document_id")) for row in early.get("Q04_document_ids") or []]
    counts = _counts_from(early)
    _check_counts(counts, found, inventory_ids)
    labels = sorted(str(row.get("label")) for row in early.get("Q05_labels") or [])
    types = sorted(str(row.get("relationship_type") or row.get("relationshipType") or "") for row in early.get("Q06_relationship_types") or [])
    for required in ("AnnotatedText", "EntityMention", "EventMention", "TEvent", "TIMEX", "VALUE"):
        if required not in labels:
            raise SafetyStop(f"Required label {required} is absent.")
    return {
        "counts": counts,
        "document_ids": sorted(found, key=lambda item: int(item)),
        "labels": labels,
        "relationship_types": [item for item in types if item],
        "query_log": log,
    }


def extract_document(session, manifest: dict, document_id: str) -> dict:
    log: list[str] = []
    scoped = _run_queries(session, manifest, document_id, _scoped_ids(manifest), log)
    bundle = build_source_records(scoped, document_id)
    for group in RECORD_GROUPS:
        for record in bundle[group]:
            if record.get("document_identifier") not in {None, document_id}:
                raise SafetyStop(f"A source record for {document_id} cites another document.")
    sanitised = sanitise(bundle)
    sanitised["document_id"] = document_id
    row_counts = {query_id: len(rows) for query_id, rows in scoped.items()}
    return {"bundle": sanitised, "query_log": log, "query_row_counts": row_counts}


def save_bundle(destination: Path, extracted: dict) -> None:
    bundle = extracted["bundle"]
    destination.mkdir(parents=True, exist_ok=True)
    files = {
        "documents.json": bundle["documents"],
        "sentences.json": bundle["sentences"],
        "tokens.json": bundle["tokens"],
        "mentions.json": bundle["mentions"],
        "canonical_entities.json": bundle["canonical_entities"],
        "canonical_events.json": bundle["canonical_events"],
        "participants.json": bundle["participants"],
        "times.json": bundle["times"],
        "temporal_relations.json": bundle["temporal_relations"],
        "values.json": bundle["values"],
        "evidence.json": bundle["evidence"],
        "warnings.json": bundle["warnings"],
        "observed_counts.json": bundle["observed_counts"],
        "indexes.json": bundle["indexes"],
        "query_row_counts.json": extracted["query_row_counts"],
    }
    for name, payload in files.items():
        dump_json(destination / name, payload)
    dump_json(
        destination / "extraction_manifest.json",
        {
            "document_id": bundle["document_id"],
            "source_record_counts": {group: len(bundle[group]) for group in RECORD_GROUPS},
            "query_row_counts": extracted["query_row_counts"],
            "warnings": bundle["warnings"],
            "corpus": CORPUS,
        },
    )


def load_bundle(destination: Path, document_id: str) -> dict:
    from adapter.common import load_json

    def _load(name: str):
        return load_json(destination / name)

    indexes = _load("indexes.json")
    token_sentence = {}
    for key, value in (indexes.get("token_sentence") or {}).items():
        token_sentence[int(key)] = value
    indexes = dict(indexes)
    indexes["token_sentence"] = token_sentence
    bundle = {
        "document_id": document_id,
        "documents": _load("documents.json"),
        "sentences": _load("sentences.json"),
        "tokens": _load("tokens.json"),
        "mentions": _load("mentions.json"),
        "canonical_entities": _load("canonical_entities.json"),
        "canonical_events": _load("canonical_events.json"),
        "participants": _load("participants.json"),
        "times": _load("times.json"),
        "temporal_relations": _load("temporal_relations.json"),
        "values": _load("values.json"),
        "evidence": _load("evidence.json"),
        "warnings": _load("warnings.json"),
        "observed_counts": _load("observed_counts.json"),
        "indexes": indexes,
    }
    return bundle


def source_checksum(relative: str) -> str:
    path = REPO / relative
    if not path.is_file():
        return ""
    return sha256_file(path)


def adapter_query_manifest_sha() -> str:
    path = ADAPTER_ROOT / "adapter" / "extraction" / "query_manifest.yaml"
    return sha256_file(path)
