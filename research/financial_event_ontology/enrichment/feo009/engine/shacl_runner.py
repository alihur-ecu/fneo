"""Load the local SHACL subset runner. No database connection is opened."""

from __future__ import annotations

import importlib.util
import sys

from rdflib import Graph

from engine.paths import core_shapes, extension_shapes, ontology_ttl, shacl_engine_path, supplemental_shapes


def shacl_module():
    path = shacl_engine_path()
    spec = importlib.util.spec_from_file_location("feo006_shacl_engine", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("The local SHACL subset runner could not be loaded.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def validate_turtle(turtle: str, profile: str) -> dict:
    if not turtle.strip():
        return {"conforms": True, "violation_count": 0, "results": [], "engine": "not-run", "note": "Empty profile graph."}
    module = shacl_module()
    data = Graph()
    data.parse(data=turtle, format="turtle")
    ontology = module.load_graph(ontology_ttl())
    shape_paths = [core_shapes(), supplemental_shapes()]
    if profile in {"EXTENSION_REVIEWED", "EXPERIMENTAL_TEMPORAL"}:
        shape_paths.append(extension_shapes())
    violations = []
    engine = ""
    for path in shape_paths:
        report = module.validate_graphs(data, module.load_graph(path), ontology)
        engine = report.engine
        for item in report.results:
            if item.severity == "Violation":
                violations.append(item.as_dict())
    return {
        "conforms": not violations,
        "violation_count": len(violations),
        "results": violations,
        "engine": engine,
        "note": "Independent SHACL confirmation remains a pre-release requirement.",
    }
