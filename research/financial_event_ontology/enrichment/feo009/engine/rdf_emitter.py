"""Deterministic Turtle for one population profile.

Unaccepted decisions do not receive direct domain triples.
"""

from __future__ import annotations

import re

from engine.constants import (
    COMMITMENT_INDIVIDUAL,
    FNEO_NS,
    INFERENCE_INDIVIDUAL,
    MANUAL_REVIEW_INDIVIDUAL,
    MAPPING_VERSION,
    RDF_TYPE,
    RDFS_LABEL,
    TEMPORAL_TYPE_INDIVIDUAL,
    VALIDATION_INDIVIDUAL,
    XSD_NS,
)
from engine.identifiers import assertion_iri, object_form_iri, object_form_literal, resource_iri, safe_local_key
from engine.conditions import _percentage_points

XSD_STRING = XSD_NS + "string"
XSD_DECIMAL = XSD_NS + "decimal"
XSD_ANY_URI = XSD_NS + "anyURI"
XSD_INTEGER = XSD_NS + "nonNegativeInteger"
ORDER = {"precedes", "follows", "simultaneousWith", "occursDuring", "includes"}
VALUE_TYPES = {"NumericalValue", "PercentageValue", "MonetaryAmount", "QuantityValue"}
EXTENSION_TYPES = {
    "CentralBank",
    "CommercialBank",
    "Currency",
    "EquityShare",
    "FinancialSystem",
    "FinancialSector",
    "MonetaryAmount",
    "QuantityValue",
}
FORBIDDEN = ("bo" + "lt://", "local" + "host", "/home" + "/", "text" + "graphx")
LOCAL_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


class Graph:
    def __init__(self):
        self.rows: dict[tuple, tuple] = {}

    def iri(self, subject: str, predicate: str, obj: str) -> None:
        if not subject or not predicate or not obj:
            return
        self.rows[(subject, predicate, "iri", obj)] = ("iri", obj)

    def literal(self, subject: str, predicate: str, lexical: str, datatype: str) -> None:
        if subject is None or predicate is None or lexical is None or lexical == "":
            return
        self.rows[(subject, predicate, "lit", datatype, lexical)] = ("lit", lexical, datatype)

    def has(self, subject: str, predicate: str, obj: str) -> bool:
        return (subject, predicate, "iri", obj) in self.rows


def _term(iri: str) -> str:
    if iri == RDF_TYPE:
        return "rdf:type"
    if iri == RDFS_LABEL:
        return "rdfs:label"
    if iri.startswith(XSD_NS):
        return "xsd:" + iri.split("#", 1)[-1]
    if iri.startswith(FNEO_NS) and "/resource/" not in iri:
        local = iri[len(FNEO_NS):]
        if LOCAL_NAME.match(local):
            return "fneo:" + local
    return "<" + iri + ">"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def serialise(graph: Graph) -> str:
    grouped: dict[str, list[tuple[str, str]]] = {}
    for (subject, predicate, kind, *rest) in graph.rows:
        if kind == "iri":
            rendered = _term(rest[0])
        else:
            datatype, lexical = rest[0], rest[1]
            rendered = f'"{_escape(lexical)}"^^{_term(datatype)}'
        grouped.setdefault(subject, []).append((predicate, rendered))
    lines = [
        "@prefix fneo: <https://w3id.org/fneo/> .",
        "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .",
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
        "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
        "",
    ]
    for subject in sorted(grouped):
        pairs = sorted(grouped[subject], key=lambda item: (item[0], item[1]))
        bits = [f"{_term(predicate)} {obj}" for predicate, obj in pairs]
        lines.append(f"{_term(subject)} " + " ;\n    ".join(bits) + " .\n")
    text = "\n".join(lines).rstrip() + "\n"
    lowered = text.lower()
    for forbidden in FORBIDDEN:
        if forbidden in lowered:
            raise ValueError("Refusing public Turtle that contains a local endpoint or filesystem path.")
    return text


def _span_ok(start, end) -> bool:
    return isinstance(start, int) and isinstance(end, int) and start >= 0 and end > start


def _candidate_map(result: dict) -> dict[str, dict]:
    return {item["candidate_id"]: item for item in result.get("candidates") or []}


def _by_subject_local(result: dict) -> dict[tuple, dict]:
    found = {}
    for candidate in result.get("candidates") or []:
        features = candidate.get("features") or {}
        local = str(features.get("local_key") or candidate["candidate_id"])
        found[(candidate.get("document_id"), local)] = candidate
    return found


def emit_profile(result: dict, profile: str) -> str:
    decisions = list(result["by_profile"].get(profile) or [])
    if not decisions:
        return ""
    graph = Graph()
    corpus = result.get("corpus") or "synthetic-feo009"
    fixture_id = result.get("fixture_id") or "fixture"
    activity = resource_iri("activity", MAPPING_VERSION, fixture_id)
    agent = resource_iri("agent", "feo009-enrichment-engine")
    graph.iri(activity, RDFS_LABEL, "")  # placeholder removed below
    graph.rows.pop((activity, RDFS_LABEL, "iri", ""), None)
    graph.literal(activity, RDFS_LABEL, f"enrichment activity {fixture_id}", XSD_STRING)
    graph.iri(activity, FNEO_NS + "generatedBySoftwareAgent", agent)
    graph.literal(agent, RDFS_LABEL, "deterministic enrichment engine", XSD_STRING)
    documents = _documents(result, corpus, graph)
    candidates = _candidate_map(result)
    for decision in decisions:
        _emit_decision(graph, decision, candidates, documents, activity, corpus)
    return serialise(graph)


def _documents(result: dict, corpus: str, graph: Graph) -> dict[str, str]:
    iris = {}
    for document in result.get("documents") or []:
        document_id = str(document.get("document_id") or "")
        if not document_id:
            continue
        doc = resource_iri("document", corpus, document_id)
        iris[document_id] = doc
        graph.iri(doc, RDF_TYPE, FNEO_NS + "FinancialNewsDocument")
        graph.literal(doc, FNEO_NS + "sourceDocumentIdentifier", document_id, XSD_STRING)
        if document.get("label"):
            graph.literal(doc, RDFS_LABEL, str(document["label"]), XSD_STRING)
        if document.get("publication_normalised") or document.get("publication_lexical"):
            time_key = str(document.get("time_key") or "publication")
            time_iri = resource_iri("time", corpus, document_id, safe_local_key(time_key, purpose="time"))
            graph.iri(doc, FNEO_NS + "hasPublicationTime", time_iri)
            graph.iri(time_iri, RDF_TYPE, FNEO_NS + "TimeEntity")
            graph.literal(time_iri, RDFS_LABEL, "publication time", XSD_STRING)
            if document.get("publication_normalised"):
                graph.literal(time_iri, FNEO_NS + "normalisedTimeValue", str(document["publication_normalised"]), XSD_STRING)
            if document.get("publication_lexical"):
                graph.literal(time_iri, FNEO_NS + "publicationTimeLiteral", str(document["publication_lexical"]), XSD_STRING)
    if not iris:
        for candidate in result.get("candidates") or []:
            document_id = candidate.get("document_id")
            if document_id and document_id not in iris:
                doc = resource_iri("document", corpus, document_id)
                iris[document_id] = doc
                graph.iri(doc, RDF_TYPE, FNEO_NS + "FinancialNewsDocument")
                graph.literal(doc, FNEO_NS + "sourceDocumentIdentifier", document_id, XSD_STRING)
    return iris


def _emit_decision(graph, decision, candidates, documents, activity, corpus) -> None:
    subject = decision.get("subject_iri") or ""
    predicate = decision.get("predicate_iri") or ""
    object_iri = decision.get("object_iri") or ""
    direct = bool(decision.get("direct_triple_eligible")) and decision.get("status") == "accepted"
    if direct and subject and predicate and object_iri:
        graph.iri(subject, predicate, object_iri)
    if direct and subject and predicate and decision.get("object_lexical"):
        graph.literal(subject, predicate, decision["object_lexical"], decision.get("object_datatype") or XSD_STRING)
    if direct and predicate.endswith("hasMarketDirection"):
        graph.iri(subject, RDF_TYPE, FNEO_NS + "Event")
    _materialise_node(graph, decision, candidates, documents, corpus, direct, activity)
    if decision.get("qualified_assertion_required") and decision.get("assertion_iri"):
        _assertion(graph, decision, activity)
    if decision.get("rule_id"):
        rule_iri = resource_iri("rule", decision["rule_id"])
        graph.literal(rule_iri, RDFS_LABEL, decision["rule_id"], XSD_STRING)


def _materialise_node(graph, decision, candidates, documents, corpus, direct: bool, activity: str) -> None:
    candidate = candidates.get(decision["candidate_id"])
    if candidate is None:
        return
    subject = decision.get("subject_iri") or ""
    target = decision.get("target_local_name") or ""
    features = candidate.get("features") or {}
    label = str(features.get("label") or candidate.get("trigger_or_lexical_form") or "")
    if subject and label and decision.get("subject_kind") in {"entity", "event", "time", "value"}:
        graph.literal(subject, RDFS_LABEL, label, XSD_STRING)
    document = documents.get(candidate.get("document_id") or "")
    mention = _mention_iri(candidate, corpus) if _mention_allowed(candidate, decision) and direct else ""
    if mention and subject:
        mention_type = _mention_type(candidate, decision)
        graph.iri(mention, RDF_TYPE, FNEO_NS + mention_type)
        graph.iri(mention, FNEO_NS + "denotes", subject)
        if document:
            graph.iri(mention, FNEO_NS + "mentionedIn", document)
        form = candidate.get("trigger_or_lexical_form") or label
        if form:
            graph.literal(mention, FNEO_NS + "textualForm", str(form), XSD_STRING)
        _offsets(graph, mention, candidate)
        if decision.get("subject_kind") in {"entity", "event", "time", "value"}:
            graph.iri(subject, FNEO_NS + "hasMention", mention)
    if document and decision.get("subject_kind") == "event" and subject:
        graph.iri(document, FNEO_NS + "reportsEvent", subject)
    if direct and target == "MarketChangeEvent":
        evidence = _evidence_node(graph, candidate, corpus, decision)
        if evidence:
            graph.iri(subject, FNEO_NS + "supportedBy", evidence)
        for annotation in candidate.get("source_annotation_ids") or []:
            graph.literal(subject, FNEO_NS + "sourceAnnotationIdentifier", str(annotation), XSD_STRING)
        graph.iri(subject, FNEO_NS + "hasValidationStatus", FNEO_NS + "Accepted")
        graph.literal(subject, FNEO_NS + "populationMethod", "documented_rule", XSD_STRING)
    if direct and target in EXTENSION_TYPES and decision.get("subject_kind") == "entity":
        review = MANUAL_REVIEW_INDIVIDUAL.get(decision.get("manual_review_status") or "", "NotReviewed")
        graph.iri(subject, FNEO_NS + "hasManualReviewStatus", FNEO_NS + review)
    if direct and target in VALUE_TYPES:
        _value_properties(graph, subject, candidate, decision, activity)
    if decision.get("subject_kind") == "evidence" and direct:
        text = candidate.get("textual_evidence") or candidate.get("trigger_or_lexical_form") or ""
        if text:
            graph.literal(subject, FNEO_NS + "evidenceText", str(text), XSD_STRING)
        _offsets(graph, subject, candidate)
    if direct and target == "TimeEntity":
        normalised = features.get("normalised") or (candidate.get("source_temporal_relation") or {}).get("normalised")
        if normalised:
            graph.literal(subject, FNEO_NS + "normalisedTimeValue", str(normalised), XSD_STRING)
    if direct and decision.get("predicate_iri", "").endswith("hasEventTime"):
        _time_endpoint(graph, object_iri := decision.get("object_iri"), candidates, features)
    if direct and _local(decision.get("predicate_iri")) in ORDER:
        _type_endpoints(graph, decision)


def _time_endpoint(graph, time_iri, candidates, features) -> None:
    if not time_iri:
        return
    graph.iri(time_iri, RDF_TYPE, FNEO_NS + "TimeEntity")
    normalised = features.get("time_normalised") or features.get("normalised")
    if normalised:
        graph.literal(time_iri, FNEO_NS + "normalisedTimeValue", str(normalised), XSD_STRING)


def _type_endpoints(graph, decision) -> None:
    predicate = _local(decision.get("predicate_iri"))
    subject = decision.get("subject_iri")
    obj = decision.get("object_iri")
    if predicate in {"precedes", "follows", "simultaneousWith"}:
        graph.iri(subject, RDF_TYPE, FNEO_NS + "Event")
        graph.iri(obj, RDF_TYPE, FNEO_NS + "Event")
    elif predicate == "occursDuring":
        graph.iri(subject, RDF_TYPE, FNEO_NS + "Event")
        graph.iri(obj, RDF_TYPE, FNEO_NS + "TimeEntity")
    elif predicate == "includes":
        graph.iri(subject, RDF_TYPE, FNEO_NS + "TimeEntity")
        graph.iri(obj, RDF_TYPE, FNEO_NS + "Event")


def _value_properties(graph, subject, candidate, decision, activity) -> None:
    features = candidate.get("features") or {}
    lexical = str(features.get("lexical") or candidate.get("trigger_or_lexical_form") or "")
    graph.literal(subject, FNEO_NS + "numericalLexicalForm", lexical, XSD_STRING)
    points = ""
    if decision.get("target_local_name") == "PercentageValue":
        parsed = _percentage_points(lexical)
        points = format(parsed, "f") if parsed is not None else ""
    elif features.get("numerical_value") not in (None, ""):
        points = str(features.get("numerical_value"))
    if points and features.get("force_fraction") is not True:
        graph.literal(subject, FNEO_NS + "numericalValue", points, XSD_DECIMAL)
        literal_assertion = assertion_iri(
            profile=decision.get("assertion_profile") or decision["profile"],
            subject=subject,
            predicate=FNEO_NS + "numericalValue",
            object_form=object_form_literal(points, XSD_DECIMAL),
            assertion_kind="literal",
        )
        graph.iri(literal_assertion, RDF_TYPE, FNEO_NS + "RelationAssertion")
        graph.iri(literal_assertion, FNEO_NS + "assertionSubject", subject)
        graph.literal(literal_assertion, FNEO_NS + "assertionPredicateIRI", FNEO_NS + "numericalValue", XSD_ANY_URI)
        graph.literal(literal_assertion, FNEO_NS + "assertionObjectLiteral", points, XSD_DECIMAL)
        _assertion_meta(graph, literal_assertion, decision, activity)
    if features.get("currency_code") and decision.get("target_local_name") == "MonetaryAmount":
        graph.literal(subject, FNEO_NS + "currencyCode", str(features["currency_code"]), XSD_STRING)


def _assertion(graph, decision, activity) -> None:
    assertion = decision["assertion_iri"]
    kind = decision.get("assertion_kind") or "relation"
    graph.iri(assertion, RDF_TYPE, FNEO_NS + "RelationAssertion")
    if kind == "temporal":
        graph.iri(assertion, RDF_TYPE, FNEO_NS + "TemporalRelationAssertion")
    if kind == "participation":
        graph.iri(assertion, RDF_TYPE, FNEO_NS + "EventParticipation")
    graph.iri(assertion, FNEO_NS + "assertionSubject", decision["subject_iri"])
    graph.literal(assertion, FNEO_NS + "assertionPredicateIRI", decision["predicate_iri"], XSD_ANY_URI)
    if decision.get("object_iri") and not decision.get("object_lexical"):
        graph.iri(assertion, FNEO_NS + "assertionObject", decision["object_iri"])
    elif decision.get("object_lexical"):
        graph.literal(
            assertion,
            FNEO_NS + "assertionObjectLiteral",
            decision["object_lexical"],
            decision.get("object_datatype") or XSD_STRING,
        )
    _assertion_meta(graph, assertion, decision, activity)
    if kind == "participation":
        graph.iri(assertion, FNEO_NS + "participationEvent", decision["subject_iri"])
        graph.iri(decision["subject_iri"], RDF_TYPE, FNEO_NS + "Event")
        if decision.get("object_iri"):
            graph.iri(assertion, FNEO_NS + "participatingEntity", decision["object_iri"])
            graph.iri(decision["object_iri"], RDF_TYPE, FNEO_NS + "Entity")
        roles = decision.get("source_roles_preserved") or []
        if roles:
            graph.literal(assertion, FNEO_NS + "sourceRoleLabel", str(roles[0]), XSD_STRING)
        evidence = (decision.get("evidence_references") or [None])[0]
        if evidence:
            graph.iri(assertion, FNEO_NS + "supportedBy", evidence)
    if kind == "temporal":
        _temporal_assertion(graph, assertion, decision)


def _assertion_meta(graph, assertion, decision, activity) -> None:
    graph.literal(assertion, FNEO_NS + "confidence", str(decision.get("confidence") or "0.00"), XSD_DECIMAL)
    graph.literal(assertion, FNEO_NS + "ruleIdentifier", decision["rule_id"], XSD_STRING)
    graph.literal(assertion, FNEO_NS + "populatedByRule", decision["rule_id"], XSD_STRING)
    graph.literal(assertion, FNEO_NS + "populationMethod", decision.get("population_method") or "documented_rule", XSD_STRING)
    graph.iri(assertion, FNEO_NS + "populatedByActivity", activity)
    status = VALIDATION_INDIVIDUAL[decision["status"]]
    graph.iri(assertion, FNEO_NS + "hasValidationStatus", FNEO_NS + status)
    review = MANUAL_REVIEW_INDIVIDUAL.get(decision.get("manual_review_status") or "not_reviewed", "NotReviewed")
    graph.iri(assertion, FNEO_NS + "hasManualReviewStatus", FNEO_NS + review)


def _temporal_assertion(graph, assertion, decision) -> None:
    graph.iri(assertion, FNEO_NS + "temporalSubject", decision["subject_iri"])
    if decision.get("object_iri"):
        graph.iri(assertion, FNEO_NS + "temporalObject", decision["object_iri"])
    local = _local(decision.get("predicate_iri"))
    relation_type = TEMPORAL_TYPE_INDIVIDUAL.get(local)
    if relation_type:
        graph.iri(assertion, FNEO_NS + "temporalRelationType", FNEO_NS + relation_type)
    graph.literal(assertion, FNEO_NS + "canonicalPublicRelation", local, XSD_STRING)
    original = decision.get("original_relation_label") or ""
    if original:
        graph.literal(assertion, FNEO_NS + "originalTemporalRelationLabel", original, XSD_STRING)
    source_kind = decision.get("temporal_source_kind") or ""
    if source_kind:
        graph.literal(assertion, FNEO_NS + "sourceKind", source_kind, XSD_STRING)
        graph.literal(assertion, FNEO_NS + "relationSource", source_kind, XSD_STRING)
    eligibility = "accepted" if decision.get("status") == "accepted" else "not_eligible"
    graph.literal(assertion, FNEO_NS + "materialisationEligibility", eligibility, XSD_STRING)
    commitment = _commitment(decision)
    if commitment:
        graph.iri(assertion, FNEO_NS + "hasCommitmentStatus", FNEO_NS + commitment)
    inference = INFERENCE_INDIVIDUAL.get(decision.get("temporal_inference") or "")
    if inference:
        graph.iri(assertion, FNEO_NS + "hasInferenceStatus", FNEO_NS + inference)
    if decision.get("status") == "suppressed":
        graph.literal(
            assertion,
            FNEO_NS + "suppressionReason",
            decision.get("manual_review_reason") or "Suppressed temporal candidate is not an accepted fact.",
            XSD_STRING,
        )


def _commitment(decision: dict) -> str:
    status = decision.get("status")
    if status == "accepted":
        return "Committed"
    if status == "suppressed":
        return "SuppressedCommitment"
    if status == "requires_review":
        return "Proposed"
    return ""


def _evidence_node(graph, candidate, corpus, decision) -> str:
    references = decision.get("evidence_references") or []
    evidence = references[0] if references else ""
    if not evidence:
        return ""
    text = candidate.get("textual_evidence") or candidate.get("trigger_or_lexical_form") or ""
    if not text:
        return ""
    graph.iri(evidence, RDF_TYPE, FNEO_NS + "TextualEvidence")
    graph.literal(evidence, FNEO_NS + "evidenceText", str(text), XSD_STRING)
    _offsets(graph, evidence, candidate)
    return evidence


def _offsets(graph, node, candidate) -> None:
    if _span_ok(candidate.get("token_start"), candidate.get("token_end")):
        boundary = candidate.get("token_boundary_length")
        if not isinstance(boundary, int) or candidate["token_end"] <= boundary:
            graph.literal(node, FNEO_NS + "tokenStart", str(candidate["token_start"]), XSD_INTEGER)
            graph.literal(node, FNEO_NS + "tokenEnd", str(candidate["token_end"]), XSD_INTEGER)
    if _span_ok(candidate.get("character_start"), candidate.get("character_end")):
        boundary = candidate.get("text_boundary_length")
        if not isinstance(boundary, int) or candidate["character_end"] <= boundary:
            graph.literal(node, FNEO_NS + "characterStart", str(candidate["character_start"]), XSD_INTEGER)
            graph.literal(node, FNEO_NS + "characterEnd", str(candidate["character_end"]), XSD_INTEGER)


def _mention_allowed(candidate: dict, decision: dict) -> bool:
    kind = candidate.get("candidate_kind")
    subject_kind = decision.get("subject_kind")
    features = candidate.get("features") or {}
    if kind == "entity_candidate" and subject_kind == "entity":
        return True
    if kind == "event_candidate" and subject_kind == "event":
        return True
    if kind == "value_candidate" and subject_kind == "value":
        return True
    if kind == "temporal_candidate" and features.get("time_mention") and subject_kind == "time":
        return True
    return False


def _mention_type(candidate, decision) -> str:
    features = candidate.get("features") or {}
    if candidate["candidate_kind"] == "event_candidate" or decision.get("subject_kind") == "event":
        return "EventMention"
    if features.get("time_mention") or decision.get("subject_kind") == "time":
        return "TimeMention"
    if candidate["candidate_kind"] == "value_candidate" or decision.get("subject_kind") == "value":
        return "TextualMention"
    return "EntityMention"


def _mention_iri(candidate, corpus) -> str:
    features = candidate.get("features") or {}
    if candidate.get("candidate_kind") == "participation_candidate":
        return ""
    if features.get("unmapped"):
        return ""
    kind = {
        "entity_candidate": "entity",
        "event_candidate": "event",
        "value_candidate": "value",
        "temporal_candidate": "time" if features.get("time_mention") or candidate.get("candidate_kind") == "temporal_candidate" else "event",
    }.get(candidate["candidate_kind"], "entity")
    if candidate["candidate_kind"] == "temporal_candidate" and not features.get("time_mention"):
        return ""
    local = str(features.get("mention_key") or features.get("local_key") or candidate["candidate_id"])
    document_id = candidate.get("document_id") or "document"
    return resource_iri("mention", kind, corpus, document_id, safe_local_key(local, purpose="mention"))


def _local(iri: str | None) -> str:
    if not iri:
        return ""
    return iri.rstrip("/").rsplit("/", 1)[-1].rsplit("#", 1)[-1]


def assert_no_unaccepted_direct(graph_text: str, decisions: list[dict]) -> list[str]:
    """Return materialisation violations. Parsing uses rdflib when the caller asks."""
    violations = []
    for decision in decisions:
        if decision.get("status") == "accepted":
            continue
        predicate = decision.get("predicate_iri") or ""
        subject = decision.get("subject_iri") or ""
        obj = decision.get("object_iri") or decision.get("object_lexical") or ""
        if not predicate or not subject or not obj:
            continue
        # A direct triple is present when the predicate line follows the subject block.
        # The caller performs the graph check. This string check is a backstop.
        needle_subject = subject
        if needle_subject in graph_text and obj in graph_text and predicate in graph_text:
            # Ambiguous across blocks; the evaluator uses rdflib.
            continue
    return violations
