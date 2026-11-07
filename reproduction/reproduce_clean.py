"""Regenerate the semantic-projection experiment from this package alone.

Inputs, engines, public labels, and reference checksums all live under the
package root. No parent repository and no private second-reader directory
are read. A disposable Neo4j URI and password come from the environment.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import traceback
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reproduction"))

from graphio import (  # noqa: E402
    EXPECTED_DOCUMENTS,
    EXPECTED_NODES,
    EXPECTED_RELATIONSHIPS,
    GRAPH_DIR,
    SUPPLEMENT_NAME,
    sha256_file,
)

ENGINES = ROOT / "research" / "financial_event_ontology"
WORK = ROOT / "work" / "reproduction"
SEMANTIC_GLOBS = (
    "candidates/per_document/*/candidates.json",
    "decisions/per_document/*/decisions.json",
    "rdf/accepted/per_document/*.ttl",
    "rdf/review-required/per_document/*.ttl",
    "rdf/rejected/per_document/*.ttl",
    "rdf/experimental/per_document/*.ttl",
)
PACKAGED = {
    "System-Accepted Graph": ROOT / "population/system-accepted/fneo-stock-system-accepted.ttl",
    "Researcher-Adjudicated Projection": ROOT / "population/human-validated/fneo-stock-human-validated.ttl",
    "Review-Required Overlay": ROOT / "population/review-required/fneo-stock-review-required.ttl",
    "Rejected Graph": ROOT / "population/rejected/fneo-stock-rejected.ttl",
    "Extension Graph": ROOT / "population/extension/fneo-stock-extension.ttl",
    "Experimental Temporal Graph": ROOT / "population/experimental-temporal/fneo-stock-experimental-temporal.ttl",
}
CENSUS = {
    ("accepted", "structural_direct"): 4285,
    ("accepted", "direct_and_qualified"): 379,
    ("requires_review", "direct_and_qualified"): 1751,
    ("rejected", "direct_and_qualified"): 66,
    ("insufficient_evidence", "none"): 1481,
}
HEADLINE_EXPECTED = {
    "R-EVT-BASE": "31/50",
    "R-EVT-REF": "25/26",
    "R-REL-BASE": "29/50",
    "R-REL-REF": "23/26",
    "R-EVT-HOLD": "26/50",
    "R-REL-HOLD": "26/50",
    "R-EVT-AVAIL": "21/24",
    "R-REL-AVAIL": "6/19",
    "R-TRIG-EXACT": "0/27",
    "R-TRIG-PART": "18/27",
    "R-ASSERT-ALIGN": "22/25",
    "R-READ-EVT": "46/50",
    "R-READ-REL": "45/50",
    "R-READ-EVID": "26/27",
}
EXCLUDED = {"30/46", "28/46", "24/25"}
EXTRACTION_FILES = [
    "documents.json", "sentences.json", "tokens.json", "mentions.json",
    "canonical_entities.json", "canonical_events.json", "participants.json",
    "times.json", "temporal_relations.json", "values.json", "evidence.json",
    "warnings.json", "observed_counts.json", "indexes.json", "query_row_counts.json",
]


def _fail(report: dict, step: str, detail: str) -> None:
    report["steps"][step] = {"status": "fail", "detail": detail}
    report["ok"] = False


def _ok(report: dict, step: str, detail: str) -> None:
    report["steps"][step] = {"status": "pass", "detail": detail}


def _canonical_extraction(extracted: dict, name: str):
    if name == "query_row_counts.json":
        return extracted["query_row_counts"]
    if name == "indexes.json":
        payload = dict(extracted["bundle"]["indexes"])
        token_sentence = payload.get("token_sentence") or {}
        payload["token_sentence"] = {str(key): value for key, value in token_sentence.items()}
        return payload
    return extracted["bundle"][name[:-5]]


def _load_sums(path: Path) -> dict[str, str]:
    found = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            digest, relative = line.split(None, 1)
            found[relative] = digest
    return found


def verify_inputs(report: dict) -> None:
    checksums = (ROOT / "inputs/operational/SHA256SUMS").read_text(encoding="utf-8").splitlines()
    bad = []
    for line in checksums:
        if not line.strip():
            continue
        digest, relative = line.split(None, 1)
        path = ROOT / relative
        if not path.is_file() or sha256_file(path) != digest:
            bad.append(relative)
    documents = [path for path in GRAPH_DIR.glob("*.json") if path.name != SUPPLEMENT_NAME]
    supplement = GRAPH_DIR / SUPPLEMENT_NAME
    if bad or len(documents) != EXPECTED_DOCUMENTS or not supplement.is_file():
        _fail(report, "inputs", f"documents={len(documents)} mismatches={bad[:5]}")
        return
    payload = json.loads(supplement.read_text(encoding="utf-8"))
    phase_runs = len(payload.get("nodes") or [])
    cross = len(payload.get("relationships") or [])
    manifest = (ROOT / "document_manifest.tsv").read_text(encoding="utf-8").splitlines()
    header = manifest[0].split("\t")
    index = header.index("contains_meantime_annotation")
    flags = {line.split("\t")[index] for line in manifest[1:] if line.strip()}
    if phase_runs != 4 or cross != 432 or flags != {"no"}:
        _fail(report, "inputs", f"phase_runs={phase_runs} cross={cross} annotation_flags={sorted(flags)}")
        return
    _ok(
        report,
        "inputs",
        f"{len(documents)} document graphs and the store supplement match SHA256SUMS; "
        f"recorded import totals nodes={EXPECTED_NODES} relationships={EXPECTED_RELATIONSHIPS}",
    )


def extract_all(report: dict) -> bool:
    sys.path[:0] = [
        str(ENGINES / "population/feo011"),
        str(ENGINES / "population/feo010a/corrected_adapter"),
    ]
    from neo4j import GraphDatabase
    from driver.extract import extract_document
    from adapter.extraction.extractor import load_manifest
    from graphio import load_password

    destination = WORK / "extraction"
    if destination.exists():
        shutil.rmtree(destination)
    manifest = load_manifest()
    password = load_password()
    uri = os.environ["FNEO_REPRO_NEO4J_URI"]
    if "17688" in uri:
        _fail(report, "extraction", "refusing the frozen research endpoint")
        return False
    driver = GraphDatabase.driver(uri, auth=("neo4j", password))
    del password
    expected = _load_sums(ROOT / "expected" / "extraction.sha256")
    mismatches = []
    identifiers = sorted({relative.split("/")[0] for relative in expected}, key=int)
    with driver.session() as session:
        for document_id in identifiers:
            extracted = extract_document(session, manifest, document_id)
            out = destination / document_id
            out.mkdir(parents=True, exist_ok=True)
            for name in EXTRACTION_FILES:
                body = json.dumps(_canonical_extraction(extracted, name), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
                (out / name).write_text(body, encoding="utf-8")
                digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
                relative = f"{document_id}/{name}"
                if expected.get(relative) != digest:
                    mismatches.append(relative)
    driver.close()
    if mismatches or len(identifiers) != EXPECTED_DOCUMENTS:
        _fail(report, "extraction", f"mismatches={mismatches[:8]} documents={len(identifiers)}")
        return False
    _ok(report, "extraction", "30 documents regenerated the reference extraction checksums")
    return True


def _hashes(root: Path) -> dict[str, str]:
    found = {}
    for pattern in SEMANTIC_GLOBS:
        for path in sorted(root.glob(pattern)):
            found[path.relative_to(root).as_posix()] = sha256_file(path)
    return found


def _compare_checksums(fresh: Path, expected_file: Path) -> list[str]:
    left = _hashes(fresh)
    right = _load_sums(expected_file)
    bad = []
    if set(left) != set(right):
        bad.append(f"file set {len(left)} vs {len(right)}")
    bad.extend(sorted(key for key in left.keys() & right.keys() if left[key] != right[key]))
    return bad


def _drop_adapter_modules() -> None:
    for name in list(sys.modules):
        if name == "adapter" or name.startswith("adapter.") or name == "driver" or name.startswith("driver.") or name in {"run_feo014", "run_feo016"}:
            del sys.modules[name]


def run_configuration(report: dict, name: str, expected: Path | None, populate, *, refined: bool, compare_to: Path | None = None) -> bool:
    if refined:
        _drop_adapter_modules()
        sys.path[:0] = [str(ENGINES / "enrichment/feo016/population")]
        import run_feo016
        run_feo016.configure()
        _drop_adapter_modules()
        sys.path.insert(0, str(ENGINES / "population/feo014"))
        import run_feo014
        populate = run_feo014.install_population()
    destination = WORK / name
    if destination.exists():
        shutil.rmtree(destination)
    identifiers = sorted((path.name for path in (WORK / "extraction").iterdir() if path.is_dir()), key=int)
    sys.path.insert(0, str(ENGINES / "population/feo014"))
    import run_feo014
    for index, document_id in enumerate(identifiers, start=1):
        print(f"{name} {index}/{len(identifiers)} {document_id}", flush=True)
        bundle = run_feo014.load_bundle(WORK / "extraction" / document_id, document_id)
        populate.process_document(bundle, destination, validate_shacl=False)
    if compare_to is not None:
        mismatches = []
        left, right = _hashes(destination), _hashes(compare_to)
        if left != right:
            mismatches = sorted(key for key in set(left) | set(right) if left.get(key) != right.get(key))
    else:
        mismatches = _compare_checksums(destination, expected)
    if mismatches:
        _fail(report, name, f"{len(mismatches)} semantic files differ; first={mismatches[:5]}")
        return False
    _ok(report, name, f"{len(_hashes(destination))} semantic files matched")
    return True


def census(report: dict) -> None:
    counts: Counter = Counter()
    root = WORK / "refined" / "decisions" / "per_document"
    for path in root.glob("*/decisions.json"):
        for row in json.loads(path.read_text(encoding="utf-8")):
            counts[(row.get("status"), row.get("materialisation_policy"))] += 1
    observed = {key: counts[key] for key in CENSUS}
    if observed != CENSUS or sum(counts.values()) != 7962:
        _fail(report, "census", str(dict(counts)))
        return
    _ok(report, "census", "4285; 379; 1751; 66; 1481; total 7962")


def headlines(report: dict) -> None:
    from evaluate_headlines import calculate, write_csv

    public = ROOT / "evaluation" / "public"
    results = calculate(public, WORK / "refined")
    boundary = results[-1]["boundary"]
    rows = results[:-1]
    write_csv(WORK / "headline_results.csv", rows, list(rows[0]))
    bad = [row["result_id"] for row in rows if row["fraction"] != HEADLINE_EXPECTED[row["result_id"]]]
    calibration = [row["fraction"] for row in rows if row["fraction"] in EXCLUDED]
    if bad or calibration or any(row["unmatched_event"] or row["unmatched_relation"] for row in rows):
        _fail(report, "headlines", f"differ={bad} calibration={calibration} rows={[(r['result_id'], r['fraction']) for r in rows]}")
        return
    if boundary["ambiguous_assertion_paths"] != 2 or not boundary["accepted_duplicates_outside_included_view"]:
        _fail(report, "headlines", f"boundary={boundary}")
        return
    _ok(report, "headlines", "13 headline fractions match; two ambiguous paths and the accepted duplicate stay outside the headline denominators")


def packaged_views(report: dict) -> None:
    expected = json.loads((ROOT / "expected" / "publication_view_sha256.json").read_text(encoding="utf-8"))
    bad = []
    for name, path in PACKAGED.items():
        if not path.is_file() or sha256_file(path) != expected.get(name):
            bad.append(name)
    if bad:
        _fail(report, "publication_views", "checksum mismatch " + ", ".join(bad))
        return
    _ok(report, "publication_views", "six publication views match expected/publication_view_sha256.json")


def owl_and_shacl(report: dict) -> None:
    os.environ["FNEO_FORCE_ROBOT"] = "1"
    sys.path.insert(0, str(ROOT / "validation"))
    import run_ontology_validation as validation

    code = validation.main()
    robot = json.loads((ROOT / "validation/metadata/report.json").read_text(encoding="utf-8"))
    if code != 0:
        _fail(report, "ontology_validation", json.dumps({
            "robot": robot.get("robot", {}).get("status"),
            "shacl": robot.get("shacl", {}).get("status"),
            "cq": robot.get("competency_questions", {}).get("status"),
        }))
        return
    _ok(report, "ontology_validation", "ontology parse, HermiT, SHACL, and FDQ-001 through FDQ-005 completed")


def main() -> int:
    report: dict = {"ok": True, "steps": {}}
    try:
        verify_inputs(report)
        if report["ok"]:
            from import_operational_graphs import import_graphs
            counts = import_graphs(os.environ["FNEO_REPRO_NEO4J_URI"])
            if (
                counts.get("nodes") == EXPECTED_NODES
                and counts.get("relationships") == EXPECTED_RELATIONSHIPS
                and counts.get("documents") == 30
                and counts.get("phase_runs") == 4
                and counts.get("cross_document_relationships") == 432
            ):
                _ok(report, "import", str(counts))
            else:
                _fail(report, "import", str(counts))
        if report["ok"] and extract_all(report):
            _drop_adapter_modules()
            sys.path.insert(0, str(ENGINES / "population/feo014"))
            import run_feo014
            populate = run_feo014.install_population()
            if run_configuration(report, "baseline", ROOT / "expected/baseline_semantic.sha256", populate, refined=False):
                if run_configuration(report, "refined", ROOT / "expected/refined_semantic.sha256", populate, refined=True):
                    run_configuration(report, "refined_repeat", None, populate, refined=True, compare_to=WORK / "refined")
        if report["ok"]:
            census(report)
            headlines(report)
            packaged_views(report)
            owl_and_shacl(report)
    except Exception as exc:  # noqa: BLE001
        report["ok"] = False
        report["exception"] = str(exc)
        report["traceback"] = traceback.format_exc()
    destination = ROOT / "reports" / "clean_reproduction.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: value.get("status") for key, value in report["steps"].items()}, indent=2))
    if report.get("exception"):
        print(report["traceback"])
    print("ok", report["ok"])
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
