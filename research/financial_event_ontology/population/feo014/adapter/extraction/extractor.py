"""Execute the reviewed query manifest with read transactions only."""

from __future__ import annotations

import csv
from pathlib import Path

import yaml
from neo4j import GraphDatabase

from adapter.common import as_json, dump_json, load_flat_toml, sanitise, sha256_file
from adapter.extraction.records import build_records
from adapter.safety.guards import (
    APPROVED_URI,
    assert_approved_endpoint,
    assert_read_only_query,
    load_password,
    repo_root,
)

COUNT_QUERIES = (
    "Q01_node_count",
    "Q02_relationship_count",
    "Q03_annotated_text_count",
    "Q08_doc_id_node_count",
    "Q09_doc_id_relationship_count",
    "Q10_containment_counts",
)
EXPECTED_CONTAINER = "financial-event-ontology-neo4j-full"


class ExtractionError(RuntimeError):
    """The extraction cannot continue."""


def feo010_root() -> Path:
    """Return the FEO-010A package root (population/feo010a)."""
    return Path(__file__).resolve().parents[3]


def load_config() -> dict:
    root = Path(__file__).resolve().parents[2]
    local = root / "configuration" / "adapter-config.toml"
    example = root / "configuration" / "adapter-config.example.toml"
    path = local if local.is_file() else example
    config = load_flat_toml(path)
    config["_config_path_name"] = path.name
    return config


def load_manifest() -> dict:
    path = Path(__file__).resolve().parent / "query_manifest.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def expected_document_ids() -> list[str]:
    path = repo_root() / "research" / "financial_event_ontology" / "corpus_audit" / "stock_documents.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        return [row["document_id"] for row in csv.DictReader(handle)]


def selected_document_id() -> str:
    path = feo010_root() / "selection" / "selection_candidates.csv"
    chosen = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("selected") == "yes":
                chosen.append(row["document_id"])
    if chosen != ["61327"]:
        raise ExtractionError("The locked selection is not document 61327.")
    return "61327"


def _inspect_container(name: str) -> str:
    import subprocess

    completed = subprocess.run(
        [
            "docker",
            "inspect",
            name,
            "--format",
            "Name={{.Name}} Image={{.Config.Image}} Status={{.State.Status}} Ports={{json .NetworkSettings.Ports}}",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise ExtractionError("The research container could not be inspected.")
    line = completed.stdout.strip()
    if "17688" not in line or "127.0.0.1" not in line:
        raise ExtractionError("The research container is not published on 127.0.0.1:17688.")
    if "7687" in line and "17688" not in line:
        raise ExtractionError("The container publishes port 7687.")
    if "running" not in line:
        raise ExtractionError("The research container is not running.")
    return line


def _execute(session, cypher: str, params: dict) -> list[dict]:
    def work(tx, statement, parameters):
        return [as_json(record.data()) for record in tx.run(statement, parameters)]

    return session.execute_read(work, cypher, params)


def _run_queries(session, manifest: dict, document_id: str, query_ids: set[str] | None, log: list[str]) -> dict:
    results = {}
    for query in manifest["queries"]:
        if query_ids is not None and query["query_id"] not in query_ids:
            continue
        cypher = query["cypher"]
        assert_read_only_query(cypher, allow_unscoped=bool(query.get("allow_unscoped")))
        params = {"doc_id": document_id} if "$doc_id" in cypher else {}
        rows = _execute(session, cypher, params)
        results[query["query_id"]] = rows
        log.append(
            f"{query['query_id']}\trows={len(rows)}\tsafety={query['read_only_safety_classification']}\tpurpose={query['purpose']}"
        )
    return results


def _scalar(rows: list[dict], key: str):
    if not rows:
        return None
    return rows[0].get(key)


def graph_counts(results: dict) -> dict:
    containment = (results.get("Q10_containment_counts") or [{}])[0]
    return {
        "node_count": _scalar(results.get("Q01_node_count") or [], "node_count"),
        "relationship_count": _scalar(results.get("Q02_relationship_count") or [], "relationship_count"),
        "annotated_text_count": _scalar(results.get("Q03_annotated_text_count") or [], "annotated_text_count"),
        "selected_doc_id_node_count": _scalar(results.get("Q08_doc_id_node_count") or [], "doc_id_node_count"),
        "selected_doc_id_relationship_count": _scalar(
            results.get("Q09_doc_id_relationship_count") or [], "doc_id_relationship_count"
        ),
        "selected_sentence_count": containment.get("sentence_count"),
        "selected_token_count": containment.get("token_count"),
        "selected_sentence_relationship_count": containment.get("sentence_rel_count"),
        "selected_token_relationship_count": containment.get("token_rel_count"),
    }


def _require_same(before: dict, after: dict) -> None:
    if before != after:
        raise ExtractionError("Graph counts changed during the read-only extraction.")


def write_records(bundle: dict, destination: Path) -> None:
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
    }
    for name, payload in files.items():
        dump_json(destination / name, payload)


def extract(config: dict | None = None) -> dict:
    """Read one document and write raw and sanitised source records.

    FEO-010A does not call this function. Saved records are loaded instead.
    """
    config = config or load_config()
    document_id = selected_document_id()
    if str(config.get("document_id")) != document_id:
        raise ExtractionError("The adapter configuration document does not match the locked selection.")
    uri = assert_approved_endpoint(str(config.get("neo4j_uri") or ""))
    if uri != APPROVED_URI:
        raise ExtractionError("Endpoint verification did not return the approved URI.")
    container_line = _inspect_container(str(config.get("expected_container_name") or EXPECTED_CONTAINER))
    ontology = repo_root() / str(config["ontology_ttl"])
    checksum = sha256_file(ontology)
    if checksum != "6e58c94ce6ffcd0f94d7e8257abb5a33f342b567f28438ebca1761fc122b78af":
        raise ExtractionError("The ontology checksum does not match the release candidate.")

    manifest = load_manifest()
    for query in manifest["queries"]:
        assert_read_only_query(query["cypher"], allow_unscoped=bool(query.get("allow_unscoped")))

    password = load_password(str(config.get("neo4j_password_env") or "FEO_NEO4J_PASSWORD"))
    driver = GraphDatabase.driver(uri, auth=(str(config.get("neo4j_username") or "neo4j"), password))
    log: list[str] = []
    try:
        driver.verify_connectivity()
        with driver.session(database=str(config.get("neo4j_database") or "neo4j")) as session:
            early_ids = {"Q01_node_count", "Q02_relationship_count", "Q03_annotated_text_count", "Q04_document_ids", "Q05_labels", "Q06_relationship_types"}
            early = _run_queries(session, manifest, document_id, early_ids, log)
            found = [str(row.get("document_id")) for row in early.get("Q04_document_ids") or []]
            expected = expected_document_ids()
            if sorted(found) != sorted(expected) or len(found) != len(set(found)):
                raise ExtractionError("The AnnotatedText identifiers do not match the 30-document inventory.")
            labels = {row.get("label") for row in early.get("Q05_labels") or []}
            for required in ("AnnotatedText", "EntityMention", "EventMention", "TEvent", "TIMEX", "VALUE"):
                if required not in labels:
                    raise ExtractionError(f"Required label {required} is absent.")
            before_partial = graph_counts(early)
            scoped = _run_queries(
                session,
                manifest,
                document_id,
                None,
                log,
            )
            # The second pass of count queries is the after-measurement.
            after = _run_queries(session, manifest, document_id, set(COUNT_QUERIES), log)
    finally:
        driver.close()
        del password

    before = graph_counts(scoped)
    # Early node and relationship counts must match the counts inside the full pass.
    if before_partial.get("node_count") != before.get("node_count"):
        raise ExtractionError("Node count changed while the document list was being read.")
    if before_partial.get("relationship_count") != before.get("relationship_count"):
        raise ExtractionError("Relationship count changed while the document list was being read.")
    after_counts = graph_counts(after)
    comparable = {
        key: before.get(key)
        for key in (
            "node_count",
            "relationship_count",
            "annotated_text_count",
            "selected_doc_id_node_count",
            "selected_doc_id_relationship_count",
            "selected_sentence_count",
            "selected_token_count",
            "selected_sentence_relationship_count",
            "selected_token_relationship_count",
        )
    }
    _require_same(comparable, after_counts)

    bundle = build_records(scoped, document_id)
    for group in (
        "documents", "sentences", "tokens", "mentions", "canonical_entities", "canonical_events",
        "participants", "times", "temporal_relations", "values", "evidence",
    ):
        for record in bundle[group]:
            if record["document_identifier"] != document_id:
                raise ExtractionError("A source record is outside the selected document.")

    root = feo010_root()
    raw_dir = root / "extracted" / "raw" / document_id
    sanitised_dir = root / "extracted" / "sanitised" / document_id
    write_records(bundle, raw_dir)
    sanitised = sanitise(bundle)
    # Indexes are in-memory join aids. They contain application identifiers, not element identifiers.
    write_records(sanitised, sanitised_dir)
    dump_json(sanitised_dir / "indexes.json", sanitised["indexes"])
    dump_json(raw_dir / "indexes.json", bundle["indexes"])

    query_log = root / "reports" / "queries_executed.txt"
    query_log.parent.mkdir(parents=True, exist_ok=True)
    header = [
        "FEO-010 read-only query log",
        f"document_id={document_id}",
        f"endpoint={uri}",
        "password=excluded",
        "container_identity=recorded in the immutability report",
        "",
    ]
    query_log.write_text("\n".join(header + log) + "\n", encoding="utf-8")
    return {
        "bundle": sanitised,
        "counts_before": before,
        "counts_after": after_counts,
        "container_line": container_line,
        "ontology_checksum": checksum,
        "labels": sorted(labels),
        "document_ids": found,
    }


def load_saved_bundle(document_id: str = "61327") -> dict:
    """Load the frozen FEO-010 sanitised records for one document.

    No graph query is issued and no FEO-010 file is written.
    """
    if document_id != "61327":
        raise ExtractionError("FEO-010A loads document 61327 only.")
    source = (
        repo_root()
        / "research"
        / "financial_event_ontology"
        / "population"
        / "feo010"
        / "extracted"
        / "sanitised"
        / document_id
    )
    if not source.is_dir():
        raise ExtractionError("Saved FEO-010 source records are not available.")

    def _load(name: str):
        from adapter.common import load_json

        return load_json(source / name)

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
    for group in (
        "documents", "sentences", "tokens", "mentions", "canonical_entities", "canonical_events",
        "participants", "times", "temporal_relations", "values", "evidence",
    ):
        for record in bundle[group]:
            if record.get("document_identifier") not in {None, document_id}:
                raise ExtractionError("A saved source record is outside document 61327.")
    return bundle
