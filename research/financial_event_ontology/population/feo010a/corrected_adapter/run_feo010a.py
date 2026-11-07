"""Run the corrected adapter twice on document 61327 from saved source records.

The graph is not queried. FEO-009 is called through EnrichmentEngine.run.
"""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADAPTER_ROOT = Path(__file__).resolve().parent
if str(ADAPTER_ROOT) not in sys.path:
    sys.path.insert(0, str(ADAPTER_ROOT))

from adapter.checks import (  # noqa: E402
    ontology_profile,
    prohibited_identifier_audit,
    public_term_audit,
    reasoner_check,
    validate_accepted,
)
from adapter.classification import (  # noqa: E402
    ANCHOR_COLUMNS,
    UNRESOLVED_COLUMNS,
    build_participant_groups,
    classify_time_anchors,
    unresolved_participant_rows,
)
from adapter.common import dump_json, load_json, sha256_file  # noqa: E402
from adapter.extraction.extractor import load_config, load_saved_bundle  # noqa: E402
from adapter.identity import (  # noqa: E402
    ADAPTER_VERSION,
    MAPPING_VERSION,
    feo010_mention_local_key,
)
from adapter.materialisation.materialise import direct_domain_triples, materialise  # noqa: E402
from adapter.materialisation.mentions import expand_canonical_mentions  # noqa: E402
from adapter.normalisation.normalise import attach_accepted_markets, ensure_engine_path, normalise  # noqa: E402
from adapter.run import _metrics, _validate_candidates, _validate_records, _write_traces  # noqa: E402
from adapter.safety.guards import repo_root  # noqa: E402

DOC = "61327"
CORPUS = "meantime-en-stock"
FEO010 = repo_root() / "research/financial_event_ontology/population/feo010"


def _engine():
    ensure_engine_path()
    from engine.engine import EnrichmentEngine
    from engine.identifiers import resource_iri, safe_local_key
    from engine.rdf_emitter import emit_profile
    from engine.rule_loader import iter_rule_files

    return EnrichmentEngine, emit_profile, iter_rule_files, resource_iri, safe_local_key


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def _tree_hash(path: Path) -> str:
    digest = hashlib.sha256()
    if path.is_file():
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
        return digest.hexdigest()
    for file in sorted(item for item in path.rglob("*") if item.is_file()):
        if "__pycache__" in file.parts or file.suffix == ".pyc":
            continue
        relative = str(file.relative_to(path))
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(file.read_bytes())
    return digest.hexdigest()


def protected_hashes() -> dict:
    root = repo_root()
    feo = root / "research/financial_event_ontology"
    return {
        "rc2_ttl": _tree_hash(feo / "ontology/feo007a/ontology/fneo-0.1.0-rc2.ttl"),
        "feo007a_ontology": _tree_hash(feo / "ontology/feo007a/ontology"),
        "feo007a_shapes": _tree_hash(feo / "ontology/feo007a/validation"),
        "feo008": _tree_hash(feo / "mappings/feo008"),
        "feo009": _tree_hash(feo / "enrichment/feo009"),
        "feo010": _tree_hash(feo / "population/feo010"),
        "corpus_annotated_stock": _tree_hash(root / "src/textgraphx/datastore/annotated/corpus_stock"),
        "corpus_naf_stock": _tree_hash(root / "src/textgraphx/datastore/meantime_newsreader_english_raw_NAF/corpus_stock"),
    }


def _block_graph_driver() -> None:
    import neo4j

    def _refuse(*_args, **_kwargs):
        raise RuntimeError("FEO-010A refused a graph driver call. Saved records are the source.")

    neo4j.GraphDatabase.driver = _refuse


def execute(destination: Path) -> dict:
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    config = load_config()
    bundle = load_saved_bundle(DOC)
    record_errors = _validate_records(bundle)
    if record_errors:
        raise RuntimeError("Saved records failed schema validation: " + "; ".join(record_errors[:8]))
    normalised = normalise(bundle, CORPUS)
    _validate_candidates(normalised["candidates"])
    EnrichmentEngine, emit_profile, iter_rule_files, _resource_iri, _safe = _engine()
    engine = EnrichmentEngine()
    publication = normalised["publication"] or {}
    envelope = {
        "fixture_id": "feo010a-doc-" + DOC,
        "corpus": CORPUS,
        "documents": [
            {
                "document_id": DOC,
                "label": bundle["documents"][0].get("textual_form") or DOC,
                "publication_lexical": publication.get("lexical") or "",
                "publication_normalised": publication.get("normalised") or "",
                "time_key": "publication",
            }
        ],
        "candidates": normalised["candidates"],
    }
    import copy

    preliminary = engine.run(copy.deepcopy(envelope))
    attach_notes = attach_accepted_markets(normalised["candidates"], preliminary["decisions"])
    _validate_candidates(normalised["candidates"])
    recorded = engine.run(envelope)
    graphs = materialise(recorded, emit_profile)
    graphs["accepted"] = expand_canonical_mentions(
        graphs["accepted"], normalised["candidates"], recorded["decisions"], bundle, CORPUS
    )
    candidate_dir = destination / "candidates" / DOC
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
    decision_dir = destination / "decisions" / DOC
    dump_json(decision_dir / "decisions.json", recorded["decisions"])
    dump_json(
        decision_dir / "summary.json",
        {
            "candidate_count": len(recorded["candidates"]),
            "decision_count": len(recorded["decisions"]),
            "by_status": dict(Counter(item["status"] for item in recorded["decisions"])),
            "by_profile": {profile: len(items) for profile, items in recorded["by_profile"].items()},
            "adapter_version": ADAPTER_VERSION,
        },
    )
    paths = {
        "accepted": destination / "rdf" / "accepted" / f"{DOC}-core.ttl",
        "review": destination / "rdf" / "review-required" / f"{DOC}-review.ttl",
        "rejected": destination / "rdf" / "rejected" / f"{DOC}-rejected.ttl",
        "experimental": destination / "rdf" / "experimental" / f"{DOC}-experimental.ttl",
    }
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
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
    prohibited = prohibited_identifier_audit("\n".join(graphs[name] for name in ("accepted", "review", "rejected")))
    reasoner = reasoner_check(graphs["accepted"], ontology)
    rule_checksums = {path.name: sha256_file(path) for path in iter_rule_files()}
    trace_count = _write_traces(recorded["decisions"], normalised["candidates"], shacl, destination / "reports" / "traces")
    metrics = _metrics(bundle, normalised, recorded, shacl, graphs)
    manifest = {
        "document_id": DOC,
        "adapter_version": ADAPTER_VERSION,
        "population_profile": "CORE_DETERMINISTIC",
        "source": "saved FEO-010 sanitised records; graph not queried",
        "graphs": {name: str(path.relative_to(destination)) for name, path in paths.items()},
        "checksums": {name: sha256_file(path) for name, path in paths.items()},
        "review_direct_domain_triples": graphs["review_direct_triples"],
        "rejected_direct_domain_triples": graphs["rejected_direct_triples"],
    }
    dump_json(destination / "rdf" / "manifests" / f"{DOC}-dataset-manifest.json", manifest)
    dump_json(destination / "validation" / "shacl_accepted.json", shacl)
    dump_json(destination / "validation" / "ontology_profile.json", profile)
    dump_json(destination / "validation" / "public_term_audit.json", terms)
    dump_json(destination / "validation" / "prohibited_identifier_audit.json", prohibited)
    dump_json(destination / "validation" / "reasoner.json", reasoner)
    dump_json(destination / "reports" / "run_clock.json", {"generated_at": datetime.now().astimezone().isoformat(timespec="seconds")})
    return {
        "bundle": bundle,
        "normalised": normalised,
        "result": recorded,
        "graphs": graphs,
        "shacl": shacl,
        "reasoner": reasoner,
        "terms": terms,
        "prohibited": prohibited,
        "profile": profile,
        "metrics": metrics,
        "trace_count": trace_count,
        "rule_checksums": rule_checksums,
        "shape_checksums": {
            "core": sha256_file(core_shapes),
            "supplemental": sha256_file(supplemental),
            "extension_not_applied": sha256_file(extension),
        },
        "ontology_checksum": sha256_file(ontology),
        "paths": paths,
        "destination": destination,
    }


def _fingerprint(directory: Path) -> dict:
    found = {}
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        relative = str(path.relative_to(directory))
        if relative == "reports/run_clock.json":
            continue
        found[relative] = sha256_file(path)
    return found


def _copy_canonical(source: Path) -> None:
    for name in ("candidates", "decisions", "rdf", "reports"):
        target = ROOT / name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source / name, target)
    validation = ROOT / "validation"
    validation.mkdir(parents=True, exist_ok=True)
    for path in (source / "validation").glob("*.json"):
        shutil.copy2(path, validation / path.name)


def _git(args: list[str]) -> str:
    completed = subprocess.run(["git", *args], cwd=repo_root(), check=False, capture_output=True, text=True)
    return (completed.stdout or "").strip()


def _mention_iri(kind: str, local: str, resource_iri, safe_local_key) -> str:
    return resource_iri("mention", kind, CORPUS, DOC, safe_local_key(local, purpose="mention"))


def write_analysis(stats: dict) -> dict:
    bundle = stats["bundle"]
    _engine_bits = _engine()
    resource_iri, safe_local_key = _engine_bits[3], _engine_bits[4]
    anchors = classify_time_anchors(bundle)
    groups = build_participant_groups(bundle)
    # Prefer candidate ids assigned during normalisation.
    by_pair = {
        (row["event_source_id"], row["participant_source_id"]): row
        for row in stats["normalised"]["deduplication"]
    }
    for group in groups:
        saved = by_pair.get((group["event_source_id"], group["participant_source_id"]), {})
        group["candidate_id"] = saved.get("candidate_id") or ""
        group["participation_key"] = saved.get("participation_key") or ""
    unresolved = unresolved_participant_rows(groups)
    _write_csv(ROOT / "analysis/temporal/time_anchor_classification.csv", anchors, ANCHOR_COLUMNS)
    _write_csv(ROOT / "analysis/participants/unresolved_participant_paths.csv", unresolved, UNRESOLVED_COLUMNS)
    dedup_fields = [
        "path_id", "candidate_id", "event_source_id", "participant_source_id", "participant_candidate_kind",
        "selected_relation", "mapping_version", "participation_key", "primary_relationship", "supporting_path_ids",
        "source_roles", "operational_path_count", "classification", "normalisation_action", "duplicate_path",
        "financial_mapping_eligible", "review_required", "notes",
    ]
    dedup_rows = []
    for group in groups:
        dedup_rows.append(
            {
                "path_id": group["path_id"],
                "candidate_id": group.get("candidate_id") or "",
                "event_source_id": group["event_source_id"],
                "participant_source_id": group["participant_source_id"],
                "participant_candidate_kind": "entity_participant" if group.get("emit") or group.get("candidate_id") else group["classification"],
                "selected_relation": "hasParticipant" if group.get("candidate_id") else "",
                "mapping_version": MAPPING_VERSION if group.get("candidate_id") else "",
                "participation_key": group.get("participation_key") or "",
                "primary_relationship": group["primary_relationship"],
                "supporting_path_ids": "|".join(group["source_records"]),
                "source_roles": "|".join(group["source_roles"]),
                "operational_path_count": group["operational_path_count"],
                "classification": group["classification"],
                "normalisation_action": group["normalisation_action"],
                "duplicate_path": group["duplicate_path"],
                "financial_mapping_eligible": group["financial_mapping_eligible"],
                "review_required": group["review_required"],
                "notes": group["notes"],
            }
        )
    _write_csv(ROOT / "evaluation/participant_deduplication.csv", dedup_rows, dedup_fields)
    identity = stats["normalised"]["mention_identity"]
    # FEO-010 representative keys.
    feo010_candidates = load_json(FEO010 / "candidates" / DOC / "candidates.json")
    feo010_key_by_mention = {}
    for candidate in feo010_candidates:
        mentions = candidate.get("source_mention_ids") or []
        key = (candidate.get("features") or {}).get("mention_key")
        if mentions and key:
            feo010_key_by_mention.setdefault(mentions[0], key)
    decisions = stats["result"]["decisions"]
    assertion_iris = "\n".join(json.dumps(item) for item in decisions)
    graph_text = stats["graphs"]["accepted"]
    cross = []
    for mention in sorted(bundle["mentions"], key=lambda item: item["source_identifier"]):
        info = identity[mention["source_identifier"]]
        kind = info["mention_kind"]
        feo010_local = feo010_key_by_mention.get(mention["source_identifier"])
        feo010_iri = _mention_iri(kind, feo010_local, resource_iri, safe_local_key) if feo010_local else ""
        feo010a_iri = _mention_iri(kind, info["local_key"], resource_iri, safe_local_key)
        users = [
            candidate["candidate_id"]
            for candidate in stats["normalised"]["candidates"]
            if mention["source_identifier"] in (candidate.get("source_mention_ids") or [])
        ]
        cross.append(
            {
                "source_mention_id": mention["source_identifier"],
                "mention_kind": kind,
                "document_id": DOC,
                "token_start": mention.get("token_start"),
                "token_end": mention.get("token_end"),
                "character_start": "" if mention.get("character_start") is None else mention.get("character_start"),
                "character_end": "" if mention.get("character_end") is None else mention.get("character_end"),
                "textual_form": mention.get("textual_form") or "",
                "feo010_iri": feo010_iri,
                "feo010a_iri": feo010a_iri,
                "candidate_count": len(users),
                "assertion_count": graph_text.count(feo010a_iri) + assertion_iris.count(feo010a_iri),
                "collision_detected": "false",
                "resolution": "canonical_annotation" if info["group_size"] == 1 else "consolidated_coextensive_annotation",
                "notes": "" if info["group_size"] == 1 else "co-extensive source records share one textual-mention IRI; retained annotation " + info["canonical_annotation_id"],
                "local_key": info["local_key"],
            }
        )
    by_iri = {}
    for row in cross:
        by_iri.setdefault(row["feo010a_iri"], []).append(row["source_mention_id"])
    for row in cross:
        members = by_iri[row["feo010a_iri"]]
        spans = {
            (item["token_start"], item["token_end"], item["textual_form"])
            for item in cross
            if item["feo010a_iri"] == row["feo010a_iri"]
        }
        collision = len(spans) > 1
        row["collision_detected"] = "true" if collision else "false"
        if collision:
            row["notes"] = "distinct textual spans resolved to one IRI"
    _write_csv(
        ROOT / "analysis/identifiers/mention_identity_crosswalk.csv",
        cross,
        [
            "source_mention_id", "mention_kind", "document_id", "token_start", "token_end",
            "character_start", "character_end", "textual_form", "feo010_iri", "feo010a_iri",
            "candidate_count", "assertion_count", "collision_detected", "resolution", "notes",
        ],
    )
    return {
        "anchors": anchors,
        "groups": groups,
        "unresolved": unresolved,
        "crosswalk": cross,
    }


def main() -> int:
    _block_graph_driver()
    before = protected_hashes()
    run1 = ROOT / "runs" / "run1"
    run2 = ROOT / "runs" / "run2"
    first = execute(run1)
    second = execute(run2)
    fp1 = _fingerprint(run1)
    fp2 = _fingerprint(run2)
    differences = [name for name in sorted(set(fp1) | set(fp2)) if fp1.get(name) != fp2.get(name)]
    determinism_ok = not differences
    _copy_canonical(run1)
    after = protected_hashes()
    hash_ok = before == after
    analysis = write_analysis(first)
    dump_json(ROOT / "validation" / "protected_hashes_before.json", before)
    dump_json(ROOT / "validation" / "protected_hashes_after.json", after)
    (ROOT / "validation" / "corrected_determinism_report.md").write_text(
        "\n".join(
            [
                "# Determinism of the corrected adapter",
                "",
                "The corrected adapter was executed twice on document 61327 from the same saved source records.",
                "Run clocks may differ. Every other file under runs/run1 and runs/run2 was compared by SHA-256.",
                "",
                f"Result: {'pass' if determinism_ok else 'fail'}.",
                f"Files compared: {len(fp1)}.",
                "",
                "## Differences",
                "",
                *(differences or ["- none"]),
                "",
                "Compared artefacts: mention IRIs in the RDF graphs, participation candidates, decisions, assertion IRIs,",
                "accepted RDF, review RDF, rejected RDF, experimental RDF, and output manifests apart from timestamps.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print("determinism", determinism_ok, "files", len(fp1), "differences", len(differences))
    print("hash_ok", hash_ok)
    print("shacl", first["shacl"]["conforms"], first["shacl"]["violation_count"], first["shacl"]["warning_count"], first["shacl"]["info_count"])
    print("decisions", Counter(item["status"] for item in first["result"]["decisions"]))
    print("anchors", Counter(row["classification"] for row in analysis["anchors"]))
    print("unresolved", len(analysis["unresolved"]), Counter(row["classification"] for row in analysis["unresolved"]))
    dump_json(
        ROOT / "runs" / "run_status.json",
        {
            "determinism_ok": determinism_ok,
            "differences": differences,
            "hash_ok": hash_ok,
            "shacl": {
                "conforms": first["shacl"]["conforms"],
                "violations": first["shacl"]["violation_count"],
                "warnings": first["shacl"]["warning_count"],
                "information": first["shacl"]["info_count"],
            },
            "reasoner": first["reasoner"],
            "trace_count": first["trace_count"],
        },
    )
    return 0 if determinism_ok and hash_ok and first["shacl"]["conforms"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
