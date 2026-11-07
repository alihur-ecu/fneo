"""Shared helpers for the single-document adapter.

Public keys are digests of document-scoped application identifiers. A
canonical event identifier from the operational graph is not copied into
a public IRI.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ELEMENT_ID_RE = re.compile(r"^\d+:[0-9a-fA-F-]{8,}:\d+$")
FORBIDDEN_FRAGMENTS = (
    "bolt://",
    "neo4j://",
    "localhost",
    "127.0.0.1",
    ":7687",
    ":17688",
    "/home/",
    "financial-event-ontology-neo4j",
)


def dump_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def as_json(value):
    """Convert driver values to JSON values. Element identifiers are not invented."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else value
    if isinstance(value, list):
        return [as_json(item) for item in value]
    if isinstance(value, tuple):
        return [as_json(item) for item in value]
    if isinstance(value, dict):
        return {str(key): as_json(item) for key, item in value.items()}
    iso = getattr(value, "iso_format", None)
    if callable(iso):
        return iso()
    iso_py = getattr(value, "isoformat", None)
    if callable(iso_py):
        return iso_py()
    return str(value)


def as_int(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def as_text(value) -> str:
    if value is None:
        return ""
    return str(value)


def public_key(kind: str, document_id: str, application_id: str) -> str:
    """Digest an application identifier. The raw value is not the IRI segment."""
    raw = str(application_id).strip()
    if not raw:
        raise ValueError(f"Missing application identifier for {kind}.")
    digest = hashlib.sha256(f"{kind}|{document_id}|{raw}".encode("utf-8")).hexdigest()[:16]
    return f"{kind}-{digest}"


def token_span(start, end) -> tuple:
    """Convert an inclusive token span to a half-open span."""
    start_i = as_int(start)
    end_i = as_int(end)
    if start_i is None or end_i is None:
        return None, None, "absent"
    if end_i < start_i:
        return None, None, "invalid"
    return start_i, end_i + 1, "inclusive_token_converted_to_half_open"


def character_span(start, end, text: str) -> tuple:
    """Return a half-open character span when the stored convention can be observed."""
    start_i = as_int(start)
    end_i = as_int(end)
    if start_i is None or end_i is None:
        return None, None, "absent"
    if text:
        length = len(text)
        if end_i > start_i and end_i - start_i == length:
            return start_i, end_i, "source_half_open"
        if start_i <= end_i and end_i - start_i + 1 == length:
            return start_i, end_i + 1, "inclusive_character_converted_to_half_open"
    if end_i > start_i:
        return start_i, end_i, "assumed_half_open"
    if end_i == start_i:
        return start_i, end_i + 1, "zero_width_converted_to_half_open"
    return None, None, "invalid"


def contains_forbidden(value: str) -> bool:
    lowered = value.lower()
    if ELEMENT_ID_RE.match(value):
        return True
    return any(fragment in lowered for fragment in FORBIDDEN_FRAGMENTS)


def sanitise(value):
    """Drop private join keys and redact endpoint or filesystem fragments."""
    if isinstance(value, list):
        return [sanitise(item) for item in value]
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            if key in {"join_id", "start_join_id", "end_join_id", "element_id", "password"}:
                continue
            cleaned[key] = sanitise(item)
        return cleaned
    if isinstance(value, str) and contains_forbidden(value):
        return None
    return value


def load_flat_toml(path: Path) -> dict:
    data = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or "=" not in line:
            continue
        key, raw = line.split("=", 1)
        value = raw.strip()
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        if value == "true":
            parsed = True
        elif value == "false":
            parsed = False
        else:
            parsed = value
        data[key.strip()] = parsed
    return data
