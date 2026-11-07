"""Populate one document with the corrected adapter and the FEO-009 engine."""

from __future__ import annotations

import copy
import json
from collections import Counter
from pathlib import Path

from rdflib import Graph, URIRef
from rdflib.namespace import OWL

from driver.common import (
    ADAPTER_ROOT,
    CORPUS,
    REPO,
    ensure_adapter_path,
    excerpt,
    local_name,
    scrub,
)

ensure_adapter_path()

from adapter.checks import validate_accepted  # noqa: E402
from adapter.classification import UNRESOLVED_COLUMNS, classify_time_anchors, unresolved_participant_rows  # noqa: E402
from adapter.common import dump_json  # noqa: E402
from adapter.identity import ADAPTER_VERSION, MAPPING_VERSION  # noqa: E402
from adapter.materialisation.materialise import (  # noqa: E402
    deterministic_turtle,
    direct_domain_triples,
    materialise,
)
from adapter.materialisation.mentions import expand_canonical_mentions  # noqa: E402
from adapter.normalisation.normalise import attach_accepted_markets, ensure_engine_path, normalise  # noqa: E402
from adapter.run import _validate_records  # noqa: E402

FINANCIAL_TARGETS = {
    "MarketIndex",
    "EquityMarket",
    "MarketChangeEvent",
    "NumericalValue",
    "PercentageValue",
    "hasAffectedMarket",
    "hasEventTime",
}
PARTICIPANT_COLUMNS = {
    "valid_entity_participant": "valid_entity_participants",
    "value_argument": "value_arguments",
    "temporal_argument": "temporal_arguments",
    "event_argument": "event_arguments",
    "mention_without_canonical_entity": "mention_without_entity",
    "frame_argument_without_entity": "frame_argument_without_entity",
    "unresolved_reference": "unresolved_references",
    "duplicate_operational_path": "duplicate_paths",
    "structural_only": "structural_only",
    "out_of_scope": "out_of_scope",
    "malformed": "malformed",
    "unresolved": "unresolved",
}
EMPTY_EXTENSION = (
    "# EXTENSION_REVIEWED profile.\n"
    "# No extension-profile decisions were emitted for this document.\n"
    "# This graph is not part of the accepted core.\n"
)
EMPTY_CANDIDATE = (
    "# CANDIDATE_REVIEW profile.\n"
    "# No candidate-review decisions were emitted for this document.\n"
    "# This graph is not part of the accepted core.\n"
)
EMPTY_EXPERIMENTAL = (
    "# EXPERIMENTAL_TEMPORAL profile.\n"
    "# No experimental-profile decisions were emitted for this document.\n"
    "# Source ordering relations are inventoried separately and are not accepted facts.\n"
    "# This graph is not part of the accepted core.\n"
)


def _engine():
    ensure_engine_path()
    from engine.engine import EnrichmentEngine
    from engine.identifiers import resource_iri, safe_local_key
    from engine.rdf_emitter import emit_profile
    from engine.rule_loader import iter_rule_files

    return EnrichmentEngine, emit_profile, iter_rule_files, resource_iri, safe_local_key


def _schema(name: str) -> dict:
    path = REPO / "research/financial_event_ontology/enrichment/feo009/rules/schemas" / name
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_candidates(candidates: list[dict]) -> tuple[list[dict], list[dict]]:
    import jsonschema

    schema = _schema("normalised_candidate.schema.json")
    valid = []
    errors = []
    for candidate in candidates:
        try:
            jsonschema.validate(candidate, schema)
            valid.append(candidate)
        except jsonschema.ValidationError as exc:
            errors.append(
                {
                    "document_id": candidate.get("document_id") or "",
                    "candidate_id": candidate.get("candidate_id") or "",
                    "candidate_kind": candidate.get("candidate_kind") or "",
                    "schema_valid": "false",
                    "error_message": exc.message,
                    "notes": "Invalid candidate reported and excluded from the rule engine.",
                }
            )
    return valid, errors


def _validate_decisions(decisions: list[dict]) -> list[dict]:
    import jsonschema

    schema = _schema("enrichment_decision.schema.json")
    errors = []
    for decision in decisions:
        try:
            jsonschema.validate(decision, schema)
        except jsonschema.ValidationError as exc:
            errors.append(
                {
                    "document_id": decision.get("document_id") or "",
                    "candidate_id": decision.get("decision_id") or "",
                    "candidate_kind": "decision",
                    "schema_valid": "false",
                    "error_message": exc.message,
                    "notes": "Invalid decision reported and retained.",
                }
            )
    return errors


def _repair_turtle_literals(text: str) -> str:
    """Escape raw control characters inside double-quoted Turtle literals.

    The corrected adapter's deterministic writer copies newline characters
    into quoted literals. The literal value is preserved as an escaped
    newline. This is a serialisation repair, not a change to a rule.
    """
    if not text or text.lstrip().startswith("#"):
        return text
    pieces = []
    index = 0
    length = len(text)
    while index < length:
        character = text[index]
        if character != '"':
            pieces.append(character)
            index += 1
            continue
        pieces.append(character)
        index += 1
        while index < length:
            character = text[index]
            if character == "\\":
                pieces.append(character)
                if index + 1 < length:
                    pieces.append(text[index + 1])
                    index += 2
                    continue
                index += 1
                continue
            if character == '"':
                pieces.append(character)
                index += 1
                break
            if character == "\n":
                pieces.append("\\n")
            elif character == "\r":
                pieces.append("\\r")
            elif character == "\t":
                pieces.append("\\t")
            else:
                pieces.append(character)
            index += 1
    return "".join(pieces)


def _parse(text: str) -> Graph:
    graph = Graph()
    if text and text.strip() and not text.lstrip().startswith("#"):
        graph.parse(data=text, format="turtle")
    return graph


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8")


def _mention_row(bundle: dict, normalised: dict, candidates: list[dict], resource_iri, safe_local_key) -> dict:
    document_id = bundle["document_id"]
    grouped: dict[str, dict] = {}
    span_keys: dict[str, set] = {}
    for source_id, info in (normalised.get("mention_identity") or {}).items():
        local = info["local_key"]
        grouped.setdefault(local, info)
        span_keys.setdefault(local, set()).add(
            (info.get("mention_kind"), info.get("token_start"), info.get("token_end"), info.get("textual_form"))
        )
    iris = []
    collisions = 0
    for local, info in grouped.items():
        iri = resource_iri(
            "mention",
            info.get("mention_kind") or "mention",
            CORPUS,
            document_id,
            safe_local_key(str(local), purpose="mention"),
        )
        iris.append(iri)
        if len(span_keys[local]) > 1:
            collisions += 1
    use = Counter()
    for candidate in candidates:
        keys = set((candidate.get("features") or {}).get("mention_identity_by_source", {}).values())
        for key in keys:
            use[key] += 1
    coextensive = 0
    seen = set()
    for info in (normalised.get("mention_identity") or {}).values():
        local = info["local_key"]
        if local in seen:
            continue
        seen.add(local)
        if int(info.get("group_size") or 1) > 1:
            coextensive += int(info["group_size"])
    duplicate_iris = len(iris) - len(set(iris))
    status = "blocking" if collisions or duplicate_iris else "ok"
    return {
        "document_id": document_id,
        "source_mention_records": len(bundle["mentions"]),
        "public_mention_iris": len(set(iris)),
        "coextensive_source_records": coextensive,
        "candidate_reuse_count": sum(1 for value in use.values() if value > 1),
        "collisions": collisions,
        "duplicate_iris": duplicate_iris,
        "cross_document_collision": 0,
        "status": status,
        "notes": "Mentions stay document-scoped. Public IRIs include the document identifier.",
        "iris": sorted(set(iris)),
    }


def _participant_row(document_id: str, groups: list[dict]) -> dict:
    counts = Counter(group.get("classification") or "unresolved" for group in groups)
    raw = sum(int(group.get("operational_path_count") or 0) for group in groups)
    unexpected = sorted(set(counts) - set(PARTICIPANT_COLUMNS))
    row = {
        "document_id": document_id,
        "raw_operational_paths": raw,
        "normalised_groups": len(groups),
        "review_required": sum(1 for group in groups if str(group.get("review_required")) == "true"),
        "notes": "",
    }
    for classification, column in PARTICIPANT_COLUMNS.items():
        row[column] = counts.get(classification, 0)
    if unexpected:
        row["unresolved"] = int(row["unresolved"]) + sum(counts[name] for name in unexpected)
        row["notes"] = "Unexpected classifications counted as unresolved: " + ", ".join(unexpected)
    structural_emitted = sum(1 for group in groups if group.get("classification") == "structural_only" and group.get("emit"))
    if structural_emitted:
        row["notes"] = (row["notes"] + "; " if row["notes"] else "") + f"structural paths emitted: {structural_emitted}"
    row["structural_emitted"] = structural_emitted
    return row


def _policy(recorded: dict, graphs: dict) -> dict:
    accepted = _parse(graphs["accepted"])
    review = _parse(graphs["review"])
    rejected = _parse(graphs["rejected"])
    extension = _parse(graphs["extension"])
    candidate = _parse(graphs["candidate_review"])
    experimental = _parse(graphs["experimental"])
    review_direct = direct_domain_triples(graphs["review"])
    rejected_direct = direct_domain_triples(graphs["rejected"])
    same_as = 0
    for graph in (accepted, review, rejected, extension, candidate, experimental):
        same_as += len(list(graph.triples((None, OWL.sameAs, None))))
    missing_direct = []
    missing_qualified = []
    missing_evidence = []
    noncore_in_core = []
    by_id = {item["candidate_id"]: item for item in recorded.get("candidates") or []}
    for decision in recorded["decisions"]:
        profile = decision.get("profile")
        status = decision.get("status")
        target = decision.get("target_local_name") or ""
        subject = decision.get("subject_iri") or ""
        predicate = decision.get("predicate_iri") or ""
        object_iri = decision.get("object_iri") or ""
        in_core = False
        if subject and predicate and object_iri:
            in_core = (URIRef(subject), URIRef(predicate), URIRef(object_iri)) in accepted
        if profile != "CORE_DETERMINISTIC" and status == "accepted" and decision.get("direct_triple_eligible") and in_core:
            noncore_in_core.append(decision.get("decision_id") or "")
        if status != "accepted" and in_core and local_name(predicate) in {
            "hasAffectedMarket",
            "hasEventTime",
            "hasMarketDirection",
            "hasReportedValue",
            "hasParticipant",
            "precedes",
            "follows",
            "simultaneousWith",
            "occursDuring",
        }:
            noncore_in_core.append(decision.get("decision_id") or "")
        if profile != "CORE_DETERMINISTIC" or status != "accepted" or target not in FINANCIAL_TARGETS:
            continue
        candidate = by_id.get(decision.get("candidate_id"), {})
        if not str(candidate.get("textual_evidence") or "").strip():
            missing_evidence.append(decision.get("decision_id") or "")
        if (
            decision.get("direct_triple_eligible")
            and subject
            and predicate
            and (object_iri or decision.get("object_lexical"))
            and not in_core
        ):
            literal_present = bool(subject and predicate and any(accepted.triples((URIRef(subject), URIRef(predicate), None))))
            if object_iri or not literal_present:
                missing_direct.append(decision.get("decision_id") or "")
        if decision.get("qualified_assertion_required"):
            assertion = decision.get("assertion_iri") or ""
            if not assertion or (URIRef(assertion), None, None) not in accepted:
                missing_qualified.append(decision.get("decision_id") or "")
    return {
        "review_direct": len(review_direct),
        "rejected_direct": len(rejected_direct),
        "same_as": same_as,
        "missing_direct": len(missing_direct),
        "missing_qualified": len(missing_qualified),
        "missing_evidence": len(missing_evidence),
        "noncore_in_core": len(set(noncore_in_core)),
        "examples": {
            "missing_direct": missing_direct[:8],
            "missing_qualified": missing_qualified[:8],
            "missing_evidence": missing_evidence[:8],
            "noncore_in_core": sorted(set(noncore_in_core))[:8],
        },
    }


def _run_rules(bundle: dict, normalised: dict):
    EnrichmentEngine, emit_profile, _iter_rule_files, _resource_iri, _safe = _engine()
    document_id = bundle["document_id"]
    publication = normalised.get("publication") or {}
    label = ""
    if bundle["documents"]:
        label = bundle["documents"][0].get("textual_form") or document_id
    envelope = {
        "fixture_id": "feo011-doc-" + document_id,
        "corpus": CORPUS,
        "documents": [
            {
                "document_id": document_id,
                "label": label or document_id,
                "publication_lexical": publication.get("lexical") or "",
                "publication_normalised": publication.get("normalised") or "",
                "time_key": "publication",
            }
        ],
        "candidates": normalised["candidates"],
    }
    engine = EnrichmentEngine()
    preliminary = engine.run(copy.deepcopy(envelope))
    notes = attach_accepted_markets(normalised["candidates"], preliminary["decisions"])
    recorded = engine.run(envelope)
    return recorded, notes, emit_profile


def process_document(bundle: dict, root: Path, *, validate_shacl: bool = True) -> dict:
    """Run one document. Failures are returned; they are not repaired by rule edits."""
    document_id = bundle["document_id"]
    record_errors = _validate_records(bundle)
    if record_errors:
        raise RuntimeError("Source records failed schema validation: " + "; ".join(record_errors[:6]))
    normalised = normalise(bundle, CORPUS)
    valid, schema_errors = _validate_candidates(normalised["candidates"])
    if schema_errors:
        normalised["candidates"] = valid
    recorded, attach_notes, emit_profile = _run_rules(bundle, normalised)
    decision_errors = _validate_decisions(recorded["decisions"])
    graphs = materialise(recorded, emit_profile)
    graphs["accepted"] = expand_canonical_mentions(
        graphs["accepted"], normalised["candidates"], recorded["decisions"], bundle, CORPUS
    )
    extension = emit_profile(recorded, "EXTENSION_REVIEWED")
    candidate_review = emit_profile(recorded, "CANDIDATE_REVIEW")
    experimental = emit_profile(recorded, "EXPERIMENTAL_TEMPORAL")
    graphs["extension"] = extension if extension.strip() else EMPTY_EXTENSION
    graphs["candidate_review"] = candidate_review if candidate_review.strip() else EMPTY_CANDIDATE
    graphs["experimental"] = experimental if experimental.strip() else EMPTY_EXPERIMENTAL
    # Candidate-review and experimental output must not add a positive direct
    # triple for a decision that was not accepted.
    graphs["candidate_review"] = _drop_unaccepted_direct(graphs["candidate_review"], recorded, "CANDIDATE_REVIEW")
    graphs["experimental"] = _drop_unaccepted_direct(graphs["experimental"], recorded, "EXPERIMENTAL_TEMPORAL")
    for key in list(graphs):
        if isinstance(graphs[key], str):
            graphs[key] = _repair_turtle_literals(graphs[key])
    _write_candidates(root, document_id, normalised, attach_notes, schema_errors)
    _write_decisions(root, document_id, bundle, normalised, recorded)
    _write_rdf(root, document_id, graphs)
    policy = _policy(recorded, graphs)
    shacl = {"conforms": None, "violation_count": None, "warning_count": None, "info_count": None, "violations": [], "engine": ""}
    if validate_shacl:
        ontology = REPO / "research/financial_event_ontology/ontology/feo007a/ontology/fneo-0.1.0-rc2.ttl"
        core = REPO / "research/financial_event_ontology/ontology/feo007a/validation/fneo-core-shapes.ttl"
        supplemental = REPO / "research/financial_event_ontology/ontology/feo007a/validation/supplemental-shapes.ttl"
        shacl = validate_accepted(graphs["accepted"], ontology, core, supplemental)
        dump_json(root / "validation" / "per_document" / f"{document_id}.json", shacl)
    _engine_names = _engine()
    resource_iri, safe_local_key = _engine_names[3], _engine_names[4]
    mention = _mention_row(bundle, normalised, normalised["candidates"], resource_iri, safe_local_key)
    dump_json(root / "decisions" / "per_document" / document_id / "mention_iris.json", mention.get("iris") or [])
    groups = normalised.get("participant_groups") or []
    participant = _participant_row(document_id, groups)
    statuses = Counter(item["status"] for item in recorded["decisions"])
    profiles = {name: len(items) for name, items in recorded["by_profile"].items()}
    warning_count = len(normalised.get("warnings") or []) + len(attach_notes) + sum(len(item.get("warnings") or []) for item in recorded["decisions"])
    error_count = len(schema_errors) + len(decision_errors)
    status = "completed"
    if error_count:
        status = "partial"
    elif warning_count or bundle.get("warnings"):
        status = "completed_with_warnings"
    source_records = sum(len(bundle[group]) for group in (
        "documents", "sentences", "tokens", "mentions", "canonical_entities", "canonical_events",
        "participants", "times", "temporal_relations", "values", "evidence",
    ))
    summary = {
        "document_id": document_id,
        "status": status,
        "source_records": source_records,
        "candidates": len(normalised["candidates"]),
        "decisions": len(recorded["decisions"]),
        "accepted": statuses.get("accepted", 0),
        "review_required": statuses.get("requires_review", 0),
        "rejected": statuses.get("rejected", 0),
        "out_of_scope": statuses.get("out_of_scope", 0),
        "insufficient_evidence": statuses.get("insufficient_evidence", 0),
        "suppressed": statuses.get("suppressed", 0),
        "warnings": warning_count + len(bundle.get("warnings") or []),
        "errors": error_count,
        "profiles": profiles,
        "policy": policy,
        "shacl": {
            "conforms": shacl.get("conforms"),
            "violation_count": shacl.get("violation_count"),
            "warning_count": shacl.get("warning_count"),
            "info_count": shacl.get("info_count"),
            "engine": shacl.get("engine"),
            "violations": shacl.get("violations") or [],
        },
        "mention": {key: value for key, value in mention.items() if key != "iris"},
        "participant": participant,
        "adapter_version": ADAPTER_VERSION,
        "mapping_version": MAPPING_VERSION,
        "notes": "",
    }
    if schema_errors:
        summary["notes"] = f"{len(schema_errors)} candidates failed schema validation and were excluded from the engine."
    stored = {key: value for key, value in summary.items() if key not in {"shacl", "policy"}}
    stored["mention"] = {key: value for key, value in mention.items() if key != "iris"}
    dump_json(root / "decisions" / "per_document" / document_id / "process_summary.json", stored)
    return summary


def _drop_unaccepted_direct(turtle: str, recorded: dict, profile: str) -> str:
    if not turtle.strip() or turtle.lstrip().startswith("#"):
        return turtle
    accepted_pairs = set()
    for decision in recorded["decisions"]:
        if decision.get("profile") != profile or decision.get("status") != "accepted":
            continue
        if not decision.get("direct_triple_eligible"):
            continue
        accepted_pairs.add(
            (
                decision.get("subject_iri") or "",
                decision.get("predicate_iri") or "",
                decision.get("object_iri") or decision.get("object_lexical") or "",
            )
        )
    graph = _parse(turtle)
    kept = Graph()
    for subject, predicate, obj in graph:
        local = local_name(str(predicate))
        if local in {
            "hasAffectedMarket",
            "hasEventTime",
            "hasMarketDirection",
            "hasReportedValue",
            "hasParticipant",
            "precedes",
            "follows",
            "simultaneousWith",
            "occursDuring",
            "includes",
        } and "/assertion/" not in str(subject):
            if (str(subject), str(predicate), str(obj)) not in accepted_pairs:
                continue
        kept.add((subject, predicate, obj))
    if len(kept) == 0:
        return EMPTY_EXPERIMENTAL if profile == "EXPERIMENTAL_TEMPORAL" else EMPTY_CANDIDATE
    return deterministic_turtle(kept)


def _write_candidates(root: Path, document_id: str, normalised: dict, attach_notes: list[str], schema_errors: list[dict]) -> None:
    destination = root / "candidates" / "per_document" / document_id
    by_kind = {
        "entity_candidates.json": "entity_candidate",
        "event_candidates.json": "event_candidate",
        "participation_candidates.json": "participation_candidate",
        "temporal_candidates.json": "temporal_candidate",
        "value_candidates.json": "value_candidate",
        "evidence_candidates.json": "evidence_candidate",
    }
    for name, kind in by_kind.items():
        dump_json(destination / name, [item for item in normalised["candidates"] if item["candidate_kind"] == kind])
    dump_json(destination / "candidates.json", normalised["candidates"])
    dump_json(destination / "normalisation_warnings.json", list(normalised.get("warnings") or []) + list(attach_notes))
    dump_json(destination / "schema_errors.json", schema_errors)


def _write_decisions(root: Path, document_id: str, bundle: dict, normalised: dict, recorded: dict) -> None:
    destination = root / "decisions" / "per_document" / document_id
    dump_json(destination / "decisions.json", recorded["decisions"])
    groups = normalised.get("participant_groups") or []
    slim = []
    for group in groups:
        row = {column: group.get(column, "") for column in UNRESOLVED_COLUMNS}
        row["operational_path_count"] = group.get("operational_path_count") or 0
        row["emit"] = bool(group.get("emit"))
        row["classification"] = group.get("classification") or ""
        slim.append(row)
    dump_json(destination / "participant_groups.json", slim)
    dump_json(destination / "unresolved_participants.json", unresolved_participant_rows(groups))
    dump_json(destination / "time_anchors.json", classify_time_anchors(bundle))
    dump_json(
        destination / "summary.json",
        {
            "document_id": document_id,
            "candidate_count": len(recorded.get("candidates") or normalised["candidates"]),
            "decision_count": len(recorded["decisions"]),
            "by_status": dict(Counter(item["status"] for item in recorded["decisions"])),
            "by_profile": {profile: len(items) for profile, items in recorded["by_profile"].items()},
            "adapter_version": ADAPTER_VERSION,
            "mapping_version": MAPPING_VERSION,
        },
    )


def _write_rdf(root: Path, document_id: str, graphs: dict) -> None:
    paths = {
        "accepted": root / "rdf" / "accepted" / "per_document" / f"{document_id}-core.ttl",
        "review": root / "rdf" / "review-required" / "per_document" / f"{document_id}-review.ttl",
        "extension": root / "rdf" / "review-required" / "per_document" / f"{document_id}-extension.ttl",
        "candidate_review": root / "rdf" / "review-required" / "per_document" / f"{document_id}-candidate-review.ttl",
        "rejected": root / "rdf" / "rejected" / "per_document" / f"{document_id}-rejected.ttl",
        "experimental": root / "rdf" / "experimental" / "per_document" / f"{document_id}-experimental.ttl",
    }
    for key, path in paths.items():
        _write_text(path, graphs[key])


def failure_summary(document_id: str, message: str) -> dict:
    return {
        "document_id": document_id,
        "status": "failed",
        "source_records": 0,
        "candidates": 0,
        "decisions": 0,
        "accepted": 0,
        "review_required": 0,
        "rejected": 0,
        "out_of_scope": 0,
        "insufficient_evidence": 0,
        "suppressed": 0,
        "warnings": 0,
        "errors": 1,
        "profiles": {},
        "policy": {
            "review_direct": 0,
            "rejected_direct": 0,
            "same_as": 0,
            "missing_direct": 0,
            "missing_qualified": 0,
            "missing_evidence": 0,
            "noncore_in_core": 0,
            "examples": {},
        },
        "shacl": {"conforms": None, "violation_count": None, "warning_count": None, "info_count": None, "engine": "", "violations": []},
        "mention": {
            "document_id": document_id,
            "source_mention_records": 0,
            "public_mention_iris": 0,
            "coextensive_source_records": 0,
            "candidate_reuse_count": 0,
            "collisions": 0,
            "duplicate_iris": 0,
            "cross_document_collision": 0,
            "status": "failed",
            "notes": excerpt(message, 300),
        },
        "participant": {"document_id": document_id, "raw_operational_paths": 0, "normalised_groups": 0},
        "notes": excerpt(message, 500),
    }


def safe_message(exc: BaseException) -> str:
    return scrub(f"{type(exc).__name__}: {exc}")
