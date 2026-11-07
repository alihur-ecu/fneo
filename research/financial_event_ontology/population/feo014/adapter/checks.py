"""Validation checks for the one-document population graphs."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS

from adapter.common import sha256_file
from adapter.safety.guards import repo_root

ONTOLOGY_SHA = "6e58c94ce6ffcd0f94d7e8257abb5a33f342b567f28438ebca1761fc122b78af"
RESOURCE = "https://w3id.org/fneo/resource/"


def _shacl():
    path = repo_root() / "research" / "financial_event_ontology" / "ontology" / "feo006" / "scripts" / "shacl_engine.py"
    spec = importlib.util.spec_from_file_location("feo006_shacl_engine_feo010", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _parse(turtle: str) -> Graph:
    graph = Graph()
    if turtle and turtle.strip() and not turtle.lstrip().startswith("#"):
        graph.parse(data=turtle, format="turtle")
    return graph


def validate_accepted(turtle: str, ontology_path: Path, core_path: Path, supplemental_path: Path) -> dict:
    module = _shacl()
    data = _parse(turtle)
    ontology = module.load_graph(ontology_path)
    results = []
    engine = ""
    for path in (core_path, supplemental_path):
        report = module.validate_graphs(data, module.load_graph(path), ontology)
        engine = report.engine
        results.extend(item.as_dict() for item in report.results)
    results.sort(key=lambda item: (item.get("severity", ""), item.get("message", ""), str(item.get("focus", ""))))
    violations = [item for item in results if item["severity"] == "Violation"]
    warnings = [item for item in results if item["severity"] == "Warning"]
    infos = [item for item in results if item["severity"] == "Info"]
    return {
        "conforms": not violations,
        "engine": engine,
        "violation_count": len(violations),
        "warning_count": len(warnings),
        "info_count": len(infos),
        "violations": violations[:40],
        "warnings": warnings[:40],
        "infos": infos[:40],
        "extension_shapes_applied": False,
        "note": "Core and supplemental shapes were applied to the accepted graph. Extension shapes were not applied.",
    }


def _allowed(term: URIRef, known: set) -> bool:
    text = str(term)
    if text.startswith(RESOURCE):
        return True
    if text.startswith("http://www.w3.org/1999/02/22-rdf-syntax-ns#"):
        return True
    if text.startswith("http://www.w3.org/2000/01/rdf-schema#"):
        return True
    if text.startswith("http://www.w3.org/2001/XMLSchema#"):
        return True
    if text.startswith("http://www.w3.org/2002/07/owl#"):
        return True
    return term in known


def public_term_audit(turtle: str, ontology_path: Path) -> dict:
    data = _parse(turtle)
    ontology = Graph()
    ontology.parse(ontology_path, format="turtle")
    known = set(ontology.subjects()) | set(ontology.predicates()) | set(ontology.objects())
    problems = []
    for _subject, predicate, obj in data:
        if isinstance(predicate, URIRef) and not _allowed(predicate, known):
            problems.append(str(predicate))
        if predicate == RDF.type and isinstance(obj, URIRef) and not _allowed(obj, known):
            problems.append("type:" + str(obj))
    return {"problem_count": len(set(problems)), "problems": sorted(set(problems))[:40]}


def prohibited_identifier_audit(turtle: str) -> dict:
    from adapter.common import ELEMENT_ID_RE, FORBIDDEN_FRAGMENTS

    data = _parse(turtle)
    problems = []
    for subject, predicate, obj in data:
        for term in (subject, predicate, obj):
            text = str(term)
            if ELEMENT_ID_RE.search(text) or any(fragment in text.lower() for fragment in FORBIDDEN_FRAGMENTS):
                problems.append(text[:180])
    return {"problem_count": len(problems), "problems": problems[:40]}


def reasoner_check(turtle: str, ontology_path: Path) -> dict:
    """Run a rule-based OWL RL expansion when owlrl is installed.

    This is not a complete OWL DL consistency proof. Entailed inverse
    temporal triples are not treated as extracted facts.
    """
    try:
        import owlrl
    except ImportError:
        return {
            "ran": False,
            "engine": "unavailable",
            "consistent": None,
            "unsatisfiable_classes": [],
            "note": "owlrl is not installed. No reasoner expansion was run.",
        }
    ontology = Graph()
    ontology.parse(ontology_path, format="turtle")
    combined = Graph()
    for triple in ontology:
        combined.add(triple)
    data = _parse(turtle)
    before = set(data)
    for triple in data:
        combined.add(triple)
    owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(combined)
    unsatisfiable = sorted(
        str(subject)
        for subject in combined.subjects(RDFS.subClassOf, OWL.Nothing)
        if isinstance(subject, URIRef) and not str(subject).startswith(RESOURCE)
    )
    entailed_only = []
    for triple in combined:
        if triple in before or triple in ontology:
            continue
        predicate = str(triple[1])
        if predicate.endswith(("precedes", "follows", "simultaneousWith", "occursDuring", "includes")):
            entailed_only.append(predicate.rsplit("/", 1)[-1])
    return {
        "ran": True,
        "engine": "owlrl.OWLRL_Semantics",
        "consistent": not unsatisfiable,
        "unsatisfiable_classes": unsatisfiable[:40],
        "entailed_inverse_or_order_predicates_not_counted_as_extractions": sorted(set(entailed_only)),
        "note": "Asserted-graph SHACL is separate from this expansion. Entailed order triples are not extracted facts.",
    }


def ontology_profile(ontology_path: Path) -> dict:
    graph = Graph()
    graph.parse(ontology_path, format="turtle")
    ontologies = list(graph.subjects(RDF.type, OWL.Ontology))
    return {
        "parsed": True,
        "triple_count": len(graph),
        "declares_owl_ontology": bool(ontologies),
        "checksum_sha256": sha256_file(ontology_path),
        "checksum_matches_rc2": sha256_file(ontology_path) == ONTOLOGY_SHA,
        "owl_dl_profile_validator": "not_installed",
        "note": "The ontology parses as RDF. A dedicated OWL 2 DL profile checker is not installed, so no OWL 2 DL profile pass is claimed.",
    }
