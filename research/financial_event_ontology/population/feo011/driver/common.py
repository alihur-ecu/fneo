"""Paths, checksums, and CSV helpers for the dry population."""

from __future__ import annotations

import csv
import hashlib
import os
import sys
from pathlib import Path

FEO011 = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[5]
ADAPTER_ROOT = (
    REPO
    / "research"
    / "financial_event_ontology"
    / "population"
    / "feo010a"
    / "corrected_adapter"
)
ONTOLOGY_SHA = "6e58c94ce6ffcd0f94d7e8257abb5a33f342b567f28438ebca1761fc122b78af"
EXPECTED_NODES = 27126
EXPECTED_RELATIONSHIPS = 121539
EXPECTED_DOCUMENTS = 30
FROZEN_RUN = "FEO-MASTER-001-STOCK-20261029T232113"
CORPUS = "meantime-en-stock"
APPROVED_URI = "bolt://127.0.0.1:17688"

RECORD_GROUPS = (
    "documents",
    "sentences",
    "tokens",
    "mentions",
    "canonical_entities",
    "canonical_events",
    "participants",
    "times",
    "temporal_relations",
    "values",
    "evidence",
)


def ensure_adapter_path() -> None:
    text = str(ADAPTER_ROOT)
    if text not in sys.path:
        sys.path.insert(0, text)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tree_hash(path: Path) -> str:
    digest = hashlib.sha256()
    if path.is_file():
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
        return digest.hexdigest()
    files = sorted(item for item in path.rglob("*") if item.is_file() and "__pycache__" not in item.parts and item.suffix != ".pyc")
    for file in files:
        digest.update(str(file.relative_to(path)).encode())
        digest.update(b"\0")
        digest.update(file.read_bytes())
    return digest.hexdigest()


def scrub(text: str) -> str:
    """Remove a loaded research password from an error string."""
    secret = os.environ.get("FEO_NEO4J_PASSWORD", "")
    cleaned = text
    if secret:
        cleaned = cleaned.replace(secret, "[redacted]")
    return cleaned


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _cell(row.get(key, "")) for key in fieldnames})


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return "|".join(_cell(item) for item in value)
    return str(value)


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def local_name(iri: str) -> str:
    if not iri:
        return ""
    return str(iri).rstrip("/").rsplit("/", 1)[-1].rsplit("#", 1)[-1]


def excerpt(text: str, limit: int = 240) -> str:
    return " ".join(str(text or "").split())[:limit]


def protected_hashes() -> dict:
    feo = REPO / "research" / "financial_event_ontology"
    return {
        "ontology": sha256_file(feo / "ontology/feo007a/ontology/fneo-0.1.0-rc2.ttl"),
        "core_shapes": sha256_file(feo / "ontology/feo007a/validation/fneo-core-shapes.ttl"),
        "supplemental_shapes": sha256_file(feo / "ontology/feo007a/validation/supplemental-shapes.ttl"),
        "extension_shapes": sha256_file(feo / "ontology/feo007a/validation/fneo-extension-shapes.ttl"),
        "feo009_rules": tree_hash(feo / "enrichment/feo009/rules"),
        "feo009": tree_hash(feo / "enrichment/feo009"),
        "feo008": tree_hash(feo / "mappings/feo008"),
        "feo010a_adapter": tree_hash(ADAPTER_ROOT),
        "corpus_naf": tree_hash(REPO / "src/textgraphx/datastore/meantime_newsreader_english_raw_NAF/corpus_stock"),
        "corpus_gold": tree_hash(REPO / "src/textgraphx/datastore/annotated/corpus_stock"),
        "document_inventory": sha256_file(feo / "corpus_audit/stock_documents.csv"),
    }
