"""FEO-014 corrected population, validation, and delta review package.

The frozen FEO-010A adapter and the FEO-011 population are not modified.
Source records are the FEO-011 extraction bundles. The text-extraction
pipeline is not rerun. Graph access is limited to read-only counts.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import traceback
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

FEO014 = Path(__file__).resolve().parent
REPO = FEO014.parents[3]
FEO = REPO / "research" / "financial_event_ontology"
FEO011 = FEO / "population" / "feo011"
FEO010A = FEO / "population" / "feo010a" / "corrected_adapter"
ONTOLOGY = FEO / "ontology/feo007a/ontology/fneo-0.1.0-rc2.ttl"
CORE_SHAPES = FEO / "ontology/feo007a/validation/fneo-core-shapes.ttl"
SUPPLEMENTAL_SHAPES = FEO / "ontology/feo007a/validation/supplemental-shapes.ttl"
EXTENSION_SHAPES = FEO / "ontology/feo007a/validation/fneo-extension-shapes.ttl"
EXPECTED_ONTOLOGY = "6e58c94ce6ffcd0f94d7e8257abb5a33f342b567f28438ebca1761fc122b78af"
EXPECTED_NODES = 27126
EXPECTED_RELATIONSHIPS = 121539
EXPECTED_DOCUMENTS = 30
APPROVED_URI = "bolt://127.0.0.1:17688"
CORPUS = "meantime-en-stock"
TASK_DATE = "2026-10-31"
COLLISION_DOCUMENTS = [
    "61327",
    "82738",
    "112579",
    "113267",
    "113330",
    "114719",
    "114904",
    "115711",
    "121225",
    "122475",
    "131162",
    "180695",
]
FROZEN_CANDIDATE = "cand-publication"
FROZEN_DECISION = "dec-d6042ce35a353291"
SHACL_REVIEW = {
    "62405": "FEO012-SHACL-0001",
    "112579": "FEO012-SHACL-0002",
    "115587": "FEO012-SHACL-0003",
    "116834": "FEO012-SHACL-0004",
    "122475": "FEO012-SHACL-0005",
    "124259": "FEO012-SHACL-0006",
}
FINANCIAL_LOCALS = {
    "MarketIndex",
    "EquityMarket",
    "MarketChangeEvent",
    "NumericalValue",
    "PercentageValue",
    "MonetaryAmount",
    "QuantityValue",
    "hasAffectedMarket",
    "hasEventTime",
    "hasMarketDirection",
    "hasReportedValue",
    "hasParticipant",
    "hasPercentageChange",
    "hasMonetaryAmount",
}


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
        if item.is_file() and "__pycache__" not in item.parts and item.suffix != ".pyc"
    )
    for file in files:
        digest.update(str(file.relative_to(path)).encode())
        digest.update(b"\0")
        digest.update(file.read_bytes())
    return digest.hexdigest()


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: "" if row.get(key) is None else row.get(key) for key in fieldnames})


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def dump_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def local_name(iri: str) -> str:
    if not iri:
        return ""
    return str(iri).rstrip("/").rsplit("/", 1)[-1].rsplit("#", 1)[-1]


def git_info() -> dict:
    def read(args: list[str]) -> str:
        try:
            return subprocess.check_output(args, cwd=REPO, text=True).strip()
        except Exception:
            return ""

    return {"branch": read(["git", "rev-parse", "--abbrev-ref", "HEAD"]), "commit": read(["git", "rev-parse", "HEAD"])}


def document_ids() -> list[str]:
    rows = read_csv(FEO / "corpus_audit/stock_documents.csv")
    identifiers = [row["document_id"] for row in rows]
    if len(identifiers) != EXPECTED_DOCUMENTS or len(set(identifiers)) != EXPECTED_DOCUMENTS:
        raise RuntimeError("The canonical document inventory is not an exact 30-document set.")
    return identifiers


def protected_hashes() -> dict:
    rules = FEO / "enrichment/feo009/rules"
    return {
        "ontology": sha256_file(ONTOLOGY),
        "core_shapes": sha256_file(CORE_SHAPES),
        "supplemental_shapes": sha256_file(SUPPLEMENTAL_SHAPES),
        "extension_shapes": sha256_file(EXTENSION_SHAPES),
        "feo009_rules": tree_hash(rules),
        "feo009": tree_hash(FEO / "enrichment/feo009"),
        "feo008": tree_hash(FEO / "mappings/feo008"),
        "feo010a_adapter": tree_hash(FEO010A),
        "feo011_population": tree_hash(FEO011),
        "feo012b_reference_csv": sha256_file(FEO / "review/feo012b/reference_set/feo012b_reference_set.csv"),
        "feo013_metrics": sha256_file(FEO / "evaluation/feo013/metrics.csv"),
        "document_inventory": sha256_file(FEO / "corpus_audit/stock_documents.csv"),
        "affected_market_rules": sha256_file(rules / "core/affected_market_rules.json"),
        "entity_rules_extension": sha256_file(rules / "extension/entity_rules.json"),
        "market_change_rules": sha256_file(rules / "core/market_change_rules.json"),
        "temporal_rules": sha256_file(rules / "temporal/temporal_rules.json"),
        "value_and_evidence_rules": sha256_file(rules / "core/value_and_evidence_rules.json"),
    }


def expected_recorded_hashes() -> dict:
    return {
        "ontology": EXPECTED_ONTOLOGY,
        "core_shapes": "d6136c024234f71d68e47d49c2b2c2b1903f4abd7f06c599b1fdac927dcb608c",
        "supplemental_shapes": "089c5bd67091782b96929b990253a38e8cafcebfc2dd23311139f559d9bd9c50",
        "extension_shapes": "4c8b51a488a909ea5b6dcf4d0ce2d398cf3c665dc5f7e3f842f970d606e022db",
        "feo009_rules": "c8564a8aa33f79539782483dff6e9683a6fb39e33611f9c3b21b8a0aa966fa25",
        "feo009": "1482eb0f82dfe523cd01164b61b89686a6cee39ec1549ceab644784f8855d95b",
        "feo008": "0beacc6838d055e9d5e32e78cd13f1e136dc8be997ad64c53903720e8097e571",
        "feo010a_adapter": "ca09718d6f8a495f1f354e986805207cc5a5ab04ea03467980e3960650fa8918",
        "document_inventory": "3550680e0f48de4e08b879dd4a2ac1ff08af0d10e8aa5a6c6bbf40101a48f3f1",
        "affected_market_rules": "3e414ba48cc4ec8666371c68c585e526cea5766d933d789e7264926dae680850",
        "entity_rules_extension": "07d0cff5be2a4a7deb7ce02a50592f4b14dd9d137a449d7d312a86833b4f00e7",
        "market_change_rules": "88696ae484a28b2da4c56123addfbdb82859a0ca62ea79b58f4ab34d1d2dd126",
        "temporal_rules": "a3268c97f89efcb92b5f244cbe54d5cd07bc4bafae797dc042d01d6b535458a7",
        "value_and_evidence_rules": "af0a3b4ba2cdb79a681610ff910e685fb5b827ac55f62c5dfeed93a4088e5803",
    }


def write_baseline(hashes: dict) -> list[str]:
    expected = expected_recorded_hashes()
    mismatches = [key for key, value in expected.items() if hashes.get(key) != value]
    payload = {
        "task_id": "FEO-014",
        "task_date": TASK_DATE,
        "recorded_at_local": datetime.now().astimezone().isoformat(timespec="seconds"),
        "ontology_sha256": hashes["ontology"],
        "expected_ontology_sha256": EXPECTED_ONTOLOGY,
        "checksums": hashes,
        "expected_recorded": expected,
        "mismatches": mismatches,
        "baseline_match": not mismatches,
        "notes": [
            "The entity_rules.json checksum recorded by FEO-011 matches extension/entity_rules.json.",
            "FEO-011 RDF, candidate, and decision trees are hashed as feo011_population.",
            "The FEO-012B reference-set CSV and FEO-013 metrics file are included.",
        ],
    }
    dump_json(FEO014 / "reports/baseline_manifest.json", payload)
    lines = [f"{hashes[key]}  {key}" for key in sorted(hashes)]
    (FEO014 / "reports/baseline_checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return mismatches


def load_bundle(destination: Path, document_id: str) -> dict:
    def _load(name: str):
        return json.loads((destination / name).read_text(encoding="utf-8"))

    indexes = _load("indexes.json")
    token_sentence = {int(key): value for key, value in (indexes.get("token_sentence") or {}).items()}
    indexes = dict(indexes)
    indexes["token_sentence"] = token_sentence
    bundle = {"document_id": document_id, "indexes": indexes}
    for name in (
        "documents",
        "sentences",
        "tokens",
        "mentions",
        "canonical_entities",
        "canonical_events",
        "participants",
        "times",
        "temporal_relations",
        "values",
        "evidence",
        "warnings",
        "observed_counts",
    ):
        bundle[name] = _load(name + ".json")
    return bundle


def copy_extraction(destination: Path, identifiers: list[str]) -> str:
    source = FEO011 / "extraction" / "per_document"
    target = destination / "extraction" / "per_document"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for document_id in identifiers:
        shutil.copytree(source / document_id, target / document_id)
    note = destination / "extraction" / "SOURCE_RECORDS.md"
    note.write_text(
        "\n".join(
            [
                "# Source records",
                "",
                "These bundles are byte copies of the FEO-011 read-only extraction.",
                "The text-extraction pipeline was not rerun, and the frozen graph was not rewritten.",
                "The ontology population adapter reads these records and applies the three FEO-014 corrections.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return tree_hash(target)


def measure_graph() -> dict:
    sys.path.insert(0, str(FEO014))
    from adapter.safety.guards import APPROVED_URI as approved
    from adapter.safety.guards import assert_approved_endpoint, assert_read_only_query, load_password

    uri = assert_approved_endpoint(APPROVED_URI)
    if uri != approved:
        raise RuntimeError("Endpoint verification failed.")
    password = load_password()
    from neo4j import GraphDatabase

    queries = {
        "node_count": "MATCH (n) RETURN count(n) AS node_count",
        "relationship_count": "MATCH ()-[r]->() RETURN count(r) AS relationship_count",
        "annotated_text_count": "MATCH (a:AnnotatedText) RETURN count(a) AS annotated_text_count",
        "document_ids": "MATCH (a:AnnotatedText) RETURN toString(a.id) AS document_id ORDER BY document_id",
    }
    driver = GraphDatabase.driver(uri, auth=("neo4j", password))
    try:
        counts = {}
        identifiers = []
        with driver.session() as session:
            for name, cypher in queries.items():
                assert_read_only_query(cypher, allow_unscoped=True)

                def work(tx, statement):
                    return [record.data() for record in tx.run(statement)]

                rows = session.execute_read(work, cypher)
                if name == "document_ids":
                    identifiers = [row["document_id"] for row in rows]
                else:
                    counts[name] = int(rows[0][name])
        return {"counts": counts, "document_ids": identifiers}
    finally:
        driver.close()
        del password


def scrub(text: str) -> str:
    secret = os.environ.get("FEO_NEO4J_PASSWORD", "")
    if secret:
        return text.replace(secret, "[redacted]")
    return text


def install_population():
    """Import the FEO-011 driver against the FEO-014 adapter and rewrite identifiers."""
    if str(FEO014) not in sys.path:
        sys.path.insert(0, str(FEO014))
    if str(FEO011) not in sys.path:
        sys.path.insert(0, str(FEO011))
    import driver.common as common

    common.ADAPTER_ROOT = FEO014
    import adapter.identity as identity
    import adapter.identifiers_v2 as identifiers
    import driver.populate as populate

    if identity.ADAPTER_VERSION != "feo014-adapter-0.1.0":
        raise RuntimeError("The population driver did not load the FEO-014 adapter.")
    if getattr(populate, "_feo014_wrapped", False):
        return populate

    original = populate._run_rules

    def wrapped(bundle, normalised):
        recorded, notes, emit_profile = original(bundle, normalised)
        identifiers.apply_identifier_policy(
            [normalised["candidates"], recorded.get("candidates") or []],
            recorded["decisions"],
            CORPUS,
        )
        return recorded, notes, emit_profile

    populate._run_rules = wrapped
    populate._feo014_wrapped = True
    return populate


def populate_root(root: Path, identifiers: list[str], *, validate_shacl: bool) -> list[dict]:
    populate = install_population()
    summaries = []
    for index, document_id in enumerate(identifiers, start=1):
        print(f"FEO-014 populate {index}/{len(identifiers)} {document_id}", flush=True)
        bundle = load_bundle(root / "extraction" / "per_document" / document_id, document_id)
        summary = populate.process_document(bundle, root, validate_shacl=validate_shacl)
        summaries.append(summary)
    return summaries


def correction_tables(root: Path, identifiers: list[str]) -> dict:
    from adapter.normalisation.normalise import normalise

    mention_rows = []
    time_rows = []
    discrepancies = []
    for document_id in identifiers:
        bundle = load_bundle(root / "extraction" / "per_document" / document_id, document_id)
        result = normalise(bundle, CORPUS)
        mention_rows.extend(result["mention_layer_corrections"])
        time_rows.extend(result["time_mention_corrections"])
        discrepancies.extend(result["time_discrepancies"])
    mention_fields = [
        "correction_id",
        "document_id",
        "source_mention_ids",
        "source_layers",
        "spans",
        "text",
        "endpoint_ids",
        "duplicate_confirmed",
        "retained_source_identity",
        "public_mention_iri",
        "public_referent_iri",
        "provenance_retained",
        "decision_reason",
        "notes",
    ]
    time_fields = [
        "correction_id",
        "document_id",
        "source_time_record_id",
        "old_covering_mention_id",
        "old_span",
        "corrected_mention_id",
        "corrected_span",
        "text",
        "time_entity_id",
        "normalised_value",
        "source_relation",
        "correction_status",
        "evidence",
        "notes",
    ]
    for row in time_rows:
        row["time_entity_id"] = row.get("time_entity_local_key") or ""
    write_csv(FEO014 / "corrections/mention_source_layer_corrections.csv", mention_rows, mention_fields)
    write_csv(FEO014 / "corrections/time_mention_corrections.csv", time_rows, time_fields)
    return {"mentions": mention_rows, "times": time_rows, "discrepancies": discrepancies}


def write_discrepancy(rows: list[dict]) -> None:
    september = next((row for row in rows if row.get("document_id") == "124259" and row.get("text") == "September"), None)
    lines = [
        "# Document 124259 source-normalisation discrepancy",
        "",
        "The population adapter splits the covering temporal expression into the two source temporal records. It does not change the year stored on either record.",
        "",
        "The source temporal record for September stores the normalised value 2008-09. The source text of the covering expression is \"between September and October of 2007\", which contains the wording \"of 2007\". Those two pieces of evidence are both preserved.",
        "",
        "This is a source-normalisation discrepancy. It is not treated as authority to assert 2007 in place of the stored value, and it is not treated as authority to alter the source record.",
        "",
    ]
    if september is None:
        lines.append("The September discrepancy row was not produced by the corrected adapter. The diagnostic is unresolved.")
    else:
        lines.extend(
            [
                f"Correction identifier: {september.get('correction_id')}.",
                f"Source time record: {september.get('source_time_record_id')}.",
                f"Preserved normalised value: {september.get('normalised_value')}.",
                f"Corrected mention span: {september.get('corrected_span')}.",
                f"Covering evidence: {september.get('evidence')}.",
                f"Status: {september.get('correction_status')}.",
                "",
                "The row is included in the delta-review package. A corrected year is not asserted.",
            ]
        )
    lines.append("")
    (FEO014 / "corrections/document_124259_time_discrepancy.md").write_text("\n".join(lines), encoding="utf-8")


def write_identifier_policy() -> None:
    text = """# Identifier policy version 2

Task: FEO-014. Date: 2026-10-31.

This policy replaces candidate and decision identifiers that the FEO-011 population could reuse across documents. It does not change public IRIs. A public IRI remains a function of the resource kind, the corpus, the document, and the stable local key. Corrections to duplicate source layers and to temporal mention spans may change the public IRIs of the affected mentions and of a dropped duplicate entity. They do not rewrite unaffected public IRIs.

## Candidate identifiers

Inputs, in order:

1. corpus identifier (`meantime-en-stock`);
2. document identifier;
3. candidate kind;
4. stable source identity, which is the existing local key;
5. mapping version (`feo009-enrichment-0.1.0`).

The identifier is `cand-` followed by the first 16 hexadecimal characters of the SHA-256 digest of those inputs joined by `|`.

The publication candidate keeps the local key `publication`. The document identifier is a separate input, so two documents no longer share `cand-publication`.

Excluded inputs: confidence, review status, timestamp, and processing order.

## Decision identifiers

Inputs, in order:

1. version-2 candidate identifier;
2. rule identifier;
3. target ontology term (the target IRI when the decision has one, otherwise the target local name);
4. population profile;
5. decision-schema version (`feo009-enrichment-decision-0.1.0`).

The identifier is `dec-` followed by the first 16 hexadecimal characters of the SHA-256 digest.

Excluded inputs: confidence, review status, timestamp, and processing order.

## Engine boundary

The enrichment rules and the enrichment engine are unchanged. Within one document the engine still receives the legacy candidate identifier, so its within-document processing order stays the order used by FEO-011. The population driver replaces candidate and decision identifiers with this policy before materialisation and before the population outputs are written. Decision identifiers are not an input to assertion IRIs.

## Properties

The function is deterministic and idempotent. Identical inputs produce identical identifiers. Identifiers are document-scoped. They do not contain filesystem paths or database identifiers. The same semantic classification is not altered by the identifier replacement itself.

The frozen identifiers `cand-publication` and `dec-d6042ce35a353291` are not emitted.
"""
    (FEO014 / "corrections/identifier_policy_v2.md").write_text(text, encoding="utf-8")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def iter_candidates(root: Path):
    base = root / "candidates" / "per_document"
    for path in sorted(base.glob("*/candidates.json")):
        for row in load_json(path):
            yield row


def iter_decisions(root: Path):
    base = root / "decisions" / "per_document"
    for path in sorted(base.glob("*/decisions.json")):
        for row in load_json(path):
            yield row


def index_candidates(root: Path) -> dict:
    found = {}
    for row in iter_candidates(root):
        features = row.get("features") or {}
        key = (row.get("document_id"), row.get("candidate_kind"), features.get("local_key"))
        found.setdefault(key, []).append(row)
    return found


def build_crosswalk(mention_rows: list[dict]) -> list[dict]:
    old_candidates = index_candidates(FEO011)
    new_candidates = index_candidates(FEO014 / "rerun")
    retained_for_dropped = {}
    for row in mention_rows:
        retained = row["retained_source_identity"]
        for entity_id in row["endpoint_ids"].split("|"):
            if entity_id and entity_id != retained:
                retained_for_dropped[(row["document_id"], entity_id)] = retained
    rows = []
    for key, old_rows in old_candidates.items():
        document_id, kind, local_key = key
        new_rows = list(new_candidates.get(key) or [])
        semantic_changed = False
        notes = ""
        if not new_rows:
            entity_id = ""
            for old in old_rows:
                entity_id = (old.get("features") or {}).get("source_entity_id") or entity_id
            retained = retained_for_dropped.get((document_id, entity_id))
            if retained:
                # The dropped entity's local key is not the retained key. Join via the retained entity.
                retained_key = None
                for candidate_key, candidates in new_candidates.items():
                    if candidate_key[0] != document_id or candidate_key[1] != kind:
                        continue
                    for candidate in candidates:
                        if (candidate.get("features") or {}).get("retained_source_entity_id") == retained or (
                            candidate.get("features") or {}
                        ).get("source_entity_id") == retained:
                            retained_key = candidate_key
                            new_rows = candidates
                            break
                    if retained_key:
                        break
                semantic_changed = True
                notes = "Duplicate source layer removed. The old identifier maps to the retained entity."
            else:
                semantic_changed = True
                notes = "No corrected candidate shares this local key."
        for old in old_rows:
            new = new_rows[0] if len(new_rows) == 1 else None
            if new is None and len(new_rows) > 1:
                new = next((item for item in new_rows if item["candidate_id"] == old["candidate_id"]), new_rows[0])
            new_id = new["candidate_id"] if new else ""
            rows.append(
                {
                    "old_identifier": old["candidate_id"],
                    "new_identifier": new_id,
                    "identifier_kind": "candidate",
                    "document_id": document_id,
                    "candidate_kind": kind,
                    "rule_id": "",
                    "collision_group": "DG12B-REJ-0005" if old["candidate_id"] == FROZEN_CANDIDATE else "",
                    "old_reused_across_documents": "true" if old["candidate_id"] == FROZEN_CANDIDATE else "false",
                    "new_unique": "true" if new_id else "false",
                    "semantic_identity_changed": "true" if semantic_changed else "false",
                    "local_key": local_key or "",
                    "notes": notes or "Identifier policy version 2. The local key is unchanged.",
                }
            )
    old_decisions = {}
    for decision in iter_decisions(FEO011):
        old_decisions.setdefault(decision["candidate_id"], []).append(decision)
    new_by_signature = {}
    candidate_local = {}
    for candidate in iter_candidates(FEO014 / "rerun"):
        candidate_local[(candidate["document_id"], candidate["candidate_id"])] = (candidate.get("features") or {}).get("local_key")
    for decision in iter_decisions(FEO014 / "rerun"):
        local = candidate_local.get((decision.get("document_id"), decision.get("candidate_id")))
        signature = (
            decision.get("document_id"),
            decision.get("candidate_kind"),
            local,
            decision.get("rule_id"),
            decision.get("target_local_name") or "",
            decision.get("profile") or "",
        )
        new_by_signature.setdefault(signature, []).append(decision)
    candidate_new = {(row["document_id"], row["old_identifier"]): row for row in rows if row["identifier_kind"] == "candidate"}
    for old_id, decisions in old_decisions.items():
        for decision in decisions:
            document_id = decision.get("document_id")
            candidate_row = candidate_new.get((document_id, old_id))
            local = (candidate_row or {}).get("local_key")
            signature = (
                document_id,
                decision.get("candidate_kind"),
                local,
                decision.get("rule_id"),
                decision.get("target_local_name") or "",
                decision.get("profile") or "",
            )
            matches = new_by_signature.get(signature) or []
            new = matches[0] if matches else None
            semantic_changed = (candidate_row or {}).get("semantic_identity_changed") == "true"
            if new and (
                new.get("status") != decision.get("status") or (new.get("target_local_name") or "") != (decision.get("target_local_name") or "")
            ):
                semantic_changed = True
            rows.append(
                {
                    "old_identifier": decision.get("decision_id"),
                    "new_identifier": new.get("decision_id") if new else "",
                    "identifier_kind": "decision",
                    "document_id": document_id,
                    "candidate_kind": decision.get("candidate_kind") or "",
                    "rule_id": decision.get("rule_id") or "",
                    "collision_group": "DG12B-REJ-0005" if decision.get("decision_id") == FROZEN_DECISION else "",
                    "old_reused_across_documents": "true" if decision.get("decision_id") == FROZEN_DECISION else "false",
                    "new_unique": "true" if new else "false",
                    "semantic_identity_changed": "true" if semantic_changed else "false",
                    "local_key": local or "",
                    "notes": "Decision identifier follows the version-2 candidate identifier.",
                }
            )
    fields = [
        "old_identifier",
        "new_identifier",
        "identifier_kind",
        "document_id",
        "candidate_kind",
        "rule_id",
        "collision_group",
        "old_reused_across_documents",
        "new_unique",
        "semantic_identity_changed",
        "notes",
    ]
    write_csv(FEO014 / "corrections/identifier_crosswalk.csv", rows, fields)
    write_csv(FEO014 / "delta/identifiers/identifier_delta.csv", rows, fields + ["local_key"])
    return rows


def triples(path: Path) -> set[tuple[str, str, str]]:
    from rdflib import Graph

    graph = Graph()
    if not path.is_file():
        return set()
    text = path.read_text(encoding="utf-8")
    if not text.strip() or text.lstrip().startswith("#"):
        return set()
    graph.parse(data=text, format="turtle")
    return {(str(subject), str(predicate), str(obj)) for subject, predicate, obj in graph}


def classify_triple(document_id: str, triple: tuple[str, str, str], direction: str, affected: set[str]) -> str:
    subject, predicate, obj = triple
    names = {local_name(subject), local_name(predicate), local_name(obj)}
    if "mention-" in subject or "mention-" in obj:
        if document_id in {"112579", "116834", "124259"} and (subject in affected or obj in affected or "TimeMention" in obj or local_name(predicate) in {"denotes", "hasMention", "textualForm", "tokenStart", "tokenEnd", "characterStart", "characterEnd"}):
            if local_name(predicate) == "denotes":
                return "denotation_removed" if direction == "removed" else "denotation_added"
            return "temporal_mention_corrected"
    if document_id in {"62405", "115587", "122475"} and (subject in affected or obj in affected):
        if local_name(predicate) == "denotes":
            return "denotation_removed" if direction == "removed" else "denotation_added"
        return "duplicate_removed" if direction == "removed" else "RDF_assertion_added"
    if local_name(predicate) == "denotes":
        return "denotation_removed" if direction == "removed" else "denotation_added"
    return "RDF_assertion_removed" if direction == "removed" else "RDF_assertion_added"


def build_assertion_delta(mention_rows: list[dict], time_rows: list[dict]) -> list[dict]:
    affected = set()
    for row in mention_rows:
        affected.add(row.get("public_referent_iri") or "")
        affected.add(row.get("public_mention_iri") or "")
    old_root = FEO011 / "rdf/accepted/per_document"
    new_root = FEO014 / "rerun/rdf/accepted/per_document"
    rows = []
    for document_id in document_ids():
        old = triples(old_root / f"{document_id}-core.ttl")
        new = triples(new_root / f"{document_id}-core.ttl")
        for triple in sorted(old - new):
            rows.append(_assertion_row(document_id, triple, "removed", affected, time_rows))
        for triple in sorted(new - old):
            rows.append(_assertion_row(document_id, triple, "added", affected, time_rows))
    fields = [
        "document_id",
        "change_type",
        "direction",
        "subject",
        "predicate",
        "object",
        "old_assertion",
        "new_assertion",
        "source_evidence",
        "reason",
        "human_review_required",
        "financial_assertion",
    ]
    write_csv(FEO014 / "delta/assertions/assertion_delta.csv", rows, fields)
    return rows


def _assertion_row(document_id, triple, direction, affected, time_rows) -> dict:
    subject, predicate, obj = triple
    change = classify_triple(document_id, triple, direction, affected)
    financial = local_name(predicate) in FINANCIAL_LOCALS or local_name(obj) in FINANCIAL_LOCALS
    evidence = ""
    for row in time_rows:
        if row["document_id"] == document_id and row.get("text") and row["text"] in obj:
            evidence = row.get("evidence") or row.get("text")
    review = change in {
        "duplicate_removed",
        "mention_split",
        "temporal_mention_corrected",
        "denotation_removed",
        "denotation_added",
    } or financial
    rendered = f"{subject} {predicate} {obj}"
    return {
        "document_id": document_id,
        "change_type": change,
        "direction": direction,
        "subject": subject,
        "predicate": predicate,
        "object": obj,
        "old_assertion": rendered if direction == "removed" else "",
        "new_assertion": rendered if direction == "added" else "",
        "source_evidence": evidence,
        "reason": change,
        "human_review_required": "true" if review else "false",
        "financial_assertion": "true" if financial else "false",
    }


def build_document_delta(assertion_rows: list[dict], crosswalk: list[dict]) -> list[dict]:
    by_doc = defaultdict(Counter)
    for row in assertion_rows:
        by_doc[row["document_id"]][row["change_type"]] += 1
        by_doc[row["document_id"]]["triples"] += 1
    id_only = Counter()
    for row in crosswalk:
        if row["semantic_identity_changed"] != "true":
            id_only[row["document_id"]] += 1
    rows = []
    for document_id in document_ids():
        counts = by_doc.get(document_id) or Counter()
        if counts["triples"]:
            label = "semantic_change"
        elif id_only[document_id]:
            label = "identifier_only"
        else:
            label = "unchanged"
        rows.append(
            {
                "document_id": document_id,
                "change_class": label,
                "changed_triples": counts["triples"],
                "identifier_only_rows": id_only[document_id],
                "duplicate_removed": counts["duplicate_removed"],
                "temporal_mention_corrected": counts["temporal_mention_corrected"],
                "denotation_removed": counts["denotation_removed"],
                "denotation_added": counts["denotation_added"],
                "rdf_added_or_removed": counts["RDF_assertion_added"] + counts["RDF_assertion_removed"],
            }
        )
    write_csv(
        FEO014 / "delta/documents/document_delta.csv",
        rows,
        [
            "document_id",
            "change_class",
            "changed_triples",
            "identifier_only_rows",
            "duplicate_removed",
            "temporal_mention_corrected",
            "denotation_removed",
            "denotation_added",
            "rdf_added_or_removed",
        ],
    )
    return rows


def build_reference_crosswalk(crosswalk: list[dict]) -> tuple[list[dict], list[dict]]:
    by_old = {(row["document_id"], row["old_identifier"], row["identifier_kind"]): row for row in crosswalk}
    reference = read_csv(FEO / "review/feo012b/reference_set/feo012b_reference_set.csv")
    rows = []
    review_rows = []
    for item in reference:
        candidate = by_old.get((item["document_id"], item.get("candidate_id") or "", "candidate"))
        decision = by_old.get((item["document_id"], item.get("decision_id") or "", "decision"))
        semantic = False
        if candidate and candidate["semantic_identity_changed"] == "true":
            semantic = True
        if decision and decision["semantic_identity_changed"] == "true":
            semantic = True
        label = item.get("adjudicated_label") or item.get("original_researcher_label") or ""
        rows.append(
            {
                "review_id": item.get("review_id") or "",
                "reference_id": item.get("reference_id") or "",
                "document_id": item.get("document_id") or "",
                "old_candidate_id": item.get("candidate_id") or "",
                "corrected_candidate_id": (candidate or {}).get("new_identifier") or "",
                "old_decision_id": item.get("decision_id") or "",
                "corrected_decision_id": (decision or {}).get("new_identifier") or "",
                "old_assertion_id": item.get("assertion_id") or "",
                "corrected_assertion_id": item.get("assertion_id") or "",
                "final_researcher_label": label,
                "semantic_identity_changed": "true" if semantic else "false",
                "human_review_required": "true" if semantic else "false",
                "proposed_label_carry_forward": "" if semantic else label,
                "notes": "Identifier-only change. The existing researcher label is carried forward."
                if not semantic
                else "Semantic identity changed. The existing label is not carried forward automatically.",
            }
        )
    write_csv(
        FEO014 / "delta/review/reference_set_crosswalk.csv",
        rows,
        [
            "review_id",
            "reference_id",
            "document_id",
            "old_candidate_id",
            "corrected_candidate_id",
            "old_decision_id",
            "corrected_decision_id",
            "old_assertion_id",
            "corrected_assertion_id",
            "final_researcher_label",
            "semantic_identity_changed",
            "human_review_required",
            "proposed_label_carry_forward",
            "notes",
        ],
    )
    return rows, review_rows


def build_review_package(mention_rows, time_rows, assertion_rows, reference_rows) -> list[dict]:
    """One review row per semantic correction, plus unexpected financial triple changes."""
    labels = {row["review_id"]: row for row in reference_rows}
    review = []
    for row in mention_rows:
        review_id = SHACL_REVIEW.get(row["document_id"], "")
        previous = labels.get(review_id, {})
        review.append(
            {
                "delta_review_id": "",
                "document_id": row["document_id"],
                "old_review_id": review_id,
                "old_candidate_id": "",
                "new_candidate_id": "",
                "old_assertion": "One textual mention denotes two entity resources.",
                "new_assertion": "One textual mention denotes one retained entity. Both source layers remain provenance.",
                "change_type": "duplicate_removed",
                "source_text": row.get("text") or "",
                "old_evidence": row.get("spans") or "",
                "new_evidence": row.get("public_mention_iri") or "",
                "old_researcher_label": previous.get("final_researcher_label") or "",
                "proposed_label_carry_forward": "",
                "human_review_required": "true",
                "researcher_final_label": "",
                "researcher_notes": "",
            }
        )
    for row in time_rows:
        review_id = SHACL_REVIEW.get(row["document_id"], "")
        previous = labels.get(review_id, {})
        discrepancy = row.get("correction_status") == "span_corrected_source_normalisation_discrepancy"
        review.append(
            {
                "delta_review_id": "",
                "document_id": row["document_id"],
                "old_review_id": review_id,
                "old_candidate_id": "",
                "new_candidate_id": "",
                "old_assertion": f"Covering mention {row.get('old_covering_mention_id')} span {row.get('old_span')}",
                "new_assertion": (
                    f"Time mention {row.get('corrected_mention_id')} span {row.get('corrected_span')} "
                    f"value {row.get('normalised_value')}"
                    + ("; source year discrepancy preserved" if discrepancy else "")
                ),
                "change_type": "temporal_mention_corrected",
                "source_text": row.get("text") or "",
                "old_evidence": row.get("evidence") or "",
                "new_evidence": row.get("corrected_span") or "",
                "old_researcher_label": previous.get("final_researcher_label") or "",
                "proposed_label_carry_forward": "",
                "human_review_required": "true",
                "researcher_final_label": "",
                "researcher_notes": "",
            }
        )
    unexpected = [row for row in assertion_rows if row["financial_assertion"] == "true"]
    for row in unexpected:
        review.append(
            {
                "delta_review_id": "",
                "document_id": row["document_id"],
                "old_review_id": "",
                "old_candidate_id": "",
                "new_candidate_id": "",
                "old_assertion": row.get("old_assertion") or "",
                "new_assertion": row.get("new_assertion") or "",
                "change_type": row["change_type"],
                "source_text": "",
                "old_evidence": "",
                "new_evidence": "",
                "old_researcher_label": "",
                "proposed_label_carry_forward": "",
                "human_review_required": "true",
                "researcher_final_label": "",
                "researcher_notes": "",
            }
        )
    for index, row in enumerate(review, start=1):
        row["delta_review_id"] = f"FEO014-DELTA-{index:04d}"
    write_csv(
        FEO014 / "delta/review/changed_assertions_review.csv",
        review,
        [
            "delta_review_id",
            "document_id",
            "old_review_id",
            "old_candidate_id",
            "new_candidate_id",
            "old_assertion",
            "new_assertion",
            "change_type",
            "source_text",
            "old_evidence",
            "new_evidence",
            "old_researcher_label",
            "proposed_label_carry_forward",
            "human_review_required",
            "researcher_final_label",
            "researcher_notes",
        ],
    )
    return review


def _count_population(root: Path, *, documents: int, shacl_conforming: int | None) -> dict:
    decisions = list(iter_decisions(root))
    candidates = list(iter_candidates(root))

    def tally(target, status=None):
        rows = [item for item in decisions if item.get("target_local_name") == target]
        if status:
            rows = [item for item in rows if item.get("status") == status]
        return len(rows)

    time_mentions = sum(
        1
        for item in candidates
        if item.get("candidate_kind") == "temporal_candidate"
        and (item.get("features") or {}).get("time_mention")
        and not (item.get("features") or {}).get("event_time")
    )
    conforming = "" if shacl_conforming is None else shacl_conforming
    return {
        "documents": documents,
        "candidates": len(candidates),
        "decisions": len(decisions),
        "accepted": sum(1 for item in decisions if item.get("status") == "accepted"),
        "review_required": sum(1 for item in decisions if item.get("status") == "requires_review"),
        "rejected": sum(1 for item in decisions if item.get("status") == "rejected"),
        "insufficient_evidence": sum(1 for item in decisions if item.get("status") == "insufficient_evidence"),
        "MarketIndex_accepted": tally("MarketIndex", "accepted"),
        "EquityMarket_accepted": tally("EquityMarket", "accepted"),
        "MarketChangeEvent_accepted": tally("MarketChangeEvent", "accepted"),
        "hasAffectedMarket_accepted": tally("hasAffectedMarket", "accepted"),
        "values_accepted": tally("NumericalValue", "accepted") + tally("PercentageValue", "accepted"),
        "time_mentions": time_mentions,
        "time_entities_accepted": tally("TimeEntity", "accepted"),
        "accepted_event_time": tally("hasEventTime", "accepted"),
        "review_event_time": tally("hasEventTime", "requires_review"),
        "shacl_conforming_documents": conforming,
        "release_eligible_documents": conforming,
    }


def population_counts(summaries: list[dict], eligible: list[str]) -> list[dict]:
    counts = _count_population(FEO014 / "rerun", documents=len(summaries), shacl_conforming=len(eligible))
    baseline = _count_population(FEO011, documents=30, shacl_conforming=24)
    rows = []
    for key, value in counts.items():
        old = baseline.get(key, "")
        delta = "" if old == "" or value == "" else int(value) - int(old)
        rows.append({"metric": key, "feo011_count": old, "feo014_count": value, "delta": delta})
    write_csv(
        FEO014 / "evaluation/corrected_population_counts.csv",
        rows,
        ["metric", "feo011_count", "feo014_count", "delta"],
    )
    return rows


def shacl_package(summaries: list[dict]) -> dict:
    rows = []
    exceptions = []
    eligible = []
    for summary in summaries:
        document_id = summary["document_id"]
        path = FEO014 / "rerun/validation/per_document" / f"{document_id}.json"
        report = load_json(path) if path.is_file() else {}
        conforms = report.get("conforms")
        if conforms is True:
            eligible.append(document_id)
        emitted = False
        for bucket in ("violations", "warnings", "infos"):
            for item in report.get(bucket) or []:
                emitted = True
                row = {
                    "document_id": document_id,
                    "conforms": conforms,
                    "violation_count": report.get("violation_count"),
                    "warning_count": report.get("warning_count"),
                    "information_count": report.get("info_count"),
                    "severity": item.get("severity") or "",
                    "shape": item.get("shape") or "",
                    "focus_node": item.get("focus") or "",
                    "message": item.get("message") or "",
                    "engine": report.get("engine") or "",
                }
                rows.append(row)
                if item.get("severity") == "Violation":
                    exceptions.append(
                        {
                            "document_id": document_id,
                            "severity": "Violation",
                            "shape": item.get("shape") or "",
                            "focus_node": item.get("focus") or "",
                            "message": item.get("message") or "",
                            "included_in_release_eligible_graph": "no",
                            "reason": "A core violation excludes this document from the release-eligible consolidated graph. The shape was not weakened.",
                        }
                    )
        if not emitted:
            rows.append(
                {
                    "document_id": document_id,
                    "conforms": conforms,
                    "violation_count": report.get("violation_count"),
                    "warning_count": report.get("warning_count"),
                    "information_count": report.get("info_count"),
                    "severity": "",
                    "shape": "",
                    "focus_node": "",
                    "message": "",
                    "engine": report.get("engine") or "",
                }
            )
    write_csv(
        FEO014 / "validation/per_document_shacl.csv",
        rows,
        ["document_id", "conforms", "violation_count", "warning_count", "information_count", "severity", "shape", "focus_node", "message", "engine"],
    )
    write_csv(
        FEO014 / "validation/shacl_exception_register.csv",
        exceptions,
        ["document_id", "severity", "shape", "focus_node", "message", "included_in_release_eligible_graph", "reason"],
    )
    sys.path.insert(0, str(FEO014))
    from adapter.checks import validate_accepted
    from rdflib import Graph

    def union(paths: list[Path]) -> str:
        graph = Graph()
        for path in paths:
            text = path.read_text(encoding="utf-8") if path.is_file() else ""
            if text.strip() and not text.lstrip().startswith("#"):
                graph.parse(data=text, format="turtle")
        from adapter.materialisation.materialise import deterministic_turtle

        if len(graph) == 0:
            return "# No triples.\n"
        sys.path.insert(0, str(FEO011))
        from driver.populate import _repair_turtle_literals

        return _repair_turtle_literals(deterministic_turtle(graph))

    core_text = union([FEO014 / "rerun/rdf/accepted/per_document" / f"{document_id}-core.ttl" for document_id in eligible])
    (FEO014 / "rerun/rdf/accepted/consolidated").mkdir(parents=True, exist_ok=True)
    (FEO014 / "rerun/rdf/accepted/consolidated/fneo-stock-core.ttl").write_text(core_text, encoding="utf-8")
    consolidated = validate_accepted(core_text, ONTOLOGY, CORE_SHAPES, SUPPLEMENTAL_SHAPES)
    extension_paths = [FEO014 / "rerun/rdf/review-required/per_document" / f"{document_id}-extension.ttl" for document_id in document_ids()]
    extension_text = union(extension_paths)
    (FEO014 / "rerun/rdf/review-required/consolidated").mkdir(parents=True, exist_ok=True)
    (FEO014 / "rerun/rdf/review-required/consolidated/fneo-stock-extension.ttl").write_text(extension_text, encoding="utf-8")
    extension_note = "Extension output was concatenated. A separate extension-shape validation is recorded only when the project engine accepts the extension graph."
    lines = [
        "# Consolidated SHACL report",
        "",
        f"Engine: {consolidated.get('engine') or 'unspecified'}.",
        "Independent confirmation with a second SHACL engine was not run. It remains a pre-release condition.",
        "",
        f"Release-eligible documents: {len(eligible)}.",
        f"Consolidated accepted core conforms: {consolidated.get('conforms')}.",
        f"Consolidated violations: {consolidated.get('violation_count')}.",
        f"Consolidated warnings: {consolidated.get('warning_count')}.",
        f"Documents with core violations: {len({row['document_id'] for row in exceptions})}.",
        "",
        extension_note,
        "",
        "The six documents previously excluded for the duplicate-mention and shared-time-mention defects are revalidated in this run. Shapes were not edited.",
        "",
    ]
    if exceptions:
        lines.append("Remaining violation focus nodes:")
        lines.append("")
        for row in exceptions:
            lines.append(f"- {row['document_id']} {row['shape']} {row['focus_node']}: {row['message']}")
        lines.append("")
    (FEO014 / "validation/consolidated_shacl_report.md").write_text("\n".join(lines), encoding="utf-8")
    return {"eligible": eligible, "consolidated": consolidated, "exceptions": exceptions, "engine": consolidated.get("engine")}


def hash_tree_files(root: Path, patterns: tuple[str, ...]) -> dict[str, str]:
    found = {}
    for pattern in patterns:
        for path in root.glob(pattern):
            if path.is_file():
                found[str(path.relative_to(root))] = sha256_file(path)
    return found


SEMANTIC_GLOBS = (
    "extraction/per_document/*/documents.json",
    "extraction/per_document/*/mentions.json",
    "extraction/per_document/*/times.json",
    "candidates/per_document/*/candidates.json",
    "decisions/per_document/*/decisions.json",
    "rdf/accepted/per_document/*.ttl",
    "rdf/review-required/per_document/*.ttl",
    "rdf/rejected/per_document/*.ttl",
    "rdf/experimental/per_document/*.ttl",
)


def write_determinism(result: dict) -> None:
    lines = [
        "# Determinism report",
        "",
        "The corrected population was executed twice from the same copied source records. The second run is in `validation/determinism_run2/` and does not replace `rerun/`.",
        "The comparison covers source-record files, candidates, decisions, and per-document RDF. SHACL reports and manifest timestamps are outside the comparison.",
        "",
        f"Result: {'pass' if result.get('pass') else 'fail'}.",
        f"Files compared: {result.get('compared_files')}.",
        f"Missing in the second run: {result.get('missing_count')}.",
        f"Extra in the second run: {result.get('extra_count')}.",
        f"Different checksums: {result.get('different_count')}.",
        "",
    ]
    if result.get("different"):
        lines.append("Differing paths:")
        lines.append("")
        for path in result["different"]:
            lines.append(f"- {path}")
        lines.append("")
    (FEO014 / "validation/determinism_report.md").write_text("\n".join(lines), encoding="utf-8")
    dump_json(FEO014 / "validation/determinism.json", result)


def write_integrity(before: dict, after: dict, graph_before: dict, graph_after: dict, graph_ok: bool) -> None:
    mismatches = [key for key in before if before.get(key) != after.get(key)]
    lines = [
        "# Integrity report",
        "",
        "Checksums were compared with the baseline recorded before the corrected population.",
        "",
        f"Protected checksums unchanged: {not mismatches}.",
        f"Graph counts unchanged: {graph_ok}.",
        f"Nodes before: {graph_before.get('node_count')}. Nodes after: {graph_after.get('node_count')}.",
        f"Relationships before: {graph_before.get('relationship_count')}. Relationships after: {graph_after.get('relationship_count')}.",
        f"AnnotatedText before: {graph_before.get('annotated_text_count')}. AnnotatedText after: {graph_after.get('annotated_text_count')}.",
        "",
        "The ontology, SHACL shapes, FEO-009 rules, FEO-008 mappings, corpus inventory, frozen FEO-010A adapter, FEO-011 population, FEO-012B reference set, and FEO-013 metrics file were compared.",
        "",
    ]
    if mismatches:
        lines.append("Changed checksums:")
        lines.append("")
        for key in mismatches:
            lines.append(f"- {key}")
        lines.append("")
    (FEO014 / "validation/integrity_report.md").write_text("\n".join(lines), encoding="utf-8")
    return mismatches


def collision_counts(root: Path) -> dict:
    candidates = Counter()
    decisions = Counter()
    for row in iter_candidates(root):
        candidates[row["candidate_id"]] += 1
    for row in iter_decisions(root):
        decisions[row["decision_id"]] += 1
    return {
        "candidate_ids_reused": sum(1 for value in candidates.values() if value > 1),
        "decision_ids_reused": sum(1 for value in decisions.values() if value > 1),
        "frozen_candidate_present": candidates[FROZEN_CANDIDATE] > 0,
        "frozen_decision_present": decisions[FROZEN_DECISION] > 0,
    }


def write_review_markdown(stats: dict) -> None:
    lines = [
        "# FEO-014 adapter correction review",
        "",
        "## 1. Task identity",
        "",
        "Task FEO-014 corrects three verified defects in the ontology population adapter, reruns the population on the same 30 documents, and prepares a delta-only human review package.",
        f"Date: {TASK_DATE}. Local completion time: {stats.get('generated_at')}.",
        f"Branch: {stats.get('branch')}. Commit: {stats.get('commit')}.",
        "",
        "## 2. Baseline",
        "",
        f"Ontology checksum matches the release candidate: {stats.get('ontology_match')}.",
        "SHACL shapes, FEO-009 rules, the FEO-010A adapter, the FEO-011 population, the FEO-012B reference set, and the FEO-013 metrics file were checksummed before the run. The comparison is in `reports/baseline_manifest.json`.",
        "",
        "## 3. Three corrections",
        "",
        "Correction A consolidates duplicate source layers of one textual mention so that one public mention denotes one entity, while both source paths remain provenance.",
        "Correction B gives each temporal record with a distinct span its own TimeMention. A covering expression remains evidence and does not denote two time entities.",
        "Correction C assigns document-scoped candidate and decision identifiers. It does not rewrite unaffected public IRIs.",
        "",
        "## 4. Affected documents",
        "",
        "Duplicate source layers: 62405, 115587, 122475.",
        "Temporal mention spans: 112579, 116834, 124259.",
        "Identifier collisions in the FEO-012 rejected sample: 61327, 82738, 112579, 113267, 113330, 114719, 114904, 115711, 121225, 122475, 131162, 180695. The underlying defect was present for every document that used the shared publication identifier.",
        "",
        "## 5. Identifier crosswalk",
        "",
        f"Candidate identifiers reused across documents before correction: {stats.get('candidate_collisions_before')}. After correction: {stats.get('candidate_collisions_after')}.",
        f"Decision identifiers reused across documents before correction: {stats.get('decision_collisions_before')}. After correction: {stats.get('decision_collisions_after')}.",
        "The crosswalk is `corrections/identifier_crosswalk.csv`. Identifier-only rows are not treated as semantic changes.",
        "",
        "## 6. Temporal discrepancy",
        "",
        "Document 124259 preserves the source value 2008-09 on the September record and preserves the covering text \"of 2007\". The discrepancy is described in `corrections/document_124259_time_discrepancy.md`. No corrected year is asserted.",
        "",
        "## 7. Rerun summary",
        "",
        f"Documents populated: {stats.get('documents')}.",
        f"Candidates: {stats.get('candidates')}. Decisions: {stats.get('decisions')}.",
        "The FEO-011 population remains the baseline. Outputs of this run are under `population/feo014/rerun/`.",
        "",
        "## 8. SHACL results",
        "",
        f"Project engine: {stats.get('shacl_engine')}.",
        f"Release-eligible documents: {stats.get('release_eligible')}.",
        f"Consolidated core conforms: {stats.get('shacl_conforms')}.",
        f"Documents with core violations: {stats.get('shacl_exception_documents')}.",
        "The project engine reports a local SHACL subset when pySHACL is not installed. An independent second engine was not run. That confirmation remains a pre-release condition.",
        "",
        "## 9. Semantic delta",
        "",
        f"Changed RDF triples: {stats.get('semantic_triples')}.",
        f"Identifier-only crosswalk rows: {stats.get('identifier_only_rows')}.",
        "Identifier replacement is separated from duplicate removal, temporal mention correction, and denotation changes.",
        "",
        "## 10. Reference-set crosswalk",
        "",
        "Existing researcher labels are carried forward where the local key, rule, target, and decision status are unchanged. The FEO-012B reference set was not rewritten.",
        "",
        "## 11. Delta-review workload",
        "",
        f"Rows requiring human delta review: {stats.get('review_rows')}.",
        "The review file is `delta/review/changed_assertions_review.csv`. New human fields are blank.",
        "",
        "## 12. Corrected population counts",
        "",
        "Counts are in `evaluation/corrected_population_counts.csv`. Correctness metrics were not calculated.",
        "",
        "## 13. Determinism",
        "",
        f"Second-run comparison: {stats.get('determinism')}.",
        "",
        "## 14. Graph integrity",
        "",
        f"Nodes before and after: {stats.get('nodes_before')} and {stats.get('nodes_after')}.",
        f"Relationships before and after: {stats.get('relationships_before')} and {stats.get('relationships_after')}.",
        f"AnnotatedText documents before and after: {stats.get('documents_before')} and {stats.get('documents_after')}.",
        "",
        "## 15. Remaining issues",
        "",
    ]
    for item in stats.get("remaining") or ["None recorded."]:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## 16. Readiness for delta review",
            "",
            stats.get("readiness") or "",
            "",
            "## 17. Files created",
            "",
            "The task outputs are under `research/financial_event_ontology/population/feo014/`. Upstream task directories were not modified.",
            "",
            "## 18. Recommended next action",
            "",
            "Complete the human delta review in `delta/review/changed_assertions_review.csv` before any correctness metric or article result is calculated.",
            "",
        ]
    )
    (FEO014 / "FEO014_ADAPTER_CORRECTION_REVIEW.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    if "--resume" in sys.argv:
        return resume()
    for relative in (
        "reports",
        "corrections",
        "validation",
        "evaluation",
        "delta/identifiers",
        "delta/assertions",
        "delta/documents",
        "delta/review",
        "tests",
    ):
        (FEO014 / relative).mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    info = git_info()
    hashes_before = protected_hashes()
    mismatches = write_baseline(hashes_before)
    if mismatches:
        dump_json(
            FEO014 / "FEO014_TASK_MANIFEST.json",
            {
                "task_id": "FEO-014",
                "date": TASK_DATE,
                "completion_status": "blocked",
                "mismatches": mismatches,
                "reason": "Authoritative inputs differ from the final recorded checksums.",
            },
        )
        print("BASELINE_MISMATCH", ",".join(mismatches))
        return 2
    identifiers = document_ids()
    try:
        before = measure_graph()
    except Exception as exc:
        (FEO014 / "reports/graph_before_error.txt").write_text(scrub(traceback.format_exc()), encoding="utf-8")
        dump_json(
            FEO014 / "FEO014_TASK_MANIFEST.json",
            {"task_id": "FEO-014", "date": TASK_DATE, "completion_status": "blocked", "reason": scrub(str(exc))},
        )
        print("GRAPH_UNAVAILABLE")
        return 2
    before_counts = before["counts"]
    if (
        before_counts.get("node_count") != EXPECTED_NODES
        or before_counts.get("relationship_count") != EXPECTED_RELATIONSHIPS
        or before_counts.get("annotated_text_count") != EXPECTED_DOCUMENTS
        or sorted(before["document_ids"]) != sorted(identifiers)
    ):
        dump_json(FEO014 / "reports/graph_before.json", before)
        dump_json(
            FEO014 / "FEO014_TASK_MANIFEST.json",
            {
                "task_id": "FEO-014",
                "date": TASK_DATE,
                "completion_status": "invalid",
                "reason": "Graph counts before the run do not match the frozen baseline.",
                "graph_counts_before": before_counts,
            },
        )
        print("GRAPH_BASELINE_INVALID", before_counts)
        return 2
    rerun = FEO014 / "rerun"
    if rerun.exists():
        shutil.rmtree(rerun)
    copy_extraction(rerun, identifiers)
    write_identifier_policy()
    summaries = populate_root(rerun, identifiers, validate_shacl=True)
    repeat = FEO014 / "validation/determinism_run2"
    if repeat.exists():
        shutil.rmtree(repeat)
    copy_extraction(repeat, identifiers)
    populate_root(repeat, identifiers, validate_shacl=False)
    left = hash_tree_files(rerun, SEMANTIC_GLOBS)
    right = hash_tree_files(repeat, SEMANTIC_GLOBS)
    missing = sorted(set(left) - set(right))
    extra = sorted(set(right) - set(left))
    different = sorted(key for key in left.keys() & right.keys() if left[key] != right[key])
    determinism = {
        "pass": not missing and not extra and not different,
        "compared_files": len(left),
        "missing_count": len(missing),
        "extra_count": len(extra),
        "different_count": len(different),
        "different": different[:30],
        "missing_in_second": missing[:30],
        "extra_in_second": extra[:30],
    }
    write_determinism(determinism)
    try:
        after = measure_graph()
    except Exception:
        (FEO014 / "reports/graph_after_error.txt").write_text(scrub(traceback.format_exc()), encoding="utf-8")
        after = {"counts": {}, "document_ids": []}
    after_counts = after.get("counts") or {}
    graph_ok = (
        after_counts.get("node_count") == EXPECTED_NODES
        and after_counts.get("relationship_count") == EXPECTED_RELATIONSHIPS
        and after_counts.get("annotated_text_count") == EXPECTED_DOCUMENTS
        and sorted(after.get("document_ids") or []) == sorted(identifiers)
    )
    dump_json(FEO014 / "reports/graph_counts.json", {"before": before, "after": after, "unchanged": graph_ok})
    hashes_after = protected_hashes()
    checksum_mismatches = write_integrity(hashes_before, hashes_after, before_counts, after_counts, graph_ok)
    if not graph_ok or checksum_mismatches:
        dump_json(
            FEO014 / "FEO014_TASK_MANIFEST.json",
            {
                "task_id": "FEO-014",
                "date": TASK_DATE,
                "generated_at_local": generated_at,
                "completion_status": "invalid",
                "reason": "Graph counts or protected checksums changed. No repair was attempted.",
                "graph_counts_before": before_counts,
                "graph_counts_after": after_counts,
                "checksum_mismatches": checksum_mismatches,
            },
        )
        print("INVALID", graph_ok, checksum_mismatches)
        return 2
    corrections = correction_tables(rerun, identifiers)
    write_discrepancy(corrections["discrepancies"])
    crosswalk = build_crosswalk(corrections["mentions"])
    assertion_rows = build_assertion_delta(corrections["mentions"], corrections["times"])
    document_delta = build_document_delta(assertion_rows, crosswalk)
    reference_rows, _unused = build_reference_crosswalk(crosswalk)
    review_rows = build_review_package(
        corrections["mentions"], corrections["times"], assertion_rows, reference_rows
    )
    shacl = shacl_package(summaries)
    counts = population_counts(summaries, shacl["eligible"])
    before_collisions = collision_counts(FEO011)
    after_collisions = collision_counts(rerun)
    identifier_only = sum(1 for row in crosswalk if row["semantic_identity_changed"] != "true")
    remaining = [
        "Independent SHACL confirmation with a second engine was not run.",
        "Document 124259 preserves a source-normalisation discrepancy between 2008-09 and the wording of 2007.",
        "Human delta review has not been completed. Correctness metrics were not calculated.",
    ]
    if shacl["exceptions"]:
        remaining.append(
            f"{len({row['document_id'] for row in shacl['exceptions']})} documents still have core SHACL violations."
        )
    if not determinism["pass"]:
        remaining.append("The second population run did not match the first.")
    readiness = (
        "Ready for human delta review."
        if determinism["pass"] and graph_ok and not checksum_mismatches
        else "Not ready for human delta review."
    )
    stats = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "branch": info.get("branch"),
        "commit": info.get("commit"),
        "ontology_match": True,
        "candidate_collisions_before": before_collisions["candidate_ids_reused"],
        "candidate_collisions_after": after_collisions["candidate_ids_reused"],
        "decision_collisions_before": before_collisions["decision_ids_reused"],
        "decision_collisions_after": after_collisions["decision_ids_reused"],
        "documents": len(summaries),
        "candidates": next(row["feo014_count"] for row in counts if row["metric"] == "candidates"),
        "decisions": next(row["feo014_count"] for row in counts if row["metric"] == "decisions"),
        "shacl_engine": shacl.get("engine"),
        "release_eligible": len(shacl["eligible"]),
        "shacl_conforms": shacl["consolidated"].get("conforms"),
        "shacl_exception_documents": len({row["document_id"] for row in shacl["exceptions"]}),
        "semantic_triples": len(assertion_rows),
        "identifier_only_rows": identifier_only,
        "review_rows": len(review_rows),
        "determinism": "pass" if determinism["pass"] else "fail",
        "nodes_before": before_counts.get("node_count"),
        "nodes_after": after_counts.get("node_count"),
        "relationships_before": before_counts.get("relationship_count"),
        "relationships_after": after_counts.get("relationship_count"),
        "documents_before": before_counts.get("annotated_text_count"),
        "documents_after": after_counts.get("annotated_text_count"),
        "remaining": remaining,
        "readiness": readiness,
    }
    write_review_markdown(stats)
    manifest = {
        "task_id": "FEO-014",
        "date": TASK_DATE,
        "generated_at_local": stats["generated_at"],
        "branch": info.get("branch"),
        "commit": info.get("commit"),
        "ontology_checksum": hashes_before["ontology"],
        "shape_checksums": {
            "core": hashes_before["core_shapes"],
            "supplemental": hashes_before["supplemental_shapes"],
            "extension": hashes_before["extension_shapes"],
        },
        "feo009_rule_checksums": {
            "rules_tree": hashes_before["feo009_rules"],
            "affected_market_rules": hashes_before["affected_market_rules"],
            "entity_rules_extension": hashes_before["entity_rules_extension"],
            "market_change_rules": hashes_before["market_change_rules"],
            "temporal_rules": hashes_before["temporal_rules"],
            "value_and_evidence_rules": hashes_before["value_and_evidence_rules"],
        },
        "adapter_version": "feo014-adapter-0.1.0",
        "identifier_policy": "feo014-identifier-policy-v2",
        "correction_ids": [row["correction_id"] for row in corrections["mentions"] + corrections["times"]],
        "graph_counts_before": before_counts,
        "graph_counts_after": after_counts,
        "document_inventory": identifiers,
        "output_checksums": {
            "rerun_candidates": tree_hash(rerun / "candidates"),
            "rerun_decisions": tree_hash(rerun / "decisions"),
            "rerun_rdf": tree_hash(rerun / "rdf"),
        },
        "tests": {"status": "pending_pytest"},
        "shacl": {
            "engine": shacl.get("engine"),
            "second_engine": False,
            "release_eligible_documents": shacl["eligible"],
            "consolidated_conforms": shacl["consolidated"].get("conforms"),
            "exception_documents": sorted({row["document_id"] for row in shacl["exceptions"]}),
        },
        "delta_counts": {
            "changed_triples": len(assertion_rows),
            "identifier_rows": len(crosswalk),
            "identifier_only_rows": identifier_only,
            "documents_with_semantic_change": sum(1 for row in document_delta if row["change_class"] == "semantic_change"),
        },
        "review_workload": len(review_rows),
        "population_counts": {row["metric"]: row["feo014_count"] for row in counts},
        "determinism": determinism,
        "candidate_collisions_before": before_collisions,
        "candidate_collisions_after": after_collisions,
        "completion_status": "complete" if determinism["pass"] and shacl["consolidated"].get("conforms") else "partial",
        "password_recorded": False,
    }
    if manifest["completion_status"] == "complete" and shacl["exceptions"]:
        manifest["completion_status"] = "partial"
        manifest["partial_reason"] = "Core SHACL violations remain. Shapes were not weakened."
    dump_json(FEO014 / "FEO014_TASK_MANIFEST.json", manifest)
    dump_json(FEO014 / "reports/run_summary.json", stats)
    print(manifest["completion_status"], "review", len(review_rows), "eligible", len(shacl["eligible"]))
    return 0


def resume() -> int:
    """Finish reports from the completed population. Does not repopulate."""
    for relative in (
        "reports",
        "corrections",
        "validation",
        "evaluation",
        "delta/identifiers",
        "delta/assertions",
        "delta/documents",
        "delta/review",
    ):
        (FEO014 / relative).mkdir(parents=True, exist_ok=True)
    identifiers = document_ids()
    info = git_info()
    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    hashes_before = protected_hashes()
    mismatches = [key for key, value in expected_recorded_hashes().items() if hashes_before.get(key) != value]
    if mismatches:
        print("BASELINE_MISMATCH", ",".join(mismatches))
        return 2
    measured = measure_graph()
    counts = measured["counts"]
    graph_ok = (
        counts.get("node_count") == EXPECTED_NODES
        and counts.get("relationship_count") == EXPECTED_RELATIONSHIPS
        and counts.get("annotated_text_count") == EXPECTED_DOCUMENTS
        and sorted(measured["document_ids"]) == sorted(identifiers)
    )
    if not graph_ok:
        dump_json(FEO014 / "reports/graph_resume.json", measured)
        print("GRAPH_COUNT_CHANGED", counts)
        return 2
    determinism = load_json(FEO014 / "validation/determinism.json")
    summaries = [{"document_id": document_id} for document_id in identifiers]
    rerun = FEO014 / "rerun"
    corrections = correction_tables(rerun, identifiers)
    write_discrepancy(corrections["discrepancies"])
    crosswalk = build_crosswalk(corrections["mentions"])
    assertion_rows = build_assertion_delta(corrections["mentions"], corrections["times"])
    document_delta = build_document_delta(assertion_rows, crosswalk)
    reference_rows, _unused = build_reference_crosswalk(crosswalk)
    review_rows = build_review_package(
        corrections["mentions"], corrections["times"], assertion_rows, reference_rows
    )
    shacl = shacl_package(summaries)
    population = population_counts(summaries, shacl["eligible"])
    before_collisions = collision_counts(FEO011)
    after_collisions = collision_counts(rerun)
    identifier_only = sum(1 for row in crosswalk if row["semantic_identity_changed"] != "true")
    checksum_mismatches = write_integrity(hashes_before, protected_hashes(), counts, counts, graph_ok)
    remaining = [
        "Independent SHACL confirmation with a second engine was not run.",
        "Document 124259 preserves a source-normalisation discrepancy between 2008-09 and the wording of 2007.",
        "Human delta review has not been completed. Correctness metrics were not calculated.",
    ]
    if shacl["exceptions"]:
        remaining.append(
            f"{len({row['document_id'] for row in shacl['exceptions']})} documents still have core SHACL violations."
        )
    if not determinism.get("pass"):
        remaining.append("The second population run did not match the first.")
    if checksum_mismatches:
        remaining.append("Protected checksums changed: " + ", ".join(checksum_mismatches))
    readiness = (
        "Ready for human delta review."
        if determinism.get("pass") and graph_ok and not checksum_mismatches
        else "Not ready for human delta review."
    )
    stats = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "branch": info.get("branch"),
        "commit": info.get("commit"),
        "ontology_match": True,
        "candidate_collisions_before": before_collisions["candidate_ids_reused"],
        "candidate_collisions_after": after_collisions["candidate_ids_reused"],
        "decision_collisions_before": before_collisions["decision_ids_reused"],
        "decision_collisions_after": after_collisions["decision_ids_reused"],
        "documents": len(summaries),
        "candidates": next(row["feo014_count"] for row in population if row["metric"] == "candidates"),
        "decisions": next(row["feo014_count"] for row in population if row["metric"] == "decisions"),
        "shacl_engine": shacl.get("engine"),
        "release_eligible": len(shacl["eligible"]),
        "shacl_conforms": shacl["consolidated"].get("conforms"),
        "shacl_exception_documents": len({row["document_id"] for row in shacl["exceptions"]}),
        "semantic_triples": len(assertion_rows),
        "identifier_only_rows": identifier_only,
        "review_rows": len(review_rows),
        "determinism": "pass" if determinism.get("pass") else "fail",
        "nodes_before": counts.get("node_count"),
        "nodes_after": counts.get("node_count"),
        "relationships_before": counts.get("relationship_count"),
        "relationships_after": counts.get("relationship_count"),
        "documents_before": counts.get("annotated_text_count"),
        "documents_after": counts.get("annotated_text_count"),
        "remaining": remaining,
        "readiness": readiness,
    }
    write_review_markdown(stats)
    manifest = {
        "task_id": "FEO-014",
        "date": TASK_DATE,
        "generated_at_local": stats["generated_at"],
        "branch": info.get("branch"),
        "commit": info.get("commit"),
        "ontology_checksum": hashes_before["ontology"],
        "shape_checksums": {
            "core": hashes_before["core_shapes"],
            "supplemental": hashes_before["supplemental_shapes"],
            "extension": hashes_before["extension_shapes"],
        },
        "feo009_rule_checksums": {
            "rules_tree": hashes_before["feo009_rules"],
            "affected_market_rules": hashes_before["affected_market_rules"],
            "entity_rules_extension": hashes_before["entity_rules_extension"],
            "market_change_rules": hashes_before["market_change_rules"],
            "temporal_rules": hashes_before["temporal_rules"],
            "value_and_evidence_rules": hashes_before["value_and_evidence_rules"],
        },
        "adapter_version": "feo014-adapter-0.1.0",
        "identifier_policy": "feo014-identifier-policy-v2",
        "correction_ids": [row["correction_id"] for row in corrections["mentions"] + corrections["times"]],
        "graph_counts_before": counts,
        "graph_counts_after": counts,
        "graph_note": "Counts were measured again after both population passes had already completed. The earlier before/after measurement is in reports/graph_counts.json.",
        "document_inventory": identifiers,
        "output_checksums": {
            "rerun_candidates": tree_hash(rerun / "candidates"),
            "rerun_decisions": tree_hash(rerun / "decisions"),
            "rerun_rdf": tree_hash(rerun / "rdf"),
        },
        "tests": {"status": "pending_pytest"},
        "shacl": {
            "engine": shacl.get("engine"),
            "second_engine": False,
            "release_eligible_documents": shacl["eligible"],
            "consolidated_conforms": shacl["consolidated"].get("conforms"),
            "exception_documents": sorted({row["document_id"] for row in shacl["exceptions"]}),
        },
        "delta_counts": {
            "changed_triples": len(assertion_rows),
            "identifier_rows": len(crosswalk),
            "identifier_only_rows": identifier_only,
            "documents_with_semantic_change": sum(1 for row in document_delta if row["change_class"] == "semantic_change"),
        },
        "review_workload": len(review_rows),
        "population_counts": {row["metric"]: row["feo014_count"] for row in population},
        "determinism": determinism,
        "candidate_collisions_before": before_collisions,
        "candidate_collisions_after": after_collisions,
        "completion_status": "complete" if determinism.get("pass") and shacl["consolidated"].get("conforms") else "partial",
        "password_recorded": False,
        "resume_started_local": generated_at,
    }
    if manifest["completion_status"] == "complete" and shacl["exceptions"]:
        manifest["completion_status"] = "partial"
        manifest["partial_reason"] = "Core SHACL violations remain. Shapes were not weakened."
    dump_json(FEO014 / "FEO014_TASK_MANIFEST.json", manifest)
    dump_json(FEO014 / "reports/run_summary.json", stats)
    print(manifest["completion_status"], "review", len(review_rows), "eligible", len(shacl["eligible"]))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        sys.stderr.write(scrub(traceback.format_exc()))
        raise
