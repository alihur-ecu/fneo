"""Shared helpers for the operational-TextGraph reproduction package.

Paths are relative to the release-candidate root or the repository root.
This module does not print database passwords.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

RC2 = Path(__file__).resolve().parents[1]
GRAPH_DIR = RC2 / "inputs" / "operational" / "textgraphs"
SUPPLEMENT_NAME = "_store_supplement.json"
FORMAT = "textgraphx-operational-property-graph-1"
NEO4J_VERSION = "5.9.0"
SCHEMA_VERSION = "textgraphx-lpg-unversioned-property"
TEXTGRAPHX_MODEL = (
    "Hur, Janjua, and Ahmed (2024), Expert Systems with Applications, 239, 122269. "
    "DOI 10.1016/j.eswa.2023.122269."
)
EXPECTED_DOCUMENTS = 30
EXPECTED_NODES = 27126
EXPECTED_RELATIONSHIPS = 121539
LABEL_RE = __import__("re").compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_password(env_var: str = "FEO_NEO4J_PASSWORD") -> str:
    current = os.environ.get(env_var, "") or os.environ.get("FNEO_NEO4J_PASSWORD", "")
    if current:
        return current
    raise RuntimeError(
        f"{env_var} is not set. Set it to the password of the disposable Neo4j container. "
        "This package does not read a password file."
    )


def canonical_json(payload) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def write_json(path: Path, payload) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = canonical_json(payload)
    path.write_bytes(body)
    return sha256_bytes(body)


def document_graph_files() -> list[Path]:
    files = sorted(path for path in GRAPH_DIR.glob("*.json") if path.name != SUPPLEMENT_NAME)
    return files


def assert_label(name: str) -> str:
    if not LABEL_RE.match(name):
        raise RuntimeError(f"Refusing a graph label that is not a plain identifier: {name!r}")
    return name
