"""Materialise FEO-009 decisions into separate RDF graphs.

The enrichment emitter is called unchanged. Review, rejected, and
experimental graphs do not receive direct domain triples.
"""

from __future__ import annotations

from rdflib import Graph, URIRef

from adapter.common import contains_forbidden

CORE = "CORE_DETERMINISTIC"
EMPTY_PROFILES = ("EXTENSION_REVIEWED", "CANDIDATE_REVIEW", "EXPERIMENTAL_TEMPORAL")
DOMAIN_PREDICATES = {
    "hasAffectedMarket",
    "hasEventTime",
    "hasMarketDirection",
    "hasParticipant",
    "hasReportedValue",
    "hasPercentageChange",
    "hasMonetaryAmount",
    "precedes",
    "follows",
    "simultaneousWith",
    "occursDuring",
    "includes",
}


def _empty_profiles() -> dict:
    return {profile: [] for profile in (CORE, *EMPTY_PROFILES)}


def _copy_for(result: dict, statuses: set[str]) -> dict:
    copied = {
        "fixture_id": result.get("fixture_id") or "",
        "mapping_version": result.get("mapping_version"),
        "decisions": result.get("decisions") or [],
        "documents": result.get("documents") or [],
        "candidates": result.get("candidates") or [],
        "corpus": result.get("corpus"),
        "by_profile": _empty_profiles(),
    }
    copied["by_profile"][CORE] = [
        decision
        for decision in result.get("by_profile", {}).get(CORE, [])
        if decision.get("status") in statuses
    ]
    return copied


def _parse(turtle: str) -> Graph:
    graph = Graph()
    if turtle and turtle.strip() and not turtle.lstrip().startswith("#"):
        graph.parse(data=turtle, format="turtle")
    return graph


def _term(value) -> str:
    if isinstance(value, URIRef):
        text = str(value)
        if text.startswith("https://w3id.org/fneo/") and "/resource/" not in text:
            local = text.rsplit("/", 1)[-1]
            if local.isidentifier() or local.replace("-", "").isalnum():
                return "fneo:" + local
        if text == "http://www.w3.org/1999/02/22-rdf-syntax-ns#type":
            return "rdf:type"
        if text == "http://www.w3.org/2000/01/rdf-schema#label":
            return "rdfs:label"
        if text.startswith("http://www.w3.org/2001/XMLSchema#"):
            return "xsd:" + text.rsplit("#", 1)[-1]
        return "<" + text + ">"
    lexical = str(value).replace("\\", "\\\\").replace('"', '\\"')
    datatype = getattr(value, "datatype", None)
    language = getattr(value, "language", None)
    if datatype:
        return f'"{lexical}"^^{_term(datatype)}'
    if language:
        return f'"{lexical}"@{language}'
    return f'"{lexical}"'


def deterministic_turtle(graph: Graph) -> str:
    grouped: dict[str, list[str]] = {}
    for subject, predicate, obj in graph:
        grouped.setdefault(str(subject), []).append(f"{_term(predicate)} {_term(obj)}")
    lines = [
        "@prefix fneo: <https://w3id.org/fneo/> .",
        "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .",
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
        "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
        "",
    ]
    for subject in sorted(grouped):
        bits = sorted(set(grouped[subject]))
        lines.append(f"{_term(URIRef(subject))} " + " ;\n    ".join(bits) + " .\n")
    text = "\n".join(lines).rstrip() + "\n"
    if contains_forbidden(text):
        raise ValueError("Refusing Turtle that contains a local endpoint, element identifier, or filesystem path.")
    return text


def assertion_only(turtle: str) -> str:
    graph = _parse(turtle)
    kept = Graph()
    for subject, predicate, obj in graph:
        if isinstance(subject, URIRef) and "/assertion/" in str(subject):
            kept.add((subject, predicate, obj))
    if len(kept) == 0:
        return "# No assertion resources were emitted for this partition.\n"
    return deterministic_turtle(kept)


def direct_domain_triples(turtle: str) -> list[str]:
    graph = _parse(turtle)
    found = []
    for subject, predicate, obj in graph:
        local = str(predicate).rstrip("/").rsplit("/", 1)[-1].rsplit("#", 1)[-1]
        if local not in DOMAIN_PREDICATES:
            continue
        if isinstance(subject, URIRef) and "/assertion/" in str(subject):
            continue
        found.append(f"{subject} {predicate} {obj}")
    return found


def materialise(result: dict, emit_profile) -> dict:
    """Emit core accepted, review, and rejected graphs. Experimental output stays empty."""
    accepted = emit_profile(_copy_for(result, {"accepted"}), CORE)
    review = assertion_only(emit_profile(_copy_for(result, {"requires_review"}), CORE))
    rejected = assertion_only(
        emit_profile(
            _copy_for(result, {"rejected", "out_of_scope", "insufficient_evidence", "suppressed"}),
            CORE,
        )
    )
    experimental = (
        "# CORE_DETERMINISTIC smoke test.\n"
        "# Extension and experimental profiles are disabled.\n"
        "# This graph contains no triples.\n"
    )
    review_direct = direct_domain_triples(review)
    rejected_direct = direct_domain_triples(rejected)
    experimental_direct = direct_domain_triples(experimental)
    return {
        "accepted": accepted if accepted.strip() else "# No accepted triples were emitted.\n",
        "review": review,
        "rejected": rejected,
        "experimental": experimental,
        "review_direct_triples": review_direct,
        "rejected_direct_triples": rejected_direct,
        "experimental_direct_triples": experimental_direct,
    }
