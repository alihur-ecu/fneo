"""Add one public mention resource per textual mention of an accepted individual.

The enrichment emitter writes the representative mention. Further textual
mentions of the same canonical individual are added here with the same
identity function, so candidates that share a textual mention share its IRI.
"""

from __future__ import annotations

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, XSD

from adapter.identity import MENTION_TYPES
from adapter.materialisation.materialise import deterministic_turtle
from adapter.normalisation.normalise import ensure_engine_path

FNEO = "https://w3id.org/fneo/"


def _kind(candidate: dict) -> str:
    features = candidate.get("features") or {}
    kind = candidate.get("candidate_kind")
    if kind == "entity_candidate":
        return "entity"
    if kind == "event_candidate":
        return "event"
    if kind == "value_candidate":
        return "value"
    if kind == "temporal_candidate" and features.get("time_mention"):
        return "time"
    return ""


def expand_canonical_mentions(turtle: str, candidates: list[dict], decisions: list[dict], bundle: dict, corpus: str) -> str:
    ensure_engine_path()
    from engine.identifiers import resource_iri, safe_local_key

    graph = Graph()
    if turtle and turtle.strip() and not turtle.lstrip().startswith("#"):
        graph.parse(data=turtle, format="turtle")
    by_id = {item["candidate_id"]: item for item in candidates}
    mentions = {item["source_identifier"]: item for item in bundle["mentions"]}
    document_id = bundle["document_id"]
    document = URIRef(resource_iri("document", corpus, document_id))
    integer = XSD.nonNegativeInteger
    for decision in decisions:
        if decision.get("status") != "accepted" or not decision.get("direct_triple_eligible"):
            continue
        candidate = by_id.get(decision.get("candidate_id"))
        if candidate is None:
            continue
        kind = _kind(candidate)
        subject = decision.get("subject_iri") or ""
        if not kind or not subject or decision.get("subject_kind") not in {"entity", "event", "time", "value"}:
            continue
        subject_ref = URIRef(subject)
        if not any(graph.triples((subject_ref, RDF.type, None))):
            continue
        for mention_id in candidate.get("source_mention_ids") or []:
            mention = mentions.get(mention_id)
            if mention is None:
                continue
            local = (candidate.get("features") or {}).get("mention_identity_by_source", {}).get(mention_id)
            if not local:
                local = (candidate.get("features") or {}).get("mention_key") if mention_id == (candidate.get("source_mention_ids") or [None])[0] else ""
            if not local:
                continue
            iri = URIRef(resource_iri("mention", kind, corpus, document_id, safe_local_key(str(local), purpose="mention")))
            graph.add((iri, RDF.type, URIRef(FNEO + MENTION_TYPES[kind])))
            graph.add((iri, URIRef(FNEO + "denotes"), subject_ref))
            graph.add((iri, URIRef(FNEO + "mentionedIn"), document))
            form = mention.get("textual_form") or ""
            if form:
                graph.add((iri, URIRef(FNEO + "textualForm"), Literal(str(form), datatype=XSD.string)))
            if mention.get("token_start") is not None and mention.get("token_end") is not None:
                graph.add((iri, URIRef(FNEO + "tokenStart"), Literal(int(mention["token_start"]), datatype=integer)))
                graph.add((iri, URIRef(FNEO + "tokenEnd"), Literal(int(mention["token_end"]), datatype=integer)))
            if mention.get("character_start") is not None and mention.get("character_end") is not None:
                graph.add((iri, URIRef(FNEO + "characterStart"), Literal(int(mention["character_start"]), datatype=integer)))
                graph.add((iri, URIRef(FNEO + "characterEnd"), Literal(int(mention["character_end"]), datatype=integer)))
            graph.add((subject_ref, URIRef(FNEO + "hasMention"), iri))
    if len(graph) == 0:
        return turtle
    return deterministic_turtle(graph)
