"""Load released operational TextGraphs into an empty Neo4j database.

The target defaults to bolt://127.0.0.1:17689. It refuses the frozen research
endpoint bolt://127.0.0.1:17688 so the export source is not overwritten.
"""

from __future__ import annotations

import json
import os

from neo4j import GraphDatabase

from graphio import (
    EXPECTED_DOCUMENTS,
    EXPECTED_NODES,
    EXPECTED_RELATIONSHIPS,
    GRAPH_DIR,
    SUPPLEMENT_NAME,
    assert_label,
    load_password,
)

FROZEN_URI = "bolt://127.0.0.1:17688"
DEFAULT_URI = "bolt://127.0.0.1:17689"


def load_payloads() -> tuple[list[dict], list[dict]]:
    nodes = []
    rels = []
    seen_nodes = set()
    seen_rels = set()
    files = sorted(GRAPH_DIR.glob("*.json"))
    names = {path.name for path in files}
    if SUPPLEMENT_NAME not in names:
        raise RuntimeError("The store supplement is missing.")
    document_files = [path for path in files if path.name != SUPPLEMENT_NAME]
    if len(document_files) != EXPECTED_DOCUMENTS:
        raise RuntimeError(f"Expected 30 document graphs, found {len(document_files)}.")
    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for node in payload["nodes"]:
            if node["export_id"] in seen_nodes:
                continue
            seen_nodes.add(node["export_id"])
            nodes.append(node)
        for rel in payload["relationships"]:
            if rel["export_id"] in seen_rels:
                continue
            seen_rels.add(rel["export_id"])
            rels.append(rel)
    if len(nodes) != EXPECTED_NODES or len(rels) != EXPECTED_RELATIONSHIPS:
        raise RuntimeError(f"Export coverage is nodes={len(nodes)} rels={len(rels)}.")
    return nodes, rels


def _batches(rows: list, size: int = 500):
    for start in range(0, len(rows), size):
        yield rows[start:start + size]


def import_graphs(uri: str | None = None) -> dict:
    target = uri or os.environ.get("FNEO_REPRO_NEO4J_URI", DEFAULT_URI)
    if target.rstrip("/") == FROZEN_URI:
        raise RuntimeError("Refusing to import into the frozen research endpoint.")
    nodes, rels = load_payloads()
    password = load_password()
    driver = GraphDatabase.driver(target, auth=("neo4j", password))
    del password
    driver.verify_connectivity()
    with driver.session() as session:
        # The reproduction database is disposable. The frozen research endpoint is refused above.
        session.run("MATCH (n) DETACH DELETE n").consume()
        groups: dict[tuple[str, ...], list[dict]] = {}
        for node in nodes:
            labels = tuple(assert_label(label) for label in node["labels"])
            groups.setdefault(labels, []).append(
                {"export_id": node["export_id"], "properties": node["properties"] or {}}
            )
        for labels, rows in groups.items():
            clause = ":".join(labels) if labels else ""
            cypher = (
                f"UNWIND $rows AS row CREATE (n:{clause}) "
                "SET n = row.properties SET n.tgx_export_id = row.export_id"
                if clause
                else "UNWIND $rows AS row CREATE (n) SET n = row.properties SET n.tgx_export_id = row.export_id"
            )
            for batch in _batches(rows):
                session.run(cypher, rows=batch).consume()
        session.run("MATCH (n) SET n:TgxImport").consume()
        session.run(
            "CREATE INDEX tgx_export_id IF NOT EXISTS FOR (n:TgxImport) ON (n.tgx_export_id)"
        ).consume()
        session.run("CALL db.awaitIndexes(300)").consume()
        by_type: dict[str, list[dict]] = {}
        supplement_ids = set()
        supplement_path = GRAPH_DIR / SUPPLEMENT_NAME
        for rel in json.loads(supplement_path.read_text(encoding="utf-8"))["relationships"]:
            supplement_ids.add(rel["export_id"])
        for rel in rels:
            by_type.setdefault(assert_label(rel["type"]), []).append(
                {
                    "start": rel["start"],
                    "end": rel["end"],
                    "properties": rel["properties"] or {},
                    "export_id": rel["export_id"],
                    "cross_document": rel["export_id"] in supplement_ids,
                }
            )
        for rel_type, rows in by_type.items():
            print(f"relationships {rel_type} {len(rows)}", flush=True)
            cypher = (
                "UNWIND $rows AS row "
                "MATCH (a:TgxImport {tgx_export_id: row.start}) "
                "MATCH (b:TgxImport {tgx_export_id: row.end}) "
                f"CREATE (a)-[r:{rel_type}]->(b) SET r = row.properties "
                "SET r.tgx_cross_document = row.cross_document"
            )
            for batch in _batches(rows, 2000):
                session.run(cypher, rows=batch).consume()
        phase_runs = session.run("MATCH (p:PhaseRun) RETURN count(p) AS c").single()["c"]
        cross = session.run(
            "MATCH ()-[r]->() WHERE r.tgx_cross_document = true RETURN count(r) AS c"
        ).single()["c"]
        session.run("MATCH ()-[r]->() REMOVE r.tgx_cross_document").consume()
        session.run("MATCH (n) REMOVE n:TgxImport, n.tgx_export_id").consume()
        session.run("DROP INDEX tgx_export_id IF EXISTS").consume()
        counts = {
            "nodes": session.run("MATCH (n) RETURN count(n) AS c").single()["c"],
            "relationships": session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"],
            "documents": session.run("MATCH (a:AnnotatedText) RETURN count(a) AS c").single()["c"],
            "phase_runs": phase_runs,
            "cross_document_relationships": cross,
        }
    driver.close()
    if (
        counts["nodes"] != EXPECTED_NODES
        or counts["relationships"] != EXPECTED_RELATIONSHIPS
        or counts["documents"] != EXPECTED_DOCUMENTS
        or counts["phase_runs"] != 4
        or counts["cross_document_relationships"] != 432
    ):
        raise RuntimeError(f"Imported graph counts do not match the frozen store: {counts}")
    return counts


if __name__ == "__main__":
    print(import_graphs())
