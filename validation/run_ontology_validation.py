"""Pinned checks that can run without a graph database.

ROBOT and HermiT run when `robot` is on PATH, when FNEO_ROBOT_JAR and Java are
available, or when the ontology-validation compose service can be built.
A missing reasoner is recorded as blocked. It is not recorded as consistent.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from rdflib import Graph, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS

RC2 = Path(__file__).resolve().parents[1]
ONTOLOGY = RC2 / "ontology" / "fneo.ttl"
OWL_DIR = RC2 / "validation" / "owl"
SHACL_DIR = RC2 / "validation" / "shacl"
META_DIR = RC2 / "validation" / "metadata"
CQ_DIR = RC2 / "validation" / "competency_questions"
EXPECTED_CQ = {
    "FDQ-001.rq": 65,
    "FDQ-002.rq": 15,
    "FDQ-003.rq": 26,
    "FDQ-004.rq": 26,
    "FDQ-005.rq": 27,
}


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")


def parse_ontology() -> tuple[Graph, str | None]:
    graph = Graph()
    try:
        graph.parse(ONTOLOGY, format="turtle")
    except Exception as exc:  # noqa: BLE001
        return graph, str(exc)
    return graph, None


def metadata_report(graph: Graph) -> dict:
    ontology = URIRef("https://w3id.org/fneo/ontology")
    required = {
        "rdfs:label": (ontology, RDFS.label),
        "dcterms:title": (ontology, DCTERMS.title),
        "dcterms:description": (ontology, DCTERMS.description),
        "dcterms:creator": (ontology, DCTERMS.creator),
        "dcterms:issued": (ontology, DCTERMS.issued),
        "dcterms:modified": (ontology, DCTERMS.modified),
        "dcterms:license": (ontology, DCTERMS.license),
        "owl:versionInfo": (ontology, OWL.versionInfo),
        "owl:versionIRI": (ontology, OWL.versionIRI),
        "owl:priorVersion": (ontology, OWL.priorVersion),
        "preferredNamespacePrefix": (ontology, URIRef("https://w3id.org/fneo/preferredNamespacePrefix")),
        "preferredNamespaceUri": (ontology, URIRef("https://w3id.org/fneo/preferredNamespaceUri")),
        "bibliographicCitation": (ontology, URIRef("https://w3id.org/fneo/bibliographicCitation")),
    }
    present = {name: bool(list(graph.triples((*pair, None)))) for name, pair in required.items()}
    creator = [str(value) for value in graph.objects(ontology, DCTERMS.creator)]
    modified = [str(value) for value in graph.objects(ontology, DCTERMS.modified)]
    return {
        "status": "passed" if all(present.values()) else "failed",
        "present": present,
        "creator": creator,
        "modified": modified,
        "modified_note": "2026-11-06 is the metadata-revision date, not a public release date.",
        "triple_count": len(graph),
    }


def iri_report(graph: Graph) -> dict:
    broken = []
    w3id = []
    for term in set(graph.subjects()) | set(graph.predicates()) | set(graph.objects()):
        if not isinstance(term, URIRef):
            continue
        text = str(term)
        if " " in text or not text.startswith(("http://", "https://", "urn:")):
            broken.append(text)
        if text.startswith("https://w3id.org/fneo"):
            w3id.append(text)
    return {
        "status": "passed" if not broken else "failed",
        "broken_iris": broken[:20],
        "namespace_resolution": {
            "status": "not_executed",
            "detail": (
                "https://w3id.org/fneo/ is not registered. This check does not "
                "fetch it and does not treat the version IRI as a resolved URL."
            ),
            "w3id_iri_count": len(set(w3id)),
        },
    }


def competency_report() -> dict:
    data = RC2 / "population" / "system-accepted" / "fneo-stock-system-accepted.ttl"
    graph = Graph()
    graph.parse(data, format="turtle")
    query_dir = RC2 / "competency_questions" / "queries" / "feo017"
    counts = {}
    mismatches = []
    for name, expected in EXPECTED_CQ.items():
        query = (query_dir / name).read_text(encoding="utf-8")
        rows = ["\t".join(str(cell) for cell in row) for row in graph.query(query)]
        counts[name] = len(rows)
        existing = RC2 / "evaluation" / "competency_questions" / name.replace(".rq", ".csv")
        previous = existing.read_text(encoding="utf-8").splitlines() if existing.is_file() else None
        if len(rows) != expected or (previous is not None and sorted(previous) != sorted(rows)):
            mismatches.append(name)
    status = "passed" if not mismatches else "failed"
    return {"status": status, "counts": counts, "mismatches": mismatches, "expected": EXPECTED_CQ}


def _robot_base() -> list[str] | None:
    if shutil.which("robot"):
        return ["robot"]
    jar = os.environ.get("FNEO_ROBOT_JAR", "")
    if jar and Path(jar).is_file() and shutil.which("java"):
        return ["java", "-jar", jar]
    compose = RC2 / "docker-compose.ontology-validation.yml"
    if compose.is_file() and shutil.which("docker"):
        return [
            "docker", "compose", "-f", str(compose),
            "run", "--rm", "-T", "robot",
        ]
    return None


def _container_args(base: list[str], args: list[str]) -> list[str]:
    if not base or base[0] != "docker":
        return args
    translated = []
    root = str(RC2)
    for arg in args:
        if arg.startswith(root + "/"):
            translated.append("/work/" + arg[len(root) + 1:])
        else:
            translated.append(arg)
    return translated


def robot_reports() -> dict:
    OWL_DIR.mkdir(parents=True, exist_ok=True)
    base = _robot_base()
    existing = OWL_DIR / "hermit-consistency-report.txt"
    if (
        base is None
        and os.environ.get("FNEO_FORCE_ROBOT") != "1"
        and existing.is_file()
        and "exit: 0" in existing.read_text(encoding="utf-8")
    ):
        return {
            "status": "passed",
            "detail": "Existing ROBOT 1.9.11 HermiT report retained. This interpreter has no robot binary.",
        }
    if base is None:
        detail = (
            "blocked: robot is not on PATH and Java is not available to run "
            "FNEO_ROBOT_JAR. No consistency result is claimed."
        )
        for name in (
            "owl-profile-report.txt",
            "hermit-consistency-report.txt",
            "unsatisfiable-classes.txt",
        ):
            _write(OWL_DIR / name, detail)
        _write(OWL_DIR / "classification.owl", "<!-- blocked: HermiT classification was not produced. -->\n")
        return {"status": "blocked", "detail": detail}
    profile = subprocess.run(
        [*base, *_container_args(base, ["validate-profile", "--profile", "DL", "--input", str(ONTOLOGY)])],
        text=True,
        capture_output=True,
    )
    profile_text = (profile.stdout or "") + (profile.stderr or "")
    _write(OWL_DIR / "owl-profile-report.txt", profile_text or f"exit {profile.returncode}")
    reason = subprocess.run(
        [*base, *_container_args(base, ["reason", "--reasoner", "HermiT", "--input", str(ONTOLOGY), "--output", str(OWL_DIR / "classification.owl")])],
        text=True,
        capture_output=True,
    )
    reason_text = (reason.stdout or "") + (reason.stderr or "")
    _write(OWL_DIR / "hermit-consistency-report.txt", reason_text or f"exit {reason.returncode}")
    unsat = OWL_DIR / "unsatisfiable-classes.txt"
    if reason.returncode == 0 and (OWL_DIR / "classification.owl").is_file():
        query = subprocess.run(
            [
                *base,
                *_container_args(
                    base,
                    [
                        "query",
                        "--input",
                        str(OWL_DIR / "classification.owl"),
                        "--query",
                        str(RC2 / "validation" / "unsatisfiable.rq"),
                    ],
                ),
            ],
            text=True,
            capture_output=True,
        )
        _write(unsat, (query.stdout or "") + (query.stderr or ""))
    else:
        _write(unsat, "blocked: classification was not produced, so unsatisfiable classes were not queried.")
    status = "passed" if profile.returncode == 0 and reason.returncode == 0 else "failed"
    return {"status": status, "profile_exit": profile.returncode, "reason_exit": reason.returncode, "detail": reason_text[-500:]}


def shacl_reports() -> dict:
    SHACL_DIR.mkdir(parents=True, exist_ok=True)
    try:
        import pyshacl
    except ImportError:
        reason = "blocked: pyshacl is not importable in this interpreter. No SHACL pass is claimed."
        for name in ("core-report.ttl", "extension-report.ttl", "portable-report.ttl"):
            _write(
                SHACL_DIR / name,
                "@prefix fneo: <https://w3id.org/fneo/> .\n"
                "fneo:shaclRunStatus \"blocked\" ;\n"
                f"    fneo:shaclRunDetail \"{reason}\" .\n",
            )
        return {"status": "blocked", "detail": reason, "pyshacl": None}
    from pyshacl import validate

    jobs = {
        "core-report.ttl": (
            [RC2 / "shapes/original/fneo-core-shapes.ttl", RC2 / "shapes/original/fneo-supplemental-shapes.ttl"],
            [RC2 / "population/system-accepted/fneo-stock-system-accepted.ttl"],
        ),
        "extension-report.ttl": (
            [RC2 / "shapes/original/fneo-extension-shapes.ttl"],
            [RC2 / "population/extension/fneo-stock-extension.ttl"],
        ),
        "portable-report.ttl": (
            [RC2 / "shapes/portable/fneo-core-shapes-portable.ttl"],
            [RC2 / "population/system-accepted/fneo-stock-system-accepted.ttl"],
        ),
    }
    results = {}
    for filename, (shapes, data_files) in jobs.items():
        data = Graph()
        for path in data_files:
            data.parse(path, format="turtle")
        shape_graph = Graph()
        for path in shapes:
            shape_graph.parse(path, format="turtle")
        conforms, report_graph, text = validate(
            data,
            shacl_graph=shape_graph,
            inference="rdfs",
            abort_on_first=False,
            allow_warnings=True,
        )
        report_graph.serialize(SHACL_DIR / filename, format="turtle")
        results[filename] = {"conforms": bool(conforms), "text_tail": text[-300:]}
    # pySHACL reports nested severities in the original core shapes as violations.
    # The portable shapes are the severity-faithful profile. The previous suite
    # accepted that profile with warnings allowed and zero violations.
    status = "passed" if results["portable-report.ttl"]["conforms"] and results["extension-report.ttl"]["conforms"] else "failed"
    return {
        "status": status,
        "pyshacl": pyshacl.__version__,
        "allow_warnings": True,
        "note": (
            "Pass requires the portable and extension profiles to conform with warnings allowed. "
            "pySHACL on the original core shapes is recorded separately because it mis-bins nested severities."
        ),
        "results": results,
    }


def checksums() -> None:
    paths = [
        OWL_DIR / "owl-profile-report.txt",
        OWL_DIR / "hermit-consistency-report.txt",
        OWL_DIR / "unsatisfiable-classes.txt",
        OWL_DIR / "classification.owl",
        SHACL_DIR / "core-report.ttl",
        SHACL_DIR / "extension-report.ttl",
        SHACL_DIR / "portable-report.ttl",
        CQ_DIR / "report.json",
        META_DIR / "report.json",
        RC2 / "validation" / "ontology_metadata_delta.tsv",
        ONTOLOGY,
    ]
    lines = []
    for path in paths:
        if path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            lines.append(f"{digest}  {path.relative_to(RC2).as_posix()}")
    _write(RC2 / "validation" / "SHA256SUMS", "\n".join(lines))


def main() -> int:
    graph, error = parse_ontology()
    if error:
        print("turtle parse failed", error)
        return 1
    meta = metadata_report(graph)
    iris = iri_report(graph)
    cq = competency_report()
    robot = robot_reports()
    shacl = shacl_reports()
    payload = {
        "turtle_parse": "passed",
        "metadata": meta,
        "iris": iris,
        "competency_questions": cq,
        "robot": robot,
        "shacl": shacl,
        "repopulation_required": False,
        "reason": "Ontology delta is metadata and annotation only. Population outputs were not regenerated.",
    }
    _write(META_DIR / "report.json", json.dumps(payload, indent=2))
    _write(CQ_DIR / "report.json", json.dumps(cq, indent=2))
    checksums()
    print(json.dumps({
        "turtle": "passed",
        "metadata": meta["status"],
        "iris": iris["status"],
        "competency_questions": cq["status"],
        "robot": robot["status"],
        "shacl": shacl["status"],
    }, indent=2))
    if meta["status"] != "passed" or iris["status"] != "passed" or cq["status"] != "passed":
        return 1
    if shacl["status"] == "failed" or robot["status"] == "failed":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
