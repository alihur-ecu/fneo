"""Repository-relative paths. Absolute personal paths are not written to artefacts."""

from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def feo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def feo009_root() -> Path:
    return Path(__file__).resolve().parents[1]


def ontology_ttl() -> Path:
    return feo_root() / "ontology" / "feo007a" / "ontology" / "fneo-0.1.0-rc2.ttl"


def core_shapes() -> Path:
    return feo_root() / "ontology" / "feo007a" / "validation" / "fneo-core-shapes.ttl"


def extension_shapes() -> Path:
    return feo_root() / "ontology" / "feo007a" / "validation" / "fneo-extension-shapes.ttl"


def supplemental_shapes() -> Path:
    return feo_root() / "ontology" / "feo007a" / "validation" / "supplemental-shapes.ttl"


def shacl_engine_path() -> Path:
    return feo_root() / "ontology" / "feo006" / "scripts" / "shacl_engine.py"


def feo008_examples() -> Path:
    return feo_root() / "mappings" / "feo008" / "examples" / "source"


def feo008_manifest() -> Path:
    return feo_root() / "mappings" / "feo008" / "FEO008_TASK_MANIFEST.json"


def frozen_manifest() -> Path:
    return (
        feo_root()
        / "experiments"
        / "pipeline_runs"
        / "FEO-MASTER-001-STOCK-20261029T232113"
        / "feo002_manifest.json"
    )


def rules_dir() -> Path:
    return feo009_root() / "rules"


def lexicon_dir() -> Path:
    return rules_dir() / "lexicon"
